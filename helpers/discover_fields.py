#!/usr/bin/env python3
"""
Discover SharePoint list field names.

Usage:
    python scripts/discover_fields.py "List Name"
    python scripts/discover_fields.py --all

Examples:
    python scripts/discover_fields.py "Training_Videos"
    python scripts/discover_fields.py "Glossary"
    python scripts/discover_fields.py --all  # Lists all lists in the site
"""

import argparse
import os
import sys

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# SharePoint configuration
SHAREPOINT_SITE = "uscedu.sharepoint.com"
SITE_PATH = "sites/AdvancementBusinessIntelligenceHub"

# Token configuration
TOKEN_SCOPE = "https://uscedu.sharepoint.com/.default"

# Environment variables
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")


def get_access_token() -> str:
    """Get access token from Microsoft Graph API using refresh token."""
    if not all([REFRESH_TOKEN, TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        print("Error: Missing required environment variables.")
        print("Required: REFRESH_TOKEN, TENANT_ID, CLIENT_ID, CLIENT_SECRET")
        sys.exit(1)

    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    
    data = {
        "grant_type": "refresh_token",
        "scope": TOKEN_SCOPE,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "redirect_uri": "http://localhost"
    }
    
    response = requests.post(token_url, data=data)
    
    if response.status_code == 200 and response.json().get("access_token"):
        return response.json()["access_token"]
    else:
        print(f"Error getting access token: {response.status_code}")
        print(response.text)
        sys.exit(1)


def list_all_lists(access_token: str) -> None:
    """List all lists in the SharePoint site."""
    url = (
        f"https://{SHAREPOINT_SITE}/{SITE_PATH}/_api/web/lists"
        f"?$select=Title,ItemCount,Hidden&$filter=Hidden eq false"
    )
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata=nometadata",
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        lists = response.json().get("value", [])
        print(f"\nFound {len(lists)} lists in site:\n")
        print(f"{'List Name':<40} {'Items':>8}")
        print("-" * 50)
        for lst in sorted(lists, key=lambda x: x["Title"]):
            print(f"{lst['Title']:<40} {lst['ItemCount']:>8}")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)


def discover_fields(access_token: str, list_name: str) -> None:
    """Discover all fields in a SharePoint list."""
    url = (
        f"https://{SHAREPOINT_SITE}/{SITE_PATH}/_api/web/lists/"
        f"getbytitle('{list_name}')/fields"
        f"?$select=Title,InternalName,TypeAsString,Required"
        f"&$filter=Hidden eq false and ReadOnlyField eq false"
    )
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata=nometadata",
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        fields = response.json().get("value", [])
        
        print(f"\nFields in '{list_name}':\n")
        print(f"{'Internal Name':<30} {'Display Name':<30} {'Type':<15} {'Req'}")
        print("-" * 80)
        
        for field in sorted(fields, key=lambda x: x["InternalName"]):
            internal = field["InternalName"]
            display = field["Title"]
            field_type = field["TypeAsString"]
            required = "Yes" if field.get("Required") else ""
            print(f"{internal:<30} {display:<30} {field_type:<15} {required}")
        
        # Print config snippet
        print("\n" + "=" * 80)
        print("Copy this to LIST_CONFIGS in fetch_sharepoint.py:")
        print("=" * 80)
        print(f'''
    "{list_name.lower().replace(' ', '_')}": {{
        "list_name": "{list_name}",
        "enabled": True,
        "fields": [''')
        
        field_names = [f'"{f["InternalName"]}"' for f in fields 
                       if f["InternalName"] not in ("ContentType", "Attachments")]
        
        # Format nicely
        for i in range(0, len(field_names), 4):
            chunk = field_names[i:i+4]
            print(f"            {', '.join(chunk)},")
        
        print("        ],")
        print("    },")
        
    elif response.status_code == 404:
        print(f"Error: List '{list_name}' not found")
        print("\nUse --all to see available lists")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)


def get_sample_items(access_token: str, list_name: str, count: int = 3) -> None:
    """Get sample items from a list to see actual data."""
    url = (
        f"https://{SHAREPOINT_SITE}/{SITE_PATH}/_api/web/lists/"
        f"getbytitle('{list_name}')/items?$top={count}"
    )
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata=nometadata",
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        items = response.json().get("value", [])
        print(f"\nSample items from '{list_name}':\n")
        
        import json
        for i, item in enumerate(items, 1):
            print(f"--- Item {i} ---")
            # Filter out system fields
            filtered = {k: v for k, v in item.items() 
                       if not k.startswith("odata") and v is not None}
            print(json.dumps(filtered, indent=2, ensure_ascii=False))
            print()
    else:
        print(f"Error: {response.status_code}")


def main():
    parser = argparse.ArgumentParser(
        description="Discover SharePoint list field names"
    )
    parser.add_argument(
        "list_name",
        nargs="?",
        help="Name of the SharePoint list"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="List all available lists in the site"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Show sample items from the list"
    )
    args = parser.parse_args()
    
    if not args.list_name and not args.all:
        parser.print_help()
        print("\nExamples:")
        print('  python scripts/discover_fields.py "Training_Videos"')
        print('  python scripts/discover_fields.py --all')
        sys.exit(0)
    
    print("Authenticating...")
    access_token = get_access_token()
    print("Success!\n")
    
    if args.all:
        list_all_lists(access_token)
    else:
        discover_fields(access_token, args.list_name)
        if args.sample:
            get_sample_items(access_token, args.list_name)


if __name__ == "__main__":
    main()

