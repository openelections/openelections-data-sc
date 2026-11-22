"""Build the U.S. Senate special Republican primary RUNOFF (August 25, 2026) county
and precinct files from the Clarity/ENR site, mirroring the 2026 primary
pipeline (single statewide contest: "U.S.  Senate  - REP", top-two runoff).

Source: https://www.enr-scvotes.org/SC/127179/web.345435
XMLs live in $SC2026_SENATE_XML_DIR (default /tmp/sc2026_senate_special).

Outputs (no Ballots Cast rows, matching the 2026 primary convention):
  2026/counties/20260825__sc__special__primary__runoff__<county>__precinct.csv
  2026/20260825__sc__special__primary__runoff__precinct.csv
  2026/20260825__sc__special__primary__runoff__county.csv

Run:  pipenv run python build_2026_senate_special.py
"""
import sys
import os
import csv
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clarify
import requests
import zipfile
import io
from lxml import etree

from build_2026_general import (VOTE_TYPE_MAP, VOTE_TYPES, HEADER, COUNTY_HEADER, UA)
from build_2026_primary import (parse_office_party, _parse_office_for_primary,
                                norm_candidate_name, parse_candidate_primary,
                                strip_prefix, norm_ws, norm_slash)

SENATE_URL = 'https://www.enr-scvotes.org/SC/127179/web.345435/#/summary'
SENATE_STATE_BASE = 'https://results.enr.clarityelections.com/SC/127179/379277'
XML_DIR = os.environ.get('SC2026_SENATE_RUNOFF_XML_DIR', '/tmp/sc2026_senate_runoff')
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026')
DATE = '20260825'
ELECTION_TAG = 'special__primary__runoff'


def download():
    j = clarify.Jurisdiction(url=SENATE_URL, level='state')
    urls = [('state', SENATE_STATE_BASE + '/reports/detailxml.zip')]
    subs = None
    for _ in range(3):  # the county list occasionally fails behind the CDN
        try:
            subs = j.get_subjurisdictions()
            break
        except Exception as e:  # noqa: BLE001
            print('retrying county list:', e)
    if subs:
        for sub in subs:
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
    votes = collections.OrderedDict()
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
            base, party = parse_office_party(norm_ws(result.contest.text))
            office, district = _parse_office_for_primary(base)
            candidate, party_choice = parse_candidate_primary(result.choice)
            party = party or party_choice
            key = (region, result.jurisdiction.name, office, district or '', party, candidate)
            votes.setdefault(key, {})[vote_type] = int(result.votes or 0)
    return votes


def rowlist(votes_row):
    return [votes_row.get(vt, 0) for vt in VOTE_TYPES]


def write_outputs(votes):
    county_dir = os.path.join(OUT_ROOT, 'counties')
    os.makedirs(county_dir, exist_ok=True)
    by_county = collections.OrderedDict()
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        by_county.setdefault(county, []).append((precinct, office, district, candidate, party, vt))
    for county, rows in by_county.items():
        fname = os.path.join(county_dir, DATE + '__sc__' + ELECTION_TAG + '__'
                             + county.replace(' ', '_').lower() + '__precinct.csv')
        with open(fname, 'w') as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            for precinct, office, district, candidate, party, vt in sorted(rows, key=lambda r: (r[1], r[2], r[0])):
                vals = rowlist(vt)
                w.writerow([county, precinct, office, district, candidate, party or '', sum(vals)] + vals)

    fname = os.path.join(OUT_ROOT, DATE + '__sc__' + ELECTION_TAG + '__precinct.csv')
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for key in sorted(votes.keys(), key=lambda k: (k[0], k[1], k[-1])):
            county, precinct, office, district, party, candidate = key
            vals = rowlist(votes[key])
            w.writerow([county, precinct, office, district, candidate, party or '', sum(vals)] + vals)

    fname = os.path.join(OUT_ROOT, DATE + '__sc__' + ELECTION_TAG + '__county.csv')
    agg = collections.Counter()
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        agg[(county, office, district, party or '', candidate)] += sum(vt.values())
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow(COUNTY_HEADER)
        for (county, office, district, party, candidate), n in sorted(agg.items()):
            w.writerow([county, office, district, party, candidate, n])


def validate(votes):
    tree = etree.parse(os.path.join(XML_DIR, 'state', 'detail.xml'))
    state_data = {}
    for contest in tree.iter('Contest'):
        base, party = parse_office_party(contest.attrib['text'])
        office, district = _parse_office_for_primary(base)
        for choice in contest.iter('Choice'):
            cand = strip_prefix(norm_candidate_name(choice.attrib.get('text', '')),
                                norm_ws(choice.attrib.get('party')))
            for vt in choice.iter('VoteType'):
                name = VOTE_TYPE_MAP.get(norm_ws(vt.attrib['name']))
                if name is None:
                    continue
                for c in vt.iter('County'):
                    state_data[(c.attrib['name'], office, district or '', name, cand)] = int(c.attrib['votes'])
    calc = {}
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        for name, n in vt.items():
            calc[(county, office, district or '', name, candidate)] = \
                calc.get((county, office, district or '', name, candidate), 0) + n
    missing = sorted(set(state_data) - set(calc))
    mism = [k for k in set(state_data) | set(calc)
            if state_data.get(k) != calc.get(k)]
    return len(state_data), mism, missing, state_data


if __name__ == '__main__':
    download()
    votes = collect_results()
    n, mism, missing, state_data = validate(votes)
    # missing keys are acceptable only when the state rollup shows 0
    nonzero_missing = [k for k in missing if state_data[k] != 0]
    print('rows:', len(votes), '| state keys:', n, '| mismatches:', mism)
    print('keys only in state snapshot (must all be 0):', missing)
    if mism or nonzero_missing:
        sys.exit(1)
    write_outputs(votes)
    print('outputs written to', OUT_ROOT)
