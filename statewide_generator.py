import os
import glob
import csv

year = '2022'
election = '20221108'
path = election+'*precinct.csv'
output_file = election+'__sc__general__precinct.csv'

def generate_headers(year, path):
    os.chdir(year)
    os.chdir('counties')
    vote_headers = []
    for fname in glob.glob(path):
        print(fname)
        with open(fname, "r") as csvfile:
            reader = csv.reader(csvfile)
            headers = next(reader)
            print(set(list(h for h in headers if h not in ['county','precinct', 'office', 'district', 'candidate', 'party'])))
            #vote_headers.append(h for h in headers if h not in ['county','precinct', 'office', 'district', 'candidate', 'party'])
#    with open('vote_headers.csv', "w") as csv_outfile:
#        outfile = csv.writer(csv_outfile)
#        outfile.writerows(vote_headers)

def generate_offices(year, path):
    os.chdir(year)
    offices = []
    for fname in glob.glob(path):
        with open(fname, "r") as csvfile:
            print(fname)
            reader = csv.DictReader(csvfile)
            for row in reader:
                if not row['office'] in offices:
                    offices.append(row['office'])
    with open('offices.csv', "w") as csv_outfile:
        outfile = csv.writer(csv_outfile)
        outfile.writerows(offices)

def generate_consolidated_file(year, path, output_file):
    results = []
    os.chdir(year)
    os.chdir('counties')
    for fname in glob.glob(path):
        with open(fname, "r") as csvfile:
            print(fname)
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['office'].strip() in ['STRAIGHT PARTY', 'President', 'Governor and Lieutenant Governor', 'Secretary of State', 'Comptroller General', 'State Auditor', 'State Treasurer', 'State Superintendent of Education', 'Commissioner of Agriculture', 'Attorney General', 'U.S. House', 'State Senate', 'State House', 'U.S. Senate', 'House of Delegates', 'State Representative', 'Registered Voters', 'Ballots Cast']:
                    results.append([row['county'], row['precinct'], row['office'], row['district'], row['candidate'], row['party'], row['votes'], row['early_voting'], row['failsafe_provisional'], row['provisional'], row['failsafe'], row['absentee_by_mail'], row['election_day']])
    os.chdir('..')
    os.chdir('..')
    with open(output_file, "w") as csv_outfile:
        outfile = csv.writer(csv_outfile)
        outfile.writerow(['county','precinct', 'office', 'district', 'candidate', 'party', 'votes', 'early_voting', 'failsafe_provisional', 'provisional', 'failsafe', 'absentee_by_mail', 'election_day'])
        outfile.writerows(results)
