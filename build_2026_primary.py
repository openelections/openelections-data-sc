"""Build South Carolina 2026 primary election county and precinct files from
the Clarity/ENR reporting site (enr-scvotes.org), mirroring the 2024 primary
files' conventions.

Sources: Clarity detail.xml per county plus the state-level detail.xml
(cross-check). XMLs live in $SC2026_PRIMARY_XML_DIR (default /tmp/sc2026_primary).

Outputs:
  2026/counties/20260609__sc__primary__<county>__precinct.csv   (one per county, every contest)
  2026/20260609__sc__primary__precinct.csv                      (consolidated statewide precinct file)
  2026/20260609__sc__primary__county.csv                        (county-level totals for statewide offices)

Party primaries in the ENR export are separate contests per party, named
"<Office> - DEM" / "... - REP" (Oconee uses a leading "DEM "/"REP " prefix);
the suffix/prefix is stripped into the party column. Unlike the general
election files there are no Ballots Cast rows (matches the 2024 primary
convention).

Run:  pipenv run python build_2026_primary.py
"""
import sys
import os
import csv
import re
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clarify
import requests
import zipfile
import io
from lxml import etree

from build_2026_general import (norm_ws, norm_slash, strip_prefix, parse_candidate,
                                VOTE_TYPE_MAP, VOTE_TYPES, HEADER, COUNTY_HEADER, UA)

PRIMARY_URL = 'https://www.enr-scvotes.org/SC/126294/web.345435/#/summary'
PRIMARY_STATE_BASE = 'https://results.enr.clarityelections.com/SC/126294/375593'
XML_DIR = os.environ.get('SC2026_PRIMARY_XML_DIR', '/tmp/sc2026_primary')
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026')
DATE = '20260609'


def parse_office_primary(text):
    """Split "<office> - DEM|REP" / "DEM|REP <office>" into (office, party).
    Office normalization reuses the general parser."""
    text = norm_ws(text.replace('&amp;', '&'))
    m = re.match(r'^(.*\S)\s*-\s*(DEM|REP)\s*$', text)
    if m:
        return [m.group(1), m.group(2)]
    m2 = re.match(r'^(DEM|REP)\s+(.*\S)$', text)
    if m2:
        return [m2.group(2), m2.group(1)]
    return [text, None]


def parse_office_party(text):
    """Strip the DEM/REP suffix or prefix from a primary contest name.
    Returns (base_text_for_parse_office, party)."""
    base, party = parse_office_primary(text)
    return base, party


def norm_candidate_name(text):
    """Canonical form for candidate choice text: collapse whitespace, drop the
    ENR '*Decertified before Primary*' annotation (present in 45 counties but
    not Chester's export), and normalize spaced hyphens ('Rivera - Vazquez'
    becomes 'Rivera-Vazquez'; the state rollup uses the unspaced form)."""
    text = norm_ws(text)
    text = re.sub(r'\s*-\s*\*Decertified before Primary\*', '', text)
    text = norm_slash(text)
    text = re.sub(r'(?<=\w)\s*-\s*(?=\w)', '-', text)
    return text.strip()


def parse_candidate_primary(choice):
    text = norm_candidate_name(choice.text) if choice.text else ''
    party = norm_ws(choice.party) if choice.party else None
    if party and text.upper().startswith(party.upper() + ' ') and len(party) <= 4:
        text = text[len(party) + 1:].strip()
    return text, party


def download():
    j = clarify.Jurisdiction(url=PRIMARY_URL, level='state')
    urls = [('state', PRIMARY_STATE_BASE + '/reports/detailxml.zip')]
    for sub in j.get_subjurisdictions():
        urls.append((sub.name.replace(' ', '_').lower(), sub.report_url('xml')))
    for name, url in urls:
        d = os.path.join(XML_DIR, name)
        os.makedirs(d, exist_ok=True)
        if os.path.isfile(os.path.join(d, 'detail.xml')):
            continue
        r = requests.get(url, headers=UA, timeout=120)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(d)
        print('downloaded', name, len(r.content))


def collect_results():
    """(county, precinct, office, district, party, candidate) -> vote-type dict,
    with the contest's DEM/REP suffix normalized into the party column.
    Statewide contests listed in the state rollup go to the consolidated and
    county-level files; everything else stays in the per-county files."""
    # contest texts (used to identify rollup contests); see collect_results
    state_offices = set()
    tree = etree.parse(os.path.join(XML_DIR, 'state', 'detail.xml'))
    for contest in tree.iter('Contest'):
        state_offices.add(contest.attrib['text'])

    votes = collections.OrderedDict()
    statewide_rows = []
    for d in sorted(os.listdir(XML_DIR)):
        xml_path = os.path.join(XML_DIR, d, 'detail.xml')
        if not os.path.isfile(xml_path) or d == 'state':
            continue
        tree = etree.parse(xml_path)
        region = tree.find('.//Region').text.strip()
        p = clarify.Parser()
        p.parse(xml_path)
        for result in p.results:
            if result.choice is None or result.jurisdiction is None:
                continue
            vote_type = VOTE_TYPE_MAP.get(result.vote_type)
            if vote_type is None:
                continue
            raw_text = result.contest.text
            base, party_contest = parse_office_party(raw_text)
            office, district = _parse_office_for_primary(base)
            candidate, party_choice = parse_candidate_primary(result.choice)
            party = party_contest or party_choice
            key = (region, result.jurisdiction.name, office, district, party, candidate)
            votes.setdefault(key, {})[vote_type] = int(result.votes or 0)
    return votes, state_offices


def _parse_office_for_primary(base_text):
    from build_2026_general import parse_office
    office, district = parse_office(base_text)
    return office, district or ''


def rowlist(votes_row):
    return [votes_row.get(vt, 0) for vt in VOTE_TYPES]


def normalized_offices_in_rollup(state_offices):
    """(office, district) tuples as they appear in the state rollup."""
    out = set()
    for text in state_offices:
        base, party = parse_office_party(text)
        office, district = _parse_office_for_primary(base)
        out.add((office, district or ''))
    return out


def write_county_files(votes):
    county_dir = os.path.join(OUT_ROOT, 'counties')
    os.makedirs(county_dir, exist_ok=True)
    by_county = collections.OrderedDict()
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        by_county.setdefault(county, []).append((precinct, office, district, candidate, party, vt))
    for county, rows in by_county.items():
        fname = os.path.join(county_dir,
                             DATE + '__sc__primary__' + county.replace(' ', '_').lower() + '__precinct.csv')
        with open(fname, 'w') as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            for precinct, office, district, candidate, party, vt in sorted(rows, key=lambda r: (r[1], r[2], r[0])):
                vals = rowlist(vt)
                w.writerow([county, precinct, office, district, candidate, party or '', sum(vals)] + vals)


def write_consolidated(votes, rollup_keys):
    fname = os.path.join(OUT_ROOT, DATE + '__sc__primary__precinct.csv')
    offices = sorted({k[2] for k in votes.keys() if (k[2], k[3] or '') in rollup_keys})
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for office in offices:
            for key in sorted(votes.keys(), key=lambda k: (k[0], k[1])):
                if key[2] != office or (key[2], key[3] or '') not in rollup_keys:
                    continue
                county, precinct, office, district, party, candidate = key
                vals = rowlist(votes[key])
                w.writerow([county, precinct, office, district, candidate, party or '', sum(vals)] + vals)


def write_county_level(votes, rollup_keys):
    fname = os.path.join(OUT_ROOT, DATE + '__sc__primary__county.csv')
    agg = collections.Counter()
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        if (office, district or '') not in rollup_keys:
            continue
        agg[(county, office, district, party or '', candidate)] += sum(vt.values())
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow(COUNTY_HEADER)
        for (county, office, district, party, candidate), n in sorted(agg.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
            w.writerow([county, office, district, party, candidate, n])


def validate(votes, rollup_keys):
    """Cross-check every state-rollup contest's per-county/per-vote-type/candidate
    totals against the state-level snapshot."""
    tree = etree.parse(os.path.join(XML_DIR, 'state', 'detail.xml'))
    state_data = {}
    for contest in tree.iter('Contest'):
        base, party = parse_office_party(contest.attrib['text'])
        office, district = _parse_office_for_primary(base)
        for choice in contest.iter('Choice'):
            candidate = norm_candidate_name(choice.attrib.get('text', ''))
            party_attr = norm_ws(choice.attrib.get('party'))
            candidate = strip_prefix(candidate, party_attr)
            for vt in choice.iter('VoteType'):
                name = VOTE_TYPE_MAP.get(norm_ws(vt.attrib['name']))
                if name is None:
                    continue
                for c in vt.iter('County'):
                    state_data[(c.attrib['name'], office, district or '', name, candidate)] = int(c.attrib['votes'])
    calc = {}
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        for name, n in vt.items():
            calc[(county, office, district or '', name, candidate)] = \
                calc.get((county, office, district or '', name, candidate), 0) + n
    mismatches = []
    for key in sorted(set(calc) & set(state_data)):
        if calc[key] != state_data[key]:
            mismatches.append((key, 'want', state_data[key], 'got', calc[key]))
    extra = sorted(set(state_data) - set(calc))
    return len(state_data), len(mismatches), mismatches[:20], extra[:20]


if __name__ == '__main__':
    download()
    votes, state_contests = collect_results()
    rollup_keys = normalized_offices_in_rollup(state_contests)
    os.makedirs(OUT_ROOT, exist_ok=True)
    write_county_files(votes)
    write_consolidated(votes, rollup_keys)
    write_county_level(votes, rollup_keys)
    checked, n_mismatch, sample, extra = validate(votes, rollup_keys)
    print('rows:', len(votes))
    print('rollup keys:', len(rollup_keys), '| state-side key count:', checked, 'mismatches:', n_mismatch)
    print('sample mismatches:', sample)
    print('keys only in state snapshot (candidates with no precinct rows):', extra)
