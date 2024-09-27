import pandas as pd
import csv

zipLinks = []
links = pd.read_csv('new_links_by_county_2014_runoff.csv')

full_navs = links['full_nav_links'].to_list()

for county in full_navs:
    zipLinks.append(county[:-15] + 'reports/detailxml.zip')

zip_links_2014 = pd.DataFrame()
zip_links_2014['county'] = links.iloc[:,0].to_list()
zip_links_2014['zip_links'] = zipLinks

zip_links_2014.to_csv('zip_links_2014_runoff.csv')
