from selenium import webdriver
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from time import sleep
import csv
import pdb

# elections = {}
# elections['2020'] =

year = '2014'

if(year == '2018'):
    driver = webdriver.Chrome()
    sleep(2)
    driver.get('https://www.enr-scvotes.org/SC/75708/Web02-state.203322/#/')
    # driver.manage().timeouts().pageLoadTimeout(30, TimeUnit.SECONDS);
    try:
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'clips-cards ')))
    except TimeoutException:
        print('Page timed out after 10 secs.')

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'lxml')
    counties = {}
    for link in soup.find_all('a',  attrs={'class':'submenu-map-county01 ng-binding'}):
        counties[link.text] = link.get('href')

    with open('county_links_2018.csv', 'w') as f:
        for key in counties.keys():
            f.write("%s,%s\n"%(key,counties[key]))

elif(year=='2014'):
        driver = webdriver.Chrome()
        sleep(2)
        driver.get('https://www.enr-scvotes.org/SC/52366/135097/en/select-county.html')
        # driver.manage().timeouts().pageLoadTimeout(30, TimeUnit.SECONDS);
        try:
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'clips-cards ')))
        except TimeoutException:
            print('Page timed out after 10 secs.')

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'lxml')
        counties = {}
        for list in soup.find_all('li'):
             for link in list.find_all('a'):
                 counties[link['id']] = link['value']

        with open('county_links_2014_runoff.csv', 'w') as f:
            for key in counties.keys():
                f.write("%s,%s\n"%(key,counties[key]))




                # counties[link.id] = link.value
                # pdb.set_trace()
        #     counties[link.text] = link.get('href')

        # with open('county_links_2014.csv', 'w') as f:
        #     for key in counties.keys():
        #         f.write("%s,%s\n"%(key,counties[key]))
