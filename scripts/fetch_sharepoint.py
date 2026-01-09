#!/usr/bin/env python3
"""
Fetch all content from SharePoint for NLP search indexing.

This script fetches:
1. Reports from the Reports list
2. Training videos from the Training Videos list
3. Glossary terms from the Glossary list
4. FAQs from the FAQ list

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
from typing import Callable

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

# Token configuration
TOKEN_SCOPE = "https://uscedu.sharepoint.com/.default"

# Environment variables
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# ============================================================================
# LIST CONFIGURATIONS
# Update these to match your SharePoint list names and field mappings
# ============================================================================

LIST_CONFIGS = {
    "reports": {
        "list_name": "Reports_Power_Automate",
        "enabled": True,
        "fields": [
            "Id", "Title",
            "field_1",   # Category/Project folder
            "field_2",   # Workbook GUID
            "field_3",   # Workbook Title
            "field_4",   # Description
            "field_5",   # URL (alternate)
            "field_6",   # URL (primary)
            "field_7",   # Platform indicator
            "field_8", "field_9", "field_10", "field_11",  # Tag groups
            "field_12", "field_13", "field_14", "field_15", "field_16",
            "Featured",
        ],
    },
    "training_videos": {
        # This is a document library with folders containing video files
        "library_name": "Training Resources",  # Document library name
        "enabled": True,
        "is_document_library": True,  # Flag to use folder fetching
    },
    "glossary": {
        "list_name": "Glossary Terms",
        "enabled": True,
        "fields": [
            "Id", "Title",  # Title = Term
            "field_1",      # Definition (update if different)
        ],
        # Field mapping: SharePoint field -> output field
        "field_map": {
            "Title": "term",
            "field_1": "definition",
        },
    },
    "faqs": {
        "list_name": "FAQs",
        "enabled": True,
        "fields": [
            "Id", "Title",  # Title = Question
            "Answer",       # Answer field
            "Link",         # Optional link
            "Priority",     # Optional priority
        ],
        # Field mapping: SharePoint field -> output field
        "field_map": {
            "Title": "question",
            "Answer": "answer",
            "Link": "url",
        },
    },
}


# ============================================================================
# AUTHENTICATION
# ============================================================================

def get_access_token() -> str:
    """Get access token from Microsoft Graph API using refresh token."""
    if not all([REFRESH_TOKEN, TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        print("Error: Missing required environment variables.")
        print("Required: REFRESH_TOKEN, TENANT_ID, CLIENT_ID, CLIENT_SECRET")
        sys.exit(1)

    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    
    headers = {"Accept": "application/json;odata=nometadata"}
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


# ============================================================================
# GENERIC SHAREPOINT LIST FETCHER
# ============================================================================

def fetch_list_items(access_token: str, list_name: str, fields: list[str]) -> list[dict]:
    """Fetch items from a SharePoint list."""
    list_url = (
        f"https://{SHAREPOINT_SITE}/{SITE_PATH}/_api/web/lists/"
        f"getbytitle('{list_name}')/items?$top=5000&$select={','.join(fields)}"
    )
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata=nometadata",
        "Content-Type": "application/json;odata=verbose"
    }
    
    print(f"  Fetching from list: {list_name}...")
    response = requests.get(list_url, headers=headers)
    
    if response.status_code == 200:
        items = response.json().get("value", [])
        print(f"  → Retrieved {len(items)} items")
        return items
    elif response.status_code == 404:
        print(f"  → List not found: {list_name} (skipping)")
        return []
    else:
        print(f"  → Error: {response.status_code}")
        print(f"     {response.text[:200]}")
        return []


def fetch_library_files(access_token: str, library_name: str) -> list[dict]:
    """
    Fetch all files from a document library, including subfolders.
    Returns file metadata with Name (title) and any custom columns.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata=nometadata",
    }
    
    # Fetch items with File expanded to get filename and folder path
    # Include _ExtendedDescription for video descriptions
    list_url = (
        f"https://{SHAREPOINT_SITE}/{SITE_PATH}/_api/web/lists/"
        f"getbytitle('{library_name}')/items"
        f"?$top=5000"
        f"&$expand=File"
        f"&$select=Id,Title,File/Name,File/ServerRelativeUrl,FileSystemObjectType,OData__ExtendedDescription"
    )
    
    print(f"  Fetching files from library: {library_name}...")
    response = requests.get(list_url, headers=headers)
    
    if response.status_code == 200:
        all_items = response.json().get("value", [])
        print(f"  → Retrieved {len(all_items)} total items")
        
        # Filter to only files (FileSystemObjectType = 0 means file, 1 means folder)
        files = []
        for item in all_items:
            # FileSystemObjectType: 0 = file, 1 = folder
            if item.get("FileSystemObjectType") == 0:
                # Extract file info from expanded File property
                file_info = item.get("File", {})
                if file_info:
                    item["_FileName"] = file_info.get("Name", "")
                    item["_FilePath"] = file_info.get("ServerRelativeUrl", "")
                    files.append(item)
        
        print(f"  → Filtered to {len(files)} files")
        
        # Debug: show sample
        if files:
            sample = files[0]
            print(f"  → Sample: {sample.get('_FileName', 'unknown')}")
        
        return files
    elif response.status_code == 404:
        print(f"  → Library not found: {library_name} (skipping)")
        print(f"     Try running: python scripts/discover_fields.py --all")
        return []
    else:
        print(f"  → Error: {response.status_code}")
        print(f"     {response.text[:300]}")
        return []


# ============================================================================
# TRANSFORM FUNCTIONS FOR EACH CONTENT TYPE
# ============================================================================

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
                if "|" in value:
                    tags.extend([t.strip() for t in value.split("|") if t.strip()])
                elif "," in value:
                    tags.extend([t.strip() for t in value.split(",") if t.strip()])
                else:
                    tags.append(value.strip())
    
    # Remove duplicates while preserving order
    seen = set()
    return [t for t in tags if t and not (t in seen or seen.add(t))]


def transform_reports(items: list[dict]) -> list[dict]:
    """Transform SharePoint report items to search format."""
    documents = []
    
    for item in items:
        doc_id = item.get("field_2") or item.get("Id")
        if not doc_id:
            continue
        
        url = item.get("field_6") or item.get("field_5") or ""
        
        # Determine platform from URL
        if "tableau" in url.lower() or "tabpri" in url.lower():
            platform = "Tableau"
        elif "cognos" in url.lower():
            platform = "Cognos"
        elif "powerbi" in url.lower():
            platform = "Power BI"
        else:
            platform = "Tableau"
        
        title = item.get("field_3") or item.get("Title") or ""
        if not title:
            continue
        
        documents.append({
            "docId": str(doc_id),
            "type": "report",
            "title": title,
            "description": item.get("field_4") or "",
            "url": url,
            "category": item.get("field_1") or "",
            "platform": platform,
            "tags": extract_tags(item),
        })
    
    return documents


def transform_training_videos(items: list[dict]) -> list[dict]:
    """Transform SharePoint training video files to search format."""
    documents = []
    
    for item in items:
        doc_id = item.get("Id")
        
        # For document library files (from fetch_library_files):
        # - _FileName = filename (e.g., "Getting Started.mp4")
        # - _FilePath = server relative URL
        # - Title = custom title field (may be empty)
        
        filename = item.get("_FileName") or ""
        title = item.get("Title") or ""
        
        # Use Title if set, otherwise use filename without extension
        if not title and filename:
            # Remove file extension for title
            title = filename.rsplit(".", 1)[0] if "." in filename else filename
        
        if not doc_id or not title:
            continue
        
        # Get folder path as category (extract folder name from path)
        file_path = item.get("_FilePath") or ""
        # Path like: /sites/Hub/Training Resources/Cognos/video.mp4
        # Extract the folder name (second to last segment)
        path_parts = file_path.split("/")
        category = path_parts[-2] if len(path_parts) >= 2 else ""
        
        # Description field in SharePoint is OData__ExtendedDescription
        description = item.get("OData__ExtendedDescription") or ""
        
        doc = {
            "docId": f"video-{doc_id}",
            "type": "training_video",
            "title": title,
            "description": description,
        }
        
        if category:
            doc["category"] = category
        
        documents.append(doc)
    
    return documents


def transform_glossary(items: list[dict]) -> list[dict]:
    """Transform SharePoint glossary items to search format.
    
    Field mapping (update in LIST_CONFIGS if your fields differ):
    - Title -> term
    - field_1 -> definition
    """
    documents = []
    
    # Get field mapping from config
    field_map = LIST_CONFIGS["glossary"].get("field_map", {})
    term_field = next((k for k, v in field_map.items() if v == "term"), "Title")
    def_field = next((k for k, v in field_map.items() if v == "definition"), "field_1")
    
    for item in items:
        doc_id = item.get("Id")
        term = item.get(term_field) or ""
        definition = item.get(def_field) or ""
        
        if not doc_id or not term:
            continue
        
        doc = {
            "docId": f"glossary-{doc_id}",
            "type": "glossary",
            "term": term,
            "definition": definition,
        }
        
        documents.append(doc)
    
    return documents


def transform_faqs(items: list[dict]) -> list[dict]:
    """Transform SharePoint FAQ items to search format.
    
    Field mapping (update in LIST_CONFIGS if your fields differ):
    - Title -> question
    - Answer -> answer
    - Link -> url (optional)
    """
    documents = []
    
    # Get field mapping from config
    field_map = LIST_CONFIGS["faqs"].get("field_map", {})
    q_field = next((k for k, v in field_map.items() if v == "question"), "Title")
    a_field = next((k for k, v in field_map.items() if v == "answer"), "Answer")
    url_field = next((k for k, v in field_map.items() if v == "url"), "Link")
    
    for item in items:
        doc_id = item.get("Id")
        question = item.get(q_field) or ""
        answer = item.get(a_field) or ""
        
        if not doc_id or not question:
            continue
        
        doc = {
            "docId": f"faq-{doc_id}",
            "type": "faq",
            "question": question,
            "answer": answer,
        }
        
        # Optional URL field
        url = item.get(url_field)
        if url:
            doc["url"] = url
        
        documents.append(doc)
    
    return documents


# Map content types to their transform functions
TRANSFORM_FUNCTIONS: dict[str, Callable] = {
    "reports": transform_reports,
    "training_videos": transform_training_videos,
    "glossary": transform_glossary,
    "faqs": transform_faqs,
}


# ============================================================================
# MAIN
# ============================================================================

def save_documents(documents: list[dict], output_path: Path) -> None:
    """Save documents to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(documents)} documents to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch SharePoint content for NLP search indexing"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "docs.json",
        help="Output file path (default: data/docs.json)"
    )
    parser.add_argument(
        "--only",
        type=str,
        help="Only fetch specific type: reports, training_videos, glossary, faqs"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("SharePoint NLP Search Data Fetcher")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get access token
    access_token = get_access_token()
    print()
    
    # Fetch and transform each content type
    all_documents = []
    stats = {}
    
    for content_type, config in LIST_CONFIGS.items():
        # Skip if not enabled or if --only specified for different type
        if not config["enabled"]:
            continue
        if args.only and args.only != content_type:
            continue
        
        print(f"[{content_type.upper()}]")
        
        # Fetch from SharePoint (handle both lists and document libraries)
        if config.get("is_document_library"):
            raw_items = fetch_library_files(
                access_token,
                config["library_name"]
            )
        else:
            raw_items = fetch_list_items(
                access_token,
                config["list_name"],
                config["fields"]
            )
        
        # Transform to search format
        if raw_items and content_type in TRANSFORM_FUNCTIONS:
            documents = TRANSFORM_FUNCTIONS[content_type](raw_items)
            all_documents.extend(documents)
            stats[content_type] = len(documents)
        else:
            stats[content_type] = 0
        
        print()
    
    # Save output
    save_documents(all_documents, args.output)
    
    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for content_type, count in stats.items():
        print(f"  {content_type}: {count}")
    print(f"  ─────────────────")
    print(f"  Total: {len(all_documents)}")
    print()
    print("Next steps:")
    print(f"  1. Review {args.output}")
    print(f"  2. Run: python scripts/build_index.py --force")
    print(f"  3. Restart the API server")


if __name__ == "__main__":
    main()
