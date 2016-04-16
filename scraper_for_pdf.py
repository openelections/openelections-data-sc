import unicodecsv
import requests

COUNTIES = ['ABBEVILLE','AIKEN','ALLENDALE','ANDERSON','BAMBERG','BARNWELL','BEAUFORT','BERKELEY','CALHOUN','CHARLESTON','CHEROKEE','CHESTER','CHESTERFIELD','CLARENDON','COLLETON','DARLINGTON','DILLON','DORCHESTER','EDGEFIELD','FAIRFIELD','FLORENCE','GEORGETOWN','GREENVILLE','GREENWOOD','HAMPTON','HORRY','JASPER','KERSHAW','LANCASTER','LAURENS','LEE','LEXINGTON','MARION','MARLBORO','MCCORMICK','NEWBERRY','OCONEE','ORANGEBURG','PICKENS','RICHLAND','SALUDA','SPARTANBURG','SUMTER','UNION','WILLIAMSBURG','YORK']
OFFICES = ['GOVERNOR', 'LIEUTENANT GOVERNOR', 'SECRETARY OF STATE', 'STATE TREASURER', 'ATTORNEY GENERAL', 'COMPTROLLER GENERAL', 'STATE SUPERINTENDENT OF EDUCATION', 'ADJUTANT GENERAL','COMMISSIONER OF AGRICULTURE']

def statewide(filename):
    text = open(filename).readlines()
    for line in text:
        if 'South Carolina Election Returns' in line:
            continue
        if 'Official Results' in line:
            continue
        if line.strip() == '':
            continue
        if any(office in line for office in OFFICES):
            office = [office for office in OFFICES if office in line][0]
        if 'COUNTY' in line:
            first_names = []


    newfile = open("test.txt", "w")
    newfile.write(text)
    newfile.close()
    text.close()
