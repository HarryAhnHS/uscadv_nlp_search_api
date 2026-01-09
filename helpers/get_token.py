# This script is used to get a new refresh token for the Azure AD app.
# Step 1: Run this script - it opens the browser for sign-in
# Step 2: After redirect, copy the code from URL into scripts/auth_code.txt
# Step 3: Run this script again - it exchanges the code for tokens

import os
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

tenant_id = os.getenv("TENANT_ID")
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = "http://localhost"

CODE_FILE = Path(__file__).parent / "auth_code.txt"


def get_refresh_token():
    # Check if auth_code.txt exists with a code
    if CODE_FILE.exists():
        auth_code = CODE_FILE.read_text().strip()
        
        if not auth_code:
            print("Error: auth_code.txt is empty")
            return None
        
        print("Found auth code in auth_code.txt")
        print("Exchanging code for tokens...")
        
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'client_secret': client_secret,
            'code': auth_code,
            'redirect_uri': redirect_uri,
            'scope': 'https://uscedu.sharepoint.com/.default offline_access'
        }
        
        response = requests.post(token_url, data=token_data)
        
        # Clean up the code file
        CODE_FILE.unlink()
        
        if response.status_code == 200:
            tokens = response.json()
            print("\nSuccess! Here's your new refresh token:")
            print(f"\nREFRESH_TOKEN={tokens['refresh_token']}")
            print(f"\nAccess token expires in: {tokens['expires_in']} seconds")
            print("Update REFRESH_TOKEN in .env file")
            return tokens['refresh_token']
        else:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    else:
        # No code file - open browser for authorization
        auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': 'https://uscedu.sharepoint.com/.default offline_access',
            'response_mode': 'query'
        }
        
        auth_url_with_params = f"{auth_url}?{urlencode(params)}"
        print("Opening browser for sign-in...")
        webbrowser.open(auth_url_with_params)
        
        print("\nAfter signing in, you'll be redirected to:")
        print("http://localhost/?code=AUTH_CODE_HERE&session_state=...")
        print()
        print("Copy the code value (between 'code=' and '&') and save it to:")
        print(f"  {CODE_FILE}")
        print()
        print("Then run this script again.")
        return None


if __name__ == "__main__":
    get_refresh_token()
