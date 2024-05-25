from io import BytesIO
from zipfile import ZipFile
from urllib.request import urlopen
import requests
import pandas as pd
import ssl
import xlrd
import clarify
import pdb
import csv
import numpy as np

ssl._create_default_https_context = ssl._create_unverified_context
# or: requests.get(url).content
#

def download_county_files(url, filename):
    no_xml = []
    j = clarify.Jurisdiction(url=url, level="state")
    subs = j.get_subjurisdictions()
    pdb.set_trace()
    for sub in subs:
        try:
            r = requests.get(sub.report_url('xml'), stream=True)
            z = zipfile.ZipFile(BytesIO(r.content))
            z.extractall()
            precinct_results(sub.name.replace(' ','_').lower(),filename)
        except:
            no_xml.append(sub.name)

    print(no_xml)

def download_county_files_new(state, json_url, filename):
    no_xml = []
    r = requests.get(json_url)
    counties = r.json()['settings']['electiondetails']['participatingcounties']
    for c in counties:
        name, first_id, second_id, date, fill = c.split('|')
        url = 'https://results.enr.clarityelections.com//' + state + '/' + name + '/' + first_id + '/' + second_id + '/reports/detailxml.zip'
        try:
            r = requests.get(url, stream=True)
            z = zipfile.ZipFile(BytesIO(r.content))
            z.extractall()
            precinct_results(name.replace(' ','_').lower(),filename)
        except:
            no_xml.append(name)
    print(no_xml)

def precinct_results(county_name, filename):
    pdb.set_trace()
    f = filename + '__' + county_name + '__precinct.csv'
    p = clarify.Parser()
    p.parse("detail.xml")
    results = []
    vote_types = []
    for result in [x for x in p.results if not 'Number of Precincts' in x.vote_type]:
        vote_types.append(result.vote_type)
        if result.choice is None:
            continue
        candidate = result.choice.text
        office, district = parse_office(result.contest.text)
        party = result.choice.party
        if '(' in candidate and party is None:
            if '(I)' in candidate:
                if '(I)(I)' in candidate:
                    candidate = candidate.split('(I)')[0]
                    party = 'I'
                else:
                    candidate, party = candidate.split('(I)')
            else:
                candidate, party = candidate.split('(', 1)
                candidate = candidate.strip()
            party = party.replace(')','').strip()
        county = p.region
        if result.jurisdiction:
            precinct = result.jurisdiction.name
        else:
            precinct = None
        if precinct == None:
            continue
        r = [x for x in results if x['county'] == county and x['precinct'] == precinct and x['office'] == office and x['district'] == district and x['party'] == party and x['candidate'] == candidate]
        if r:
             r[0][result.vote_type] = result.votes
        else:
            results.append({ 'county': county, 'precinct': precinct, 'office': office, 'district': district, 'party': party, 'candidate': candidate, result.vote_type: result.votes})

    vote_types = list(set(vote_types))
    if 'overVotes' in vote_types:
        vote_types.remove('overVotes')
    if 'underVotes' in vote_types:
        vote_types.remove('underVotes')
    if 'regVotersCounty' in vote_types:
        vote_types.remove('regVotersCounty')
    with open(f, "wt") as csvfile:
        w = csv.writer(csvfile)
        headers = ['county', 'precinct', 'office', 'district', 'party', 'candidate', 'votes'] + [x.replace(' ','_').lower() for x in vote_types]
        w.writerow(headers)
        for row in results:
            if 'Republican' in row['office']:
                row['party'] = 'REP'
            elif 'Democrat' in row['office']:
                row['party'] = 'DEM'
            total_votes = sum([row[k] for k in vote_types if row[k]])
            w.writerow([row['county'], row['precinct'], row['office'], row['district'], row['party'], row['candidate'], total_votes] + [row[k] for k in vote_types])



# def precinct_results(county_name, filename):
#     f = filename + '__' + county_name + '__precinct.csv'
#     p = clarify.Parser()
#     p.parse("detail.xml")
#     results = []
#     vote_types = []
#     for result in [x for x in p.results if not 'Number of Precincts' in x.vote_type]:
#         vote_types.append(result.vote_type)
#         if result.choice is None:
#             continue
#         candidate = result.choice.text
#         office, district = parse_office(result.contest.text)
#         party = result.choice.party
#         if '(' in candidate and party is None:
#             if '(I)' in candidate:
#                 if '(I)(I)' in candidate:
#                     candidate = candidate.split('(I)')[0]
#                     party = 'I'
#                 else:
#                     candidate, party = candidate.split('(I)')
#             else:
#                 candidate, party = candidate.split('(', 1)
#                 candidate = candidate.strip()
#             party = party.replace(')','').strip()
#         county = p.region
#         if result.jurisdiction:
#             precinct = result.jurisdiction.name
#         else:
#             precinct = None
#         if precinct == None:
#             continue
#         r = [x for x in results if x['county'] == county and x['precinct'] == precinct and x['office'] == office and x['district'] == district and x['party'] == party and x['candidate'] == candidate]
#         if r:
#              r[0][result.vote_type] = result.votes
#         else:
#             results.append({ 'county': county, 'precinct': precinct, 'office': office, 'district': district, 'party': party, 'candidate': candidate, result.vote_type: result.votes})
#
#     vote_types = list(set(vote_types))
#     if 'overVotes' in vote_types:
#         vote_types.remove('overVotes')
#     if 'underVotes' in vote_types:
#         vote_types.remove('underVotes')
#     if 'regVotersCounty' in vote_types:
#         vote_types.remove('regVotersCounty')
#     with open(f, "wt") as csvfile:
#         w = csv.writer(csvfile)
#         headers = ['county', 'precinct', 'office', 'district', 'party', 'candidate', 'votes'] + [x.replace(' ','_').lower() for x in vote_types]
#         w.writerow(headers)
#         for row in results:
#             if 'Republican' in row['office']:
#                 row['party'] = 'REP'
#             elif 'Democrat' in row['office']:
#                 row['party'] = 'DEM'
#             total_votes = sum([row[k] for k in vote_types if row[k]])
#             w.writerow([row['county'], row['precinct'], row['office'], row['district'], row['party'], row['candidate'], total_votes] + [row[k] for k in vote_types])


def parse_office(office_text):
    if ' - ' in office_text:
        office = office_text.split('-')[0]
    else:
        office = office_text.split(',')[0]
    if ', District' in office_text:
        district = office_text.split(', District')[1].split(' - ')[0].strip()
    elif 'United States Senator' in office_text:
        office = 'United States Senator'
        district = None
    elif ',' in office_text:
        district = office_text.split(',')[1]
    else:
        district = None
    return [office.strip(), district]

def parse_party(office_text):
    if '- REP' in office_text:
        party = 'REP'
    elif '- DEM' in office_text:
        party = 'DEM'
    else:
        party = None
    return party



# url = 'https://www.cftc.gov/files/dea/history/fut_disagg_xls_2020.zip'
url = 'https://www.enr-scvotes.org/SC/Abbeville/103403/253127/reports/detailxml.zip'



results = []
vote_types = []
def read_in_counties(url, county_name, results = results, vote_types = vote_types):
    r = requests.get(url, stream=True)
    z = ZipFile(BytesIO(r.content))
    z.extractall()
    read_results(county_name, results, vote_types)




# read_in_counties(url=url, filename='abbeville_2020')
# download_county_files(url=url, filename="abbeville_2020")

# def read_results(filename):
#     county_name = 'abbeville'
#     f = filename + '__' + county_name + '__precinct.csv'
#     p = clarify.Parser()
#     p.parse("detail.xml")
#     for result in [x for x in p.results if not 'Number of Precincts' in x.vote_type]:
#         vote_types.append(result.vote_type)
#         if result.choice is None:
#             continue
#         candidate = result.choice.text
#         office, district = parse_office(result.contest.text)
#         party = result.choice.party
#         if '(' in candidate and party is None:
#             if '(I)' in candidate:
#                 if '(I)(I)' in candidate:
#                     candidate = candidate.split('(I)')[0]
#                     party = 'I'
#                 else:
#                     candidate, party = candidate.split('(I)')
#             else:
#                 candidate, party = candidate.split('(', 1)
#                 candidate = candidate.strip()
#             party = party.replace(')','').strip()
#         county = p.region
#         if result.jurisdiction:
#             precinct = result.jurisdiction.name
#         else:
#             precinct = None
#         if precinct == None:
#             continue
#         r = [x for x in results if x['county'] == county and x['precinct'] == precinct and x['office'] == office and x['district'] == district and x['party'] == party and x['candidate'] == candidate]
#         if r:
#              r[0][result.vote_type] = result.votes
#         else:
#             results.append({ 'county': county, 'precinct': precinct, 'office': office, 'district': district, 'party': party, 'candidate': candidate, result.vote_type: result.votes})
#
#     vote_types = list(set(vote_types))
#     if 'overVotes' in vote_types:
#         vote_types.remove('overVotes')
#     if 'underVotes' in vote_types:
#         vote_types.remove('underVotes')
#     if 'regVotersCounty' in vote_types:
#         vote_types.remove('regVotersCounty')
#     with open(f, "wt") as csvfile:
#         w = csv.writer(csvfile)
#         headers = ['year','county', 'precinct', 'office', 'district', 'party', 'candidate', 'votes'] + [x.replace(' ','_').lower() for x in vote_types]
#         w.writerow(headers)
#         for row in results:
#             if 'Republican' in row['office']:
#                 row['party'] = 'REP'
#             elif 'Democrat' in row['office']:
#                 row['party'] = 'DEM'
#             total_votes = sum([row[k] for k in vote_types if row[k]])
#             w.writerow(['2020', row['county'], row['precinct'], row['office'], row['district'], row['party'], row['candidate'], total_votes] + [row[k] for k in vote_types])

def read_results(county_name, results, vote_types):
    p = clarify.Parser()
    p.parse("detail.xml")
    for result in [x for x in p.results if not 'Number of Precincts' in x.vote_type]:
        vote_types.append(result.vote_type)
        if result.choice is None:
            continue
        candidate = result.choice.text
        office, district = parse_office(result.contest.text)
        party = result.choice.party
        if '(' in candidate and party is None:
            if '(I)' in candidate:
                if '(I)(I)' in candidate:
                    candidate = candidate.split('(I)')[0]
                    party = 'I'
                else:
                    candidate, party = candidate.split('(I)')
            else:
                candidate, party = candidate.split('(', 1)
                candidate = candidate.strip()
            party = party.replace(')','').strip()
        county = p.region
        if result.jurisdiction:
            precinct = result.jurisdiction.name
        else:
            precinct = None
        if precinct == None:
            continue
        r = [x for x in results if x['county'] == county and x['precinct'] == precinct and x['office'] == office and x['district'] == district and x['party'] == party and x['candidate'] == candidate]
        if r:
             r[0][result.vote_type] = result.votes
        else:
            results.append({ 'year': 2020,'county': county, 'precinct': precinct, 'office': office, 'district': district, 'party': party, 'candidate': candidate, result.vote_type: result.votes})


counties_2016 = pd.read_csv('zip_links_2014_runoff.csv')
county_list = counties_2016['county'].to_list()

for county in county_list:
    print(county)
    read_in_counties(str(counties_2016[counties_2016['county'] == county]['zip_links'].to_list()[0]), county)

vote_types = list(set(vote_types))
if 'overVotes' in vote_types:
    vote_types.remove('overVotes')
if 'underVotes' in vote_types:
    vote_types.remove('underVotes')
if 'regVotersCounty' in vote_types:
    vote_types.remove('regVotersCounty')
if 'Provionsal' in vote_types:
    vote_types.remove('Provionsal')
    # vote_types.append('Provisional')




f = '2014_runoff.csv'
with open(f, "wt") as csvfile:
    w = csv.writer(csvfile)
    headers = ['county', 'precinct', 'office', 'district', 'party', 'candidate', 'votes'] + [x.replace(' ','_').lower() for x in vote_types]
    w.writerow(headers)
    for row in results:
        if 'Republican' in row['office']:
            row['party'] = 'REP'
        elif 'Democrat' in row['office']:
            row['party'] = 'DEM'
        total_votes = 0
        vote_type_list = []
        for k in vote_types:
            if(k in row):
                total_votes+= row[k]
                vote_type_list.append(row[k])

        # total_votes = sum([row[k] for k in vote_types if row[k]])
        w.writerow([row['county'], row['precinct'], row['office'], row['district'], row['party'], row['candidate'], total_votes] + vote_type_list)


# for (county in counties_2020)
#
# read_in_counties(url=url, filename="allendale")

#OS.path
#maybe save as csv?
