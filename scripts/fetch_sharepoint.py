#!/usr/bin/env python3
"""
Fetch reports from SharePoint and format for NLP search indexing.

This script:
1. Authenticates with Microsoft Graph API using refresh token
2. Fetches all reports from the SharePoint Reports list
3. Transforms data to the format expected by build_index.py
4. Saves to data/docs.json (replaces mock_docs.json for production)

Usage:
    python scripts/fetch_sharepoint.py [--output data/docs.json]

Environment variables required:
    REFRESH_TOKEN - Microsoft Graph refresh token
    TENANT_ID - Azure AD tenant ID
    CLIENT_ID - Azure AD app client ID
    CLIENT_SECRET - Azure AD app client secret
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# Disable SSL warnings for internal endpoints
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

# SharePoint configuration
SHAREPOINT_SITE = "uscedu.sharepoint.com"
SITE_PATH = "sites/AdvancementBusinessIntelligenceHub"
LIST_NAME = "Reports_Power_Automate"

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
    
    headers = {
        "Accept": "application/json;odata=nometadata"
    }
    
    data = {
        "grant_type": "refresh_token",
        "scope": TOKEN_SCOPE,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "redirect_uri": "http://localhost"
    }
    
    print("Requesting access token...")
    response = requests.post(token_url, headers=headers, data=data)
    
    if response.status_code == 200 and response.json().get("access_token"):
        print("Successfully retrieved access token")
        return response.json()["access_token"]
    else:
        print(f"Error getting access token: {response.status_code}")
        print(response.text)
        sys.exit(1)


def fetch_sharepoint_reports(access_token: str) -> list[dict]:
    """Fetch all reports from the SharePoint list."""
    # Select all relevant fields
    select_fields = [
        "Id", "Title",
        "field_1",   # Category/Project folder
        "field_2",   # Workbook GUID
        "field_3",   # Workbook Title
        "field_4",   # Description
        "field_5",   # URL (alternate)
        "field_6",   # URL (primary)
        "field_7",   # Platform indicator
        "field_8",   # Tag group 1
        "field_9",   # Tag group 2
        "field_10",  # Tag group 3
        "field_11",  # Tag group 4
        "field_12",  # Tag group 5
        "field_13",  # Tag group 6
        "field_14",  # Tag group 7
        "field_15",  # Tag group 8
        "field_16",  # Tag group 9
        "Featured",
    ]
    
    list_url = (
        f"https://{SHAREPOINT_SITE}/{SITE_PATH}/_api/web/lists/"
        f"getbytitle('{LIST_NAME}')/items?$top=5000&$select={','.join(select_fields)}"
    )
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata=nometadata",
        "Content-Type": "application/json;odata=verbose"
    }
    
    print(f"Fetching reports from SharePoint list: {LIST_NAME}...")
    response = requests.get(list_url, headers=headers)
    
    if response.status_code == 200:
        items = response.json().get("value", [])
        print(f"Successfully retrieved {len(items)} reports")
        return items
    else:
        print(f"Error fetching SharePoint data: {response.status_code}")
        print(response.text)
        sys.exit(1)


def extract_tags(item: dict) -> list[str]:
    """Extract and combine all tag fields into a single list."""
    tag_fields = [
        "field_8", "field_9", "field_10", "field_11",
        "field_12", "field_13", "field_14", "field_15", "field_16"
    ]
    
    tags = []
    for field in tag_fields:
        value = item.get(field)
        if value:
            if isinstance(value, list):
                tags.extend(value)
            elif isinstance(value, str):
                # Handle pipe-separated or comma-separated
                if "|" in value:
                    tags.extend([t.strip() for t in value.split("|") if t.strip()])
                elif "," in value:
                    tags.extend([t.strip() for t in value.split(",") if t.strip()])
                else:
                    tags.append(value.strip())
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    return unique_tags


def transform_to_search_format(items: list[dict]) -> list[dict]:
    """Transform SharePoint items to the format expected by build_index.py."""
    documents = []
    
    for item in items:
        # Get workbook GUID as docId
        doc_id = item.get("field_2") or item.get("Id")
        if not doc_id:
            continue
        
        # Get URL (prefer field_6, fallback to field_5)
        url = item.get("field_6") or item.get("field_5") or ""
        
        # Determine platform from URL
        if "tableau" in url.lower() or "tabpri" in url.lower():
            platform = "Tableau"
        elif "cognos" in url.lower():
            platform = "Cognos"
        elif "powerbi" in url.lower():
            platform = "Power BI"
        else:
            platform = "Tableau"  # Default for BI Hub
        
        # Extract tags
        tags = extract_tags(item)
        
        # Build document
        doc = {
            "docId": str(doc_id),
            "type": "report",
            "title": item.get("field_3") or item.get("Title") or "",
            "description": item.get("field_4") or "",
            "url": url,
            "category": item.get("field_1") or "",
            "platform": platform,
            "tags": tags,
        }
        
        # Only include if we have a title
        if doc["title"]:
            documents.append(doc)
    
    return documents


def save_documents(documents: list[dict], output_path: Path) -> None:
    """Save documents to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(documents)} documents to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch SharePoint reports for NLP search indexing"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "docs.json",
        help="Output file path (default: data/docs.json)"
    )
    args = parser.parse_args()
    
    print(f"SharePoint NLP Search Data Fetcher")
    print(f"=" * 40)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get access token
    access_token = get_access_token()
    
    # Fetch SharePoint data
    raw_items = fetch_sharepoint_reports(access_token)
    
    # Transform to search format
    documents = transform_to_search_format(raw_items)
    
    # Save output
    save_documents(documents, args.output)
    
    # Summary
    print()
    print("Summary:")
    print(f"  - Total reports fetched: {len(raw_items)}")
    print(f"  - Documents saved: {len(documents)}")
    print(f"  - Output file: {args.output}")
    print()
    print("Next steps:")
    print(f"  1. Review {args.output}")
    print(f"  2. Run: python scripts/build_index.py --force")
    print(f"  3. Restart the API server")


if __name__ == "__main__":
    main()

