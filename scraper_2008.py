import unicodecsv
import requests
from BeautifulSoup import BeautifulSoup
COUNTIES = ['ABBEVILLE','AIKEN','ALLENDALE','ANDERSON','BAMBERG','BARNWELL','BEAUFORT','BERKELEY','CALHOUN','CHARLESTON','CHEROKEE','CHESTER','CHESTERFIELD','CLARENDON','COLLETON','DARLINGTON','DILLON','DORCHESTER','EDGEFIELD','FAIRFIELD','FLORENCE','GEORGETOWN','GREENVILLE','GREENWOOD','HAMPTON','HORRY','JASPER','KERSHAW','LANCASTER','LAURENS','LEE','LEXINGTON','MARION','MARLBORO','MCCORMICK','NEWBERRY','OCONEE','ORANGEBURG','PICKENS','RICHLAND','SALUDA','SPARTANBURG','SUMTER','UNION','WILLIAMSBURG','YORK']

def pres_primary_dem_precinct():
    with open('20080126__sc__democratic__primary__president__precinct.csv', 'wb') as csvfile:
        w = unicodecsv.writer(csvfile, encoding='utf-8')
        for county in COUNTIES:
            url = "http://www.state.sc.us/cgi-bin/scsec/r208dpf?race=PRESIDENT&election=pri08dpf&county=%s&pr=dp" % county
            r = requests.get(url)
            soup = BeautifulSoup(r.text)
            table = soup.find('table')
            rows = table.findAll('tr')[1:]
            if county == 'ABBEVILLE':
                first_names = [x.text for x in rows[0].findAll('td') if x.text != '']
                last_names = [x.text for x in rows[1].findAll('td') if x.text != ''][2:]
                candidates = [' '.join(x) for x in zip(first_names, last_names)]
                headers = ['county', 'precinct', 'office', 'district', 'party', 'candidate', 'votes']
                w.writerow(headers)
            for row in rows[2:]:
                for candidate in candidates:
                    w.writerow([row.findAll('td')[0].text, row.findAll('td')[1].text, 'President', None, 'DEM', candidate, row.findAll('td')[candidates.index(candidate)+2].text])

def pres_primary_dem_county():
    with open('20080126__sc__democratic__primary__president__county.csv', 'wb') as csvfile:
        w = unicodecsv.writer(csvfile, encoding='utf-8')
        url = "http://www.state.sc.us/cgi-bin/scsec/r108dpf"
        r = requests.post(url, data = {'race':'PRESIDENT', 'election':'pri08dpf', 'prr':'dp'})
        soup = BeautifulSoup(r.text)
        table = soup.find('table')
        rows = table.findAll('tr')[1:]
        first_names = [x.text for x in rows[0].findAll('td') if x.text != '']
        last_names = [x.text for x in rows[1].findAll('td') if x.text != ''][2:]
        candidates = [' '.join(x) for x in zip(first_names, last_names)]
        headers = ['county', 'office', 'district', 'party', 'candidate', 'votes']
        w.writerow(headers)
        for row in rows[2:]:
            for candidate in candidates:
                w.writerow([row.findAll('td')[0].text, 'President', None, 'DEM', candidate, row.findAll('td')[candidates.index(candidate)+2].text])
