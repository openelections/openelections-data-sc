"""Update the 2026 SC primary files with certified recount results from the
ENR primary-recount election (https://www.enr-scvotes.org/SC/126666/web.345435).

Replaces precinct rows for every recounted contest in the 20260609 primary
files and validates against the recount state-level snapshot (which only
rolls up the multi-county / district recount — local county recounts are
absent from it and validated by direct parse).

Run:  pipenv run python update_2026_primary_recount.py
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
from build_2026_general import VOTE_TYPE_MAP, VOTE_TYPES, HEADER, COUNTY_HEADER, UA
from build_2026_primary import (_parse_office_for_primary, parse_candidate_primary,
                                norm_candidate_name, strip_prefix, norm_ws, parse_office_party,
                                XML_DIR as PRIMARY_XML_DIR, PRIMARY_URL, DATE as PRIMARY_DATE)

RECOUNT_URL = 'https://www.enr-scvotes.org/SC/126666/web.345435/#/summary'
RECOUNT_STATE_BASE = 'https://results.enr.clarityelections.com/SC/126666/375603'
RECOUNT_DIR = os.environ.get('SC2026_PRIMARY_RECOUNT_XML_DIR', '/tmp/sc2026_primary_recount')
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026')
DATE = PRIMARY_DATE


def download_recount():
    j = clarify.Jurisdiction(url=RECOUNT_URL, level='state')
    urls = [('state', RECOUNT_STATE_BASE + '/reports/detailxml.zip')]
    for sub in j.get_subjurisdictions():
        urls.append((sub.name.replace(' ', '_').lower(), sub.report_url('xml')))
    for name, url in urls:
        d = os.path.join(RECOUNT_DIR, name)
        os.makedirs(d, exist_ok=True)
        if os.path.isfile(os.path.join(d, 'detail.xml')):
            continue
        r = requests.get(url, headers=UA, timeout=120)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(d)
        print('downloaded', name, len(r.content))


def load_recount_votes():
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
            base, party = parse_office_party(norm_ws(result.contest.text))
            office, district = _parse_office_for_primary(base)
            candidate, party_choice = parse_candidate_primary(result.choice)
            party = party or party_choice
            key = (region, result.jurisdiction.name, office, district or '', party, candidate)
            row = votes.setdefault(key, {k: 0 for k in VOTE_TYPES})
            row[vote_type] = int(result.votes or 0)
    return votes


def state_recount_totals():
    tree = etree.parse(os.path.join(RECOUNT_DIR, 'state', 'detail.xml'))
    state_data = {}
    for contest in tree.iter('Contest'):
        base, party = parse_office_party(contest.attrib['text'])
        office, district = _parse_office_for_primary(base)
        for choice in contest.iter('Choice'):
            cand = norm_candidate_name(choice.attrib.get('text', ''))
            for vt in choice.iter('VoteType'):
                name = VOTE_TYPE_MAP.get(norm_ws(vt.attrib['name']))
                if name is None:
                    continue
                for c in vt.iter('County'):
                    state_data[(c.attrib['name'], office, district or '', name, cand)] = int(c.attrib['votes'])
    return state_data


def validate_against_state(votes, state_data):
    calc = {}
    for (county, precinct, office, district, party, candidate), vt in votes.items():
        for name, n in vt.items():
            if n == 0 and (county, office, district, name, candidate) not in state_data:
                continue
            calc[(county, office, district, name, candidate)] = \
                calc.get((county, office, district, name, candidate), 0) + n
    mism = [(k, state_data.get(k), calc.get(k)) for k in state_data if calc.get(k) != state_data[k]]
    return len(state_data), mism


def rewrite_files(votes, recounted_keys):
    """recounted_keys: set of (county, office, district, party). Party is None
    only if the contest text carried none; matched rows always carry a party."""
    counties = os.path.join(OUT_ROOT, 'counties')
    n_rows = 0
    for fname in sorted(os.listdir(counties)):
        if not fname.startswith(DATE + '__sc__primary__'):
            continue  # only the primary files carry these contests
        path = os.path.join(counties, fname)
        with open(path) as f:
            rows = list(csv.reader(f))
        header, body = rows[0], rows[1:]
        new_body, changed = [], False
        for row in body:
            c, p_, o, dt = row[0], row[1], row[2], row[3]
            if (c, o, dt, row[5]) in recounted_keys and (c, p_, o, dt, row[5], row[4]) in votes:
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

    # consolidated statewide precinct file
    path = os.path.join(OUT_ROOT, DATE + '__sc__primary__precinct.csv')
    with open(path) as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    changed = 0
    for i, row in enumerate(body):
        c, p_, o, dt = row[0], row[1], row[2], row[3]
        if (c, o, dt, row[5]) in recounted_keys and (c, p_, o, dt, row[5], row[4]) in votes:
            vt = votes[(c, p_, o, dt, row[5], row[4])]
            vals = [vt[k] for k in VOTE_TYPES]
            body[i] = [c, p_, o, dt, row[4], row[5], str(sum(vals))] + [str(v) for v in vals]
            changed += 1
    with open(path, 'w') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    print(' consolidated rows rewritten:', changed)


def report_deltas(votes, recounted_keys):
    by_key = collections.Counter()
    for (c, p_, o, dt, party, cand), vt in votes.items():
        by_key[(c, o, dt, party, cand)] += sum(vt.values())
    counties = os.path.join(OUT_ROOT, 'counties')
    deltas = []
    for (c, o, dt, party) in sorted(recounted_keys):
        fname = os.path.join(counties, DATE + '__sc__primary__' +
                             c.replace(' ', '_').lower() + '__precinct.csv')
        old = 0
        with open(fname) as f:
            for row in csv.DictReader(f):
                if row['office'] == o and row['district'] == dt and row['party'] == (party or ''):
                    old += int(row['votes'])
        new = sum(v for (cc, oo, dd, pp, cc2), v in by_key.items()
                  if cc == c and oo == o and dd == dt and pp == party)
        if old != new:
            deltas.append((c, o, dt, party, old, new))
    return deltas


if __name__ == '__main__':
    download_recount()
    votes = load_recount_votes()
    state_data = state_recount_totals()
    n, mism = validate_against_state(votes, state_data)
    recounted_keys = {(c, o, dt, party) for (c, p_, o, dt, party, cand) in votes}
    print('recount state keys:', n, 'mismatches:', mism)
    if mism:
        sys.exit(1)
    print('recounted contest-county pairs:', recounted_keys)
    print('deltas (old -> new county totals):')
    for d in report_deltas(votes, recounted_keys):
        print('  ', d)
    rewrite_files(votes, recounted_keys)
