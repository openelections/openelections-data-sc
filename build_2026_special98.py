"""Build the State House District 98 special election (January 9, 2026)
county and precinct files from the Clarity/ENR site, mirroring the 2026
general-election pipeline.

Source: https://www.enr-scvotes.org/SC/125869/web.345435 (the election's
final snapshot, published for its recount; single county: Dorchester).
XMLs live in $SC2026_SPECIAL98_XML_DIR (default /tmp/sc2026_special98).

Outputs:
  2026/counties/20260109__sc__special__general__<county>__precinct.csv
  2026/20260109__sc__special__general__precinct.csv
  2026/20260109__sc__special__general__county.csv

Run:  pipenv run python build_2026_special98.py
"""
import sys
import os
import csv
import requests
import zipfile
import io
import collections
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clarify
from build_2026_general import (norm_ws, parse_candidate, strip_prefix, parse_office,
                               norm_slash, VOTE_TYPE_MAP, VOTE_TYPES, HEADER, COUNTY_HEADER, UA)

SPECIAL_URL = 'https://www.enr-scvotes.org/SC/125869/web.345435/#/summary'
REPORTS = [('state', 'https://results.enr.clarityelections.com/SC/125869/367712/reports/detailxml.zip'),
           ('dorchester', 'https://results.enr.clarityelections.com/SC/Dorchester/125887/367710/reports/detailxml.zip')]
XML_DIR = os.environ.get('SC2026_SPECIAL98_XML_DIR', '/tmp/sc2026_special98')
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026')
DATE = '20260109'
ELECTION_TAG = 'special__general'


def download():
    for name, url in REPORTS:
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
            office, district = parse_office(norm_slash(norm_ws(result.contest.text)))
            candidate, party = parse_candidate(result.choice)
            key = (region, result.jurisdiction.name, office, district, party, candidate)
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

    # consolidated
    fname = os.path.join(OUT_ROOT, DATE + '__sc__' + ELECTION_TAG + '__precinct.csv')
    with open(fname, 'w') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for key in sorted(votes.keys(), key=lambda k: (k[0], k[1], k[-1])):
            county, precinct, office, district, party, candidate = key
            vals = rowlist(votes[key])
            w.writerow([county, precinct, office, district, candidate, party or '', sum(vals)] + vals)
        # Ballots Cast rows from VoterTurnout
        turnouts = []
        for d in sorted(os.listdir(XML_DIR)):
            xml_path = os.path.join(XML_DIR, d, 'detail.xml')
            if not os.path.isfile(xml_path) or d == 'state':
                continue
            tree = etree.parse(xml_path)
            region = tree.find('.//Region').text.strip()
            for p_el in tree.findall('.//VoterTurnout/Precincts/Precinct'):
                turnouts.append((region, p_el.attrib['name'], int(p_el.attrib['ballotsCast'])))
        for county, precinct, bc in sorted(turnouts):
            w.writerow([county, precinct, 'Ballots Cast', '', '', '', bc] + [0] * 6)

    # county-level
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
        office, district = parse_office(norm_slash(norm_ws(contest.attrib['text'])))
        for choice in contest.iter('Choice'):
            cand = strip_prefix(norm_slash(norm_ws(choice.attrib.get('text', ''))),
                                choice.attrib.get('party'))
            for vt in choice.iter('VoteType'):
                name = VOTE_TYPE_MAP.get(norm_ws(vt.attrib['name']))
                if name is None:
                    continue
                for c in vt.iter('County'):
                    state_data[(c.attrib['name'], office, district, name, cand)] = int(c.attrib['votes'])
    calc = {}
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        for name, n in vt.items():
            calc[(county, office, district, name, candidate)] = \
                calc.get((county, office, district, name, candidate), 0) + n
    mism = [k for k in set(state_data) | set(calc)
            if state_data.get(k) != calc.get(k)]
    return len(state_data), mism


if __name__ == '__main__':
    download()
    votes = collect_results()
    n, mism = validate(votes)
    print('rows:', len(votes), '| state keys:', n, '| mismatches:', mism)
    if mism:
        sys.exit(1)
    write_outputs(votes)
    print('outputs written to', OUT_ROOT)
    total = sum(sum(v.values()) for v in votes.values())
    print('total contest votes:', total, '(choice totals: Ford 1728, Satani 1707, Write-In 5)')
