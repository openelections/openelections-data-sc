import pandas as pd
from selenium import webdriver
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from time import sleep
import csv

year = '2014'

if(year == '2018'):
    counties = pd.read_csv('county_links_2018.csv', header=None)
    # print(counties)

    links = counties.iloc[:,1]
    county_full_links = []
    for link in links:
        county_full_links.append(link + 'Web02.203317/#/')

    zipLinks = []

    driver = webdriver.Chrome()
    for link in links:
        sleep(3)
        driver.get(link + 'Web02.203317/#/')
    # driver.manage().timeouts().pageLoadTimeout(30, TimeUnit.SECONDS);
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, 'clips-cards ')))
        except TimeoutException:
            print('Page timed out after 10 secs.')

            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')
            for l in soup.find_all('a', attrs={'class':'list-download-link'}):
                if(("detailxml.zip" in l.get('href')) and ((link + l.get('href')[3:]) not in zipLinks)):
                    zipLinks.append(link + l.get('href')[3:])



    counties['zips'] = zipLinks
    counties['full_nav_links'] = county_full_links
    counties.to_csv('zip_links_by_county_2018.csv', index=False)

elif(year == '2014'):
    counties = pd.read_csv('county_links_2014_runoff.csv', header=None)
    # print(counties)

    links = counties.iloc[:,1]
    county_full_links = []
    for link in links:
        county_full_links.append('https://www.enr-scvotes.org/SC'+link)

    newLinks = []

    driver = webdriver.Chrome()
    for link in county_full_links:
        sleep(3)
        driver.get(link)
        newLinks.append(driver.current_url)
    # # driver.manage().timeouts().pageLoadTimeout(30, TimeUnit.SECONDS);
        try:
            WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.CLASS_NAME, 'clips-cards ')))
        except TimeoutException:
            print('Page timed out after 10 secs.')



    #         page_source = driver.page_source
    #         soup = BeautifulSoup(page_source, 'lxml')
    #         for l in soup.find_all('a', attrs={'class':'list-download-link'}):
    #             if(("detailxml.zip" in l.get('href')) and ((link + l.get('href')[3:]) not in zipLinks)):
    #                 zipLinks.append(link + l.get('href')[3:])
    #
    #
    # #
    counties['full_nav_links'] = newLinks
    counties['county_pages'] = county_full_links
    counties.to_csv('new_links_by_county_2014_runoff.csv', index=False)
