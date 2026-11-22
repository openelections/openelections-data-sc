"""Build South Carolina general election county and precinct files from the
Clarity/ENR election-night reporting site (enr-scvotes.org).

Sources: Clarity detail.xml per county plus the state-level detail.xml
(used as cross-check for multi-county contests). XMLs are downloaded to
$SC2026_XML_DIR (default /tmp/sc2026/<county-or-state>/detail.xml).

Outputs (OpenElections conventions, mirroring the 2022/2024 files):
  2026/counties/20261103__sc__general__<county>__precinct.csv   (one per county, every contest)
  2026/20261103__sc__general__precinct.csv                       (consolidated statewide precinct file)
  2026/20261103__sc__general__county.csv                         (county-level totals, state/federal offices)

Run:  pipenv run python build_2026_general.py
"""
import requests
import zipfile
import io
import os
import csv
import re
import collections

import clarify
from lxml import etree

STATE_URL = 'https://www.enr-scvotes.org/SC/127300/web.345435/#/summary'
STATE_REPORT_BASE = 'https://results.enr.clarityelections.com/SC/127300/386661'
XML_DIR = os.environ.get('SC2026_XML_DIR', '/tmp/sc2026')
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026')
DATE = '20261103'
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

VOTE_TYPES = ['early_voting', 'failsafe_provisional', 'provisional', 'failsafe', 'absentee_by_mail', 'election_day']
VOTE_TYPE_MAP = {
    'Election Day': 'election_day',
    'Early Voting': 'early_voting',
    'Absentee By Mail': 'absentee_by_mail',
    'Provisional': 'provisional',
    'Failsafe': 'failsafe',
    'Failsafe Provisional': 'failsafe_provisional',
    'Provionsal': 'provisional',  # typo in Charleston's export
}
HEADER = ['county', 'precinct', 'office', 'district', 'candidate', 'party', 'votes'] + VOTE_TYPES
COUNTY_HEADER = ['county', 'office', 'district', 'party', 'candidate', 'votes']

# Offices included in the consolidated statewide file; everything else stays in
# the per-county files. "Auditor" is NOT statewide: it is each county's Auditor.
STATEWIDE = {
    'Straight Party', 'Ballots Cast', 'U.S. Senate', 'U.S. House',
    'Governor and Lieutenant Governor', 'Secretary of State', 'State Treasurer',
    'Attorney General', 'Comptroller General',
    'State Superintendent of Education', 'Commissioner of Agriculture',
    'State House', 'State Senate', 'Solicitor',
}


def norm_ws(s):
    return re.sub(r'\s+', ' ', s).strip()


def norm_slash(s):
    """Candidate ticket names appear with inconsistent '/' spacing across county
    and state snapshots; canonicalize to ' / '."""
    return re.sub(r'\s*/\s*', ' / ', s)


def parse_office(text):
    text = norm_ws(text)
    m = re.match(r'^STRAIGHT PARTY \d+$', text)
    if m:
        return ['Straight Party', '']
    m = re.match(r'^(U\.S\.|State) House of Representatives, District (\d+)$', text)
    if m:
        return ['U.S. House' if m.group(1) == 'U.S.' else 'State House', m.group(2)]
    if text == 'U.S. Senate':
        return ['U.S. Senate', '']
    m = re.match(r'^State Senate District (\d+) \(Unexpired Term\)$', text)
    if m:
        return ['State Senate', m.group(1)]
    m = re.match(r'^Solicitor, Circuit (\d+)$', text)
    if m:
        return ['Solicitor', m.group(1)]
    if text in ('Governor and Lieutenant Governor', 'Secretary of State', 'State Treasurer',
                'Attorney General', 'Comptroller General', 'State Superintendent of Education',
                'Commissioner of Agriculture'):
        return [text, '']
    return [text, '']


def parse_candidate(choice):
    text = norm_slash(norm_ws(choice.text)) if choice.text else ''
    party = norm_ws(choice.party) if choice.party else None
    if party and text.upper().startswith(party.upper() + ' ') and len(party) <= 4:
        text = text[len(party) + 1:].strip()
    return text, party


def strip_prefix(text, party):
    if party and text.upper().startswith(party.upper() + ' ') and len(party) <= 4:
        return text[len(party) + 1:].strip()
    return text


def download():
    """Download and extract detailxml.zip for the state and all counties."""
    j = clarify.Jurisdiction(url=STATE_URL, level='state')
    urls = [('state', STATE_REPORT_BASE + '/reports/detailxml.zip')]
    for sub in j.get_subjurisdictions():
        urls.append((sub.name.replace(' ', '_').lower(), sub.report_url('xml')))
    for name, url in urls:
        d = os.path.join(XML_DIR, name)
        os.makedirs(d, exist_ok=True)
        target = os.path.join(d, 'detail.xml')
        if os.path.isfile(target):
            continue
        r = requests.get(url, headers=UA, timeout=120)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(d)
        print('downloaded', name, len(r.content))


def collect_results():
    """Parse every county detail.xml into rows keyed by
    (county, precinct, office, district, party, candidate) -> vote-type dict."""
    votes = collections.OrderedDict()
    for d in sorted(os.listdir(XML_DIR)):
        xml_path = os.path.join(XML_DIR, d, 'detail.xml')
        if not os.path.isfile(xml_path) or d == 'state':
            continue
        tree = etree.parse(xml_path)
        region_el = tree.find('.//Region')
        region = region_el.text.strip() if region_el is not None else d
        p = clarify.Parser()
        p.parse(xml_path)
        for result in p.results:
            if result.choice is None or result.jurisdiction is None:
                continue
            vote_type = VOTE_TYPE_MAP.get(result.vote_type)
            if vote_type is None:
                continue
            office, district = parse_office(norm_slash(norm_ws(result.contest.text)))
            candidate, party = parse_candidate(result.choice)
            key = (region, result.jurisdiction.name, office, district, party, candidate)
            votes.setdefault(key, {})[vote_type] = int(result.votes or 0)
    return votes


def rowlist(votes_row):
    return [votes_row.get(vt, 0) for vt in VOTE_TYPES]


def write_county_files(votes):
    county_dir = os.path.join(OUT_ROOT, 'counties')
    os.makedirs(county_dir, exist_ok=True)
    by_county = collections.OrderedDict()
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        by_county.setdefault(county, []).append((precinct, office, district, candidate, party, vt))
    for county, rows in by_county.items():
        fname = os.path.join(county_dir,
                             DATE + '__sc__general__' + county.replace(' ', '_').lower() + '__precinct.csv')
        with open(fname, 'w') as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            for precinct, office, district, candidate, party, vt in sorted(rows, key=lambda r: (r[1], r[2], r[0])):
                vals = rowlist(vt)
                w.writerow([county, precinct, office, district, candidate, party, sum(vals)] + vals)


def write_consolidated(votes):
    """Consolidated statewide precinct file, plus Ballots Cast rows from each
    county's VoterTurnout section."""
    ballots = []
    for d in sorted(os.listdir(XML_DIR)):
        xml_path = os.path.join(XML_DIR, d, 'detail.xml')
        if not os.path.isfile(xml_path) or d == 'state':
            continue
        tree = etree.parse(xml_path)
        region = tree.find('.//Region').text.strip()
        for p in tree.findall('.//VoterTurnout/Precincts/Precinct'):
            ballots.append((region, p.attrib['name'], int(p.attrib['ballotsCast'])))
    fname = os.path.join(OUT_ROOT, DATE + '__sc__general__precinct.csv')
    offices = []
    for key in votes.keys():
        if key[2] not in offices:
            offices.append(key[2])
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for office in offices:
            if office not in STATEWIDE:
                continue
            for key in votes.keys():
                if key[2] != office:
                    continue
                county, precinct, office, district, party, candidate = key
                vals = rowlist(votes[key])
                w.writerow([county, precinct, office, district, candidate, party, sum(vals)] + vals)
        for county, precinct, bc in sorted(ballots):
            w.writerow([county, precinct, 'Ballots Cast', '', '', '', bc] + [0] * 6)


def write_county_level(votes):
    fname = os.path.join(OUT_ROOT, DATE + '__sc__general__county.csv')
    agg = collections.OrderedDict()
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        if office not in STATEWIDE or office in ('Ballots Cast', 'Straight Party'):
            continue
        key = (county, office, district, party, candidate)
        agg.setdefault(key, collections.Counter()).update(vt)
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow(COUNTY_HEADER)
        for (county, office, district, party, candidate), vt in sorted(agg.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
            w.writerow([county, office, district, party, candidate, sum(vt.values())])


def validate(votes):
    """Cross-check precinct sums against the state-level snapshot.
    Returns (n_state_keys, mismatches, sample, missing, extra)."""
    state_xml = os.path.join(XML_DIR, 'state', 'detail.xml')
    tree = etree.parse(state_xml)
    state_data = {}
    for contest in tree.iter('Contest'):
        office, district = parse_office(norm_slash(norm_ws(contest.attrib['text'])))
        if office not in STATEWIDE:
            continue
        for choice in contest.iter('Choice'):
            candidate = strip_prefix(norm_slash(norm_ws(choice.attrib.get('text', ''))),
                                     choice.attrib.get('party'))
            for vt in choice.iter('VoteType'):
                name = VOTE_TYPE_MAP.get(norm_ws(vt.attrib['name']))
                if name is None:
                    continue
                for c in vt.iter('County'):
                    key = (c.attrib['name'], office, district, name, candidate)
                    state_data[key] = int(c.attrib['votes'])
    calc = {}
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        for name, n in vt.items():
            calc[(county, office, district, name, candidate)] = \
                calc.get((county, office, district, name, candidate), 0) + n
    mismatches = []
    missing = set(calc) - set(state_data)
    extra = set(state_data) - set(calc)
    for key in sorted(set(calc) & set(state_data)):
        if calc[key] != state_data[key]:
            mismatches.append((key, 'want', state_data[key], 'got', calc[key]))
    return len(state_data), len(mismatches), mismatches[:25], sorted(missing)[:10], sorted(extra)[:10]


if __name__ == '__main__':
    download()
    votes = collect_results()
    os.makedirs(OUT_ROOT, exist_ok=True)
    write_county_files(votes)
    write_consolidated(votes)
    write_county_level(votes)
    checked, n_mismatch, sample, missing, extra = validate(votes)
    print('rows:', len(votes))
    print('state-side key count:', checked, 'mismatches:', n_mismatch)
    print('sample mismatches:', sample)
    print('keys only in county parse (local contests expected):', missing)
    print('keys only in state snapshot:', extra)
