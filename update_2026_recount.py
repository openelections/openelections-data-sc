"""Update the 2026 SC general election files with certified recount results
from the ENR recount election (https://www.enr-scvotes.org/SC/127592/web.345435).

Replaces precinct rows for every recounted contest in:
  2026/counties/...__precinct.csv, 20261103__sc__general__precinct.csv,
  20261103__sc__general__county.csv
and validates against the recount state-level snapshot. Turnout (Ballots Cast)
rows are left untouched: the recount export reports re-tabulation ballot
counts, not new turnout.

Run:  pipenv run python update_2026_recount.py
"""
import sys
import os
import csv
import collections
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clarify
import requests
import zipfile
import io
from build_2026_general import (parse_office, parse_candidate, norm_ws, norm_slash,
                                VOTE_TYPE_MAP, VOTE_TYPES, HEADER, COUNTY_HEADER,
                                strip_prefix, download as _download_generic, UA)

RECOUNT_URL = 'https://www.enr-scvotes.org/SC/127592/web.345435/#/summary'
RECOUNT_STATE_BASE = 'https://results.enr.clarityelections.com/SC/127592/386752'
RECOUNT_DIR = os.environ.get('SC2026_RECOUNT_XML_DIR', '/tmp/sc2026_recount')
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026')
DATE = '20261103'

# Offices eligible for the county-level summary file.
COUNTY_CSV_OFFICES = {'U.S. House', 'State House', 'State Senate', 'Solicitor',
                      'Governor and Lieutenant Governor', 'Attorney General',
                      'Secretary of State', 'State Treasurer', 'Comptroller General',
                      'State Superintendent of Education', 'Commissioner of Agriculture'}


def download_recount():
    j = clarify.Jurisdiction(url=RECOUNT_URL, level='state')
    urls = [('state', RECOUNT_STATE_BASE + '/reports/detailxml.zip')]
    for sub in j.get_subjurisdictions():
        urls.append((sub.name.replace(' ', '_').lower(), sub.report_url('xml')))
    for name, url in urls:
        d = os.path.join(RECOUNT_DIR, name)
        os.makedirs(d, exist_ok=True)
        target = os.path.join(d, 'detail.xml')
        if os.path.isfile(target):
            continue
        r = requests.get(url, headers=UA, timeout=120)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(d)
        print('downloaded', name, len(r.content))


def load_recount_votes():
    """Parse recount detail.xmls into rows keyed like the general files.
    County names come from each file's <Region>."""
    votes = {}
    for d in sorted(os.listdir(RECOUNT_DIR)):
        path = os.path.join(RECOUNT_DIR, d, 'detail.xml')
        if not os.path.isfile(path) or d == 'state':
            continue
        tree = etree.parse(path)
        region = tree.find('.//Region').text.strip()
        assert region.lower() == d.replace('_', ' ').lower(), (region, d)
        p = clarify.Parser()
        p.parse(path)
        for result in p.results:
            if result.choice is None or result.jurisdiction is None:
                continue
            vote_type = VOTE_TYPE_MAP.get(result.vote_type)
            if vote_type is None:
                continue
            office, district = parse_office(norm_slash(norm_ws(result.contest.text)))
            candidate, party = parse_candidate(result.choice)
            key = (region, result.jurisdiction.name, office, district, party, candidate)
            row = votes.setdefault(key, {k: 0 for k in VOTE_TYPES})
            row[vote_type] = int(result.votes or 0)
    return votes


def state_recount_totals():
    """(county, office, district, vote_type, candidate) -> votes from the
    recount state-level snapshot. Covers only the aggregated statewide recounts;
    the single-county local recounts are not in the state rollup."""
    tree = etree.parse(os.path.join(RECOUNT_DIR, 'state', 'detail.xml'))
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
    return state_data


def validate_against_state(votes, state_data):
    calc = {}
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        for name, n in vt.items():
            if n == 0 and (county, office, district, name, candidate) not in state_data:
                continue
            calc[(county, office, district, name, candidate)] = \
                calc.get((county, office, district, name, candidate), 0) + n
    mism = [(k, state_data.get(k), calc.get(k)) for k in state_data
            if calc.get(k) != state_data[k]]
    return len(state_data), mism


def rewrite_files(votes, recounted_keys, state_data):
    """recounted_keys: set of (county, office, district) present in the recount."""
    # Per-county files: replace matching rows (candidate/party/precinct keys).
    counties = os.path.join(OUT_ROOT, 'counties')
    n_rows = 0
    for fname in sorted(os.listdir(counties)):
        path = os.path.join(counties, fname)
        with open(path) as f:
            rows = list(csv.reader(f))
        header, body = rows[0], rows[1:]
        new_body, changed = [], False
        for row in body:
            c, p_, o, dt = row[0], row[1], row[2], row[3]
            if (c, o, dt) in recounted_keys and (c, p_, o, dt, row[5], row[4]) in votes:
                vt = votes[(c, p_, o, dt, row[5], row[4])]
                vals = [vt[k] for k in VOTE_TYPES]
                new_row = [c, p_, o, dt, row[4], row[5], str(sum(vals))] + [str(v) for v in vals]
                if new_row != row:
                    changed = True
                    n_rows += 1
                new_body.append(new_row)
            else:
                new_body.append(row)
        if changed:
            with open(path, 'w') as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(new_body)
            print('updated county file:', fname)
    print(' precinct rows rewritten:', n_rows)

    # Consolidated statewide precinct file.
    path = os.path.join(OUT_ROOT, DATE + '__sc__general__precinct.csv')
    with open(path) as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    changed = 0
    for i, row in enumerate(body):
        c, p_, o, dt = row[0], row[1], row[2], row[3]
        if (c, o, dt) in recounted_keys and (c, p_, o, dt, row[5], row[4]) in votes:
            vt = votes[(c, p_, o, dt, row[5], row[4])]
            vals = [vt[k] for k in VOTE_TYPES]
            body[i] = [c, p_, o, dt, row[4], row[5], str(sum(vals))] + [str(v) for v in vals]
            changed += 1
    with open(path, 'w') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    print(' consolidated rows rewritten:', changed)

    # County-level summary (state/federal offices only).
    path = os.path.join(OUT_ROOT, DATE + '__sc__general__county.csv')
    with open(path) as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    agg = collections.defaultdict(int)
    for (c, p_, o, dt, party, cand), vt in votes.items():
        if (c, o, dt) in recounted_keys and o in COUNTY_CSV_OFFICES:
            agg[(c, o, dt, party, cand)] += sum(vt.values())
    updates = 0
    for i, row in enumerate(body):
        k = tuple(row[:5])
        if k in agg and row[5] != str(agg[k]):
            print(' county.csv updated:', k, row[5], '->', agg[k])
            body[i] = list(row[:5]) + [str(agg[k])]
            updates += 1
    with open(path, 'w') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    print(' county.csv rows updated:', updates)


def report_deltas(votes, recounted_keys):
    """County-total changes from the recount, for the log."""
    by_key = collections.Counter()
    for (c, p_, o, dt, party, cand), vt in votes.items():
        by_key[(c, o, dt)] += sum(vt.values())
    deltas = []
    counties = os.path.join(OUT_ROOT, 'counties')
    for (c, o, dt) in sorted(recounted_keys):
        fname = os.path.join(counties, DATE + '__sc__general__' +
                             c.replace(' ', '_').lower() + '__precinct.csv')
        old = 0
        with open(fname) as f:
            for row in csv.DictReader(f):
                if row['office'] == o and row['district'] == dt:
                    old += int(row['votes'])
        if old != by_key[(c, o, dt)]:
            deltas.append((c, o, dt, old, by_key[(c, o, dt)]))
    return deltas


if __name__ == '__main__':
    download_recount()
    votes = load_recount_votes()
    state_data = state_recount_totals()
    n, mism = validate_against_state(votes, state_data)
    recounted_keys = {(c, o, dt) for (c, p_, o, dt, party, cand) in votes}
    print('recount state keys:', n, 'mismatches (should all be absent local contests):',
          [(k, o, dt) for k, o, dt in [(k[0], k[1], k[2]) for k, _, _ in mism]][:5])
    if any(k[1] in COUNTY_CSV_OFFICES for k, _, _ in mism):
        print('UNEXPECTED mismatches on recounted statewide contests:', mism)
        sys.exit(1)
    print('recounted contest-county pairs:', recounted_keys)
    print('deltas (old -> new county totals):')
    for d in report_deltas(votes, recounted_keys):
        print('  ', d)
    rewrite_files(votes, recounted_keys, state_data)
