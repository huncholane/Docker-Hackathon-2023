
import time
from browsermobproxy import Server
from selenium import webdriver
from pathlib import Path
from .url_utils import urlparse_json, generate_openapi_spec, har_entry_parse
import json
import requests
import os

class NFLClient():
    """
    ## Manages access to the internal nfl.com api
    
    ### Global Variables
    * `BMP_PATH` - Path to browsermob-proxy
    * `AUTH_PATH` - Path to auth file
    * `AUTH_ENDPOINT` - Endpoint used to get auth token
    * `API_ROOT` - Root for nfl.com api endpoints
    * `HAR_DIR` - Storage directory for har files
    * `URL_JSON_PATH` - Path for json list of found api endpoints
    * `OPENAPI_PATH` - Path for openapi yaml
    * `TOKEN_EXPIRE_RATE` - How many seconds to download a new auth token
    * `TOKEN_AUTH_TIMEOUT` - Timeout when searching har file for Authorization

    ### Class Variables
    * `har` - The current har in json
    * `har_path` - Where to store the current har
    * `server` - The browsermob server
    * `proxy` - The browsermob proxy
    * `driver` - The selenium driver
    * `auth_token` - The current auth token
    * `last_auth_download_time` - When the current auth token was downloaded
    * `headers` - Headers sent through requests

    ### Notes
    * HAR stands for HTTP Access Requests. This is like the network tab on Chrome inspector.
    """
    BMP_PATH = os.path.abspath('browsermob-proxy-2.1.4/bin/browsermob-proxy.bat')
    AUTH_PATH = Path('auth.json')
    AUTH_ENDPOINT = 'https://nfl.com/scores'
    API_ROOT = 'https://api.nfl.com'
    HAR_DIR = Path('nfl_client_data/har_files')
    URL_JSON_PATH = Path('nfl_client_data/urls.json')
    OPENAPI_PATH = Path('nfl_client_data/openapi.yaml')
    TOKEN_EXPIRE_RATE = 60*60
    TOKEN_AUTH_TIMEOUT = 10

    # Har download variables
    har = {}
    har_path = None
    server = None
    proxy = None
    driver = None

    # Auth variables
    auth_token = None
    last_auth_download_time = 0
    headers = {}

    def __init__(self, headless=True):
        os.makedirs(self.HAR_DIR, exist_ok=True)
        self.headless = headless

    def load_auth_token(self, store_har=False):
        """Loads the auth token into the client."""
        if os.path.exists(self.AUTH_PATH):
            with open(self.AUTH_PATH, 'r') as f:
                auth_json = json.load(f)
            self.auth_token = auth_json['token']
            self.last_auth_download_time = auth_json['time']
        if self.last_auth_download_time < time.time()-self.TOKEN_EXPIRE_RATE or not self.auth_token:
            self.download_auth_token(store_har=store_har)
        self.headers={
            'Authorization': self.auth_token
        }

    def prep_proxy(self, endpoint=None):
        """Prepares the driver and proxy to get the har"""
        endpoint = endpoint or self.AUTH_ENDPOINT
        # Start BrowserMob Proxy
        self.server = Server(self.BMP_PATH)
        self.server.start()
        self.proxy = self.server.create_proxy()

        # Configure Chrome with the proxy
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument(f'--proxy-server={self.proxy.proxy}')
        chrome_options.add_argument('--ignore-certificate-errors')
        if self.headless:
            chrome_options.add_argument('--headless')
        self.driver = webdriver.Chrome(options=chrome_options)
        # Navigate to the website
        self.driver.get(endpoint)

        # Start capturing network traffic
        self.proxy.new_har(f"nfl{time.time()}", options={'captureHeaders': True, 'captureContent': True})

        # Create the path for storing har data
        try:
            raw_path = endpoint.split('.com')[1]
            raw_path = raw_path.split('?')[0]
            str_path = raw_path.replace('/', '__')
        except:
            str_path = 'nfl'
        self.har_path = self.HAR_DIR/Path(str_path+'.har')

    def close_proxy(self):
        """Closes the driver and proxy"""
        self.server.stop()
        self.driver.quit()

    def wait_for_auth_token(self):
        """Downloads the auth token using the scores page of nfl.com"""
        start_time = time.time()
        while time.time() - start_time < self.TOKEN_AUTH_TIMEOUT:
            # Capture the HAR once
            self.har = self.proxy.har
            for entry in self.har['log']['entries']:
                request_headers = entry['request']['headers']
                for header in request_headers:
                    if header['name'] == 'Authorization':
                        self.auth_token = header['value']
                        return self.auth_token
            time.sleep(1)
        return None

    def store_auth_token(self):
        """Stores the current auth token"""
        # Store the auth token
        self.time = time.time()
        auth_json = {
            'time': self.time,
            'token': self.auth_token
        }
        with open(self.AUTH_PATH, 'w') as f:
            json.dump(auth_json, f)

    def store_har(self):
        """Stores the current har"""
        # Store the har data
        with open(self.har_path, 'w') as f:
            json.dump(self.har, f)

    def download_auth_token(self, store_har=False):
        """Downloads the auth token"""
        self.prep_proxy()         
        self.wait_for_auth_token()
        self.store_auth_token()
        if store_har:
            self.store_har()

    def download_endpoints(self, endpoint=None, wait_time=20):
        """Downloads the endpoints found in har, stores json, updates readme, updates Mixin for the class"""
        if not endpoint:
            endpoint = self.AUTH_ENDPOINT
        self.prep_proxy(endpoint)
        time.sleep(wait_time)
        self.har = self.proxy.har
        self.wait_for_auth_token()
        self.store_auth_token()
        self.store_har()
        self.close_proxy()

        # Load previous urls
        url_json = {}
        if os.path.exists(self.URL_JSON_PATH):
            with open(self.URL_JSON_PATH, 'r') as f:
                url_json = json.load(f)

        # Gather the list of endpoints
        for entry in self.har['log']['entries']:
            if self.API_ROOT in entry['request']['url']:
                url_json.update(har_entry_parse(entry))

        # Store the url json
        with open(self.URL_JSON_PATH, 'w') as f:
            json.dump(url_json, f)

        # Store the url openapi
        with open(self.OPENAPI_PATH, 'w') as f:
            f.write(generate_openapi_spec(url_json))
        
        return url_json

    def request(self, endpoint) -> dict:
        """Request an endpoint"""
        self.load_auth_token()
        try:
            return requests.get(endpoint, headers=self.headers)
        except Exception as e:
            return {
                'error': e
            }   