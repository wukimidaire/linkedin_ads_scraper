import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get credentials from .env
username = os.getenv('PROXY_USERNAME')
password = os.getenv('PROXY_PASSWORD')

if not username or not password:
    print("Please set PROXY_USERNAME and PROXY_PASSWORD in your .env file")
    exit()

url = 'https://ip.smartproxy.com/json'
proxy = f"socks5h://{username}:{password}@dc.smartproxy.com:10001"

try:
    result = requests.get(
        url, 
        proxies={
            'http': proxy,
            'https': proxy
        }
    )
    data = json.loads(result.text)
    print(f"IP: {data['proxy']['ip']}")
except requests.exceptions.RequestException as e:
    print(f"Error: {e}") 