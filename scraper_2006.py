import unicodecsv
import requests
from BeautifulSoup import BeautifulSoup
COUNTIES = ['ABBEVILLE','AIKEN','ALLENDALE','ANDERSON','BAMBERG','BARNWELL','BEAUFORT','BERKELEY','CALHOUN','CHARLESTON','CHEROKEE','CHESTER','CHESTERFIELD','CLARENDON','COLLETON','DARLINGTON','DILLON','DORCHESTER','EDGEFIELD','FAIRFIELD','FLORENCE','GEORGETOWN','GREENVILLE','GREENWOOD','HAMPTON','HORRY','JASPER','KERSHAW','LANCASTER','LAURENS','LEE','LEXINGTON','MARION','MARLBORO','MCCORMICK','NEWBERRY','OCONEE','ORANGEBURG','PICKENS','RICHLAND','SALUDA','SPARTANBURG','SUMTER','UNION','WILLIAMSBURG','YORK']
OFFICES = ['GOVERNOR', 'LIEUTENANT+GOVERNOR', 'SECRETARY+OF+STATE', 'STATE+TREASURER', 'ATTORNEY+GENERAL', 'COMPTROLLER+GENERAL', 'STATE+SUPERINTENDENT+OF+EDUCATION', 'ADJUTANT+GENERAL','COMMISSIONER+OF+AGRICULTURE']

def statewide_2006():
    with open('20061107__sc__general__precinct.csv', 'wb') as csvfile:
        w = unicodecsv.writer(csvfile, encoding='utf-8')
        headers = ['county', 'precinct', 'office', 'district', 'party', 'candidate', 'votes']
        w.writerow(headers)
        for office in OFFICES:
            for county in COUNTIES:
                url = "http://www.state.sc.us/cgi-bin/scsec/r2?race=%s&election=gen06p&county=%s" % (office, county)
                r = requests.get(url)
                soup = BeautifulSoup(r.text)
                table = soup.find('table')
                rows = table.findAll('tr')[1:]
                if county == 'ABBEVILLE':
                    first_names = [x.text for x in rows[0].findAll('td') if x.text != '']
                    last_names = [x.text for x in rows[1].findAll('td') if x.text != '']
                    candidates = [' '.join(x) for x in zip(first_names, last_names)]
                    if 'WRITE-IN' in last_names:
                        candidates.append('WRITE-IN')
                    parties = [x.text for x in rows[2].findAll('td') if x.text != ''][2:]
                for row in rows[3:]:
                    for candidate in candidates:
                        if parties[candidates.index(candidate)] == 'WRITE-IN':
                            party = None
                        else:
                            party = parties[candidates.index(candidate)]
                        w.writerow([row.findAll('td')[0].text, row.findAll('td')[1].text, office.replace('+',' '), None, party, candidate, row.findAll('td')[candidates.index(candidate)+2].text])

def statewide_2006_county():
    with open('20061107__sc__general__county.csv', 'wb') as csvfile:
        w = unicodecsv.writer(csvfile, encoding='utf-8')
        headers = ['county', 'office', 'district', 'party', 'candidate', 'votes']
        w.writerow(headers)
        url = "http://www.state.sc.us/cgi-bin/scsec/r1"
        for office in OFFICES:
            r = requests.post(url, data = {'race': office, 'election':'gen06p'})
            soup = BeautifulSoup(r.text)
            table = soup.find('table')
            rows = table.findAll('tr')[1:]
            first_names = [x.text for x in rows[0].findAll('td') if x.text != '']
            last_names = [x.text for x in rows[1].findAll('td') if x.text != '']
            candidates = [' '.join(x) for x in zip(first_names, last_names)]
            if 'WRITE-IN' in last_names:
                candidates.append('WRITE-IN')
            parties = [x.text for x in rows[2].findAll('td') if x.text != ''][2:]
            for row in rows[3:]:
                for candidate in candidates:
                    if parties[candidates.index(candidate)] == 'WRITE-IN':
                        party = None
                    else:
                        party = parties[candidates.index(candidate)]
                    w.writerow([row.findAll('td')[0].text, office.replace('+',' '), None, party, candidate, row.findAll('td')[candidates.index(candidate)+2].text])
