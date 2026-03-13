#!/usr/bin/env python3
"""
Example: Export Wasabi state to a native Google Sheet.

Demonstrates extracting bucket data from a state snapshot (as produced
by get_wasabi_state.py) and creating a formatted Google Sheets spreadsheet.

Requires: gspread, gspread-formatting, google-auth-oauthlib
    pip install gspread gspread-formatting google-auth-oauthlib

First-run setup:
    1. Create a Google Cloud project at https://console.cloud.google.com
    2. Enable the Google Sheets API and Google Drive API
    3. Create OAuth 2.0 credentials (Desktop app type)
    4. Download the credentials JSON to ~/.config/gspread/credentials.json
    5. Run the script - a browser window will open for OAuth consent
    6. The token is cached at ~/.config/gspread/authorized_user.json for future runs
"""

import json
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, List, Any

import gspread
from gspread_formatting import (
    CellFormat,
    Color,
    NumberFormat,
    TextFormat,
    format_cell_range,
    set_frozen,
)
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
CREDENTIALS_DIR = Path.home() / ".config" / "gspread"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
TOKEN_FILE = CREDENTIALS_DIR / "authorized_user.json"


def get_gspread_client() -> gspread.Client:
    """
    Authenticate and return a gspread client using OAuth2.

    On first run, opens a browser for consent. Subsequent runs use the cached token.
    """
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"OAuth credentials not found at {CREDENTIALS_FILE}\n"
            "Download your OAuth 2.0 credentials JSON from Google Cloud Console\n"
            f"and save it to: {CREDENTIALS_FILE}"
        )

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())

    return gspread.authorize(creds)


def extract_bucket_data(json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract and process bucket data from the JSON structure.

    Args:
        json_data: The parsed JSON data containing Wasabi resources

    Returns:
        A list of dictionaries with processed bucket information
    """
    buckets_data = []

    if "buckets" not in json_data:
        raise ValueError("Input JSON doesn't contain a 'buckets' section")

    for bucket_name, bucket_info in json_data["buckets"].items():
        bucket_data = {
            "bucket_name": bucket_name,
            "region": bucket_info.get("region", ""),
            "gb_used": bucket_info.get("gb_used", 0),
            "tb_used": bucket_info.get("gb_used", 0) / 1000,
            "object_count": bucket_info.get("object_count", 0),
            "has_lifecycle_policy": "No",
            "category": "",
            "notes": "",
        }

        lifecycle_rules = bucket_info.get("lifecycle-rules", {})
        if lifecycle_rules and isinstance(lifecycle_rules, dict):
            rules = lifecycle_rules.get("Rules", [])
            if rules and any(rule.get("Status") == "Enabled" for rule in rules):
                bucket_data["has_lifecycle_policy"] = "Yes"

        buckets_data.append(bucket_data)

    buckets_data.sort(key=lambda x: x["gb_used"], reverse=True)

    return buckets_data


def get_sheet_title(input_file: str) -> str:
    """Generate the Google Sheet title based on the input filename."""
    _, filename = os.path.split(input_file)
    return os.path.splitext(filename)[0]


def create_google_sheet(
    client: gspread.Client,
    bucket_data: List[Dict[str, Any]],
    title: str,
) -> str:
    """
    Create a native Google Sheets spreadsheet with formatted bucket data.

    Args:
        client: Authenticated gspread client
        bucket_data: List of dictionaries containing bucket information
        title: Title for the spreadsheet

    Returns:
        URL of the created Google Sheet
    """
    spreadsheet = client.create(title)

    worksheet = spreadsheet.sheet1
    worksheet.update_title("Bucket Data")

    headers = [
        "Bucket Name",
        "Region",
        "GB Used",
        "TB Used",
        "Object Count",
        "Has Lifecycle Policy",
        "Category",
        "Notes",
    ]

    rows = [headers]
    for data in bucket_data:
        rows.append([
            data["bucket_name"],
            data["region"],
            round(data["gb_used"]),
            round(data["tb_used"], 3),
            data["object_count"],
            data["has_lifecycle_policy"],
            data["category"],
            data["notes"],
        ])

    worksheet.update(rows, value_input_option="RAW")

    header_format = CellFormat(
        textFormat=TextFormat(bold=True),
        horizontalAlignment="CENTER",
        backgroundColor=Color(0.867, 0.867, 0.867),
    )
    format_cell_range(worksheet, "A1:H1", header_format)

    last_row = len(bucket_data) + 1
    num_format = CellFormat(
        numberFormat=NumberFormat(type="NUMBER", pattern="#,##0"),
    )
    format_cell_range(worksheet, f"C2:E{last_row}", num_format)

    set_frozen(worksheet, rows=1)

    spreadsheet.batch_update({
        "requests": [
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": worksheet.id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": len(headers),
                    }
                }
            }
        ]
    })

    return spreadsheet.url


def process_json(input_file: str) -> None:
    """Process JSON file and create a native Google Sheet."""
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    title = get_sheet_title(input_file)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    bucket_data = extract_bucket_data(data)

    if not bucket_data:
        print("No bucket data found in the JSON file")
        return

    print("Authenticating with Google...")
    client = get_gspread_client()

    print(f"Creating Google Sheet: {title}")
    url = create_google_sheet(client, bucket_data, title)

    print(f"Successfully created Google Sheet: {url}")


def main() -> int:
    """Main function to parse arguments and initiate processing."""
    parser = argparse.ArgumentParser(
        description="Convert Wasabi S3 bucket information from JSON to a native Google Sheet"
    )
    parser.add_argument("input_file", help="Input JSON file path")

    args = parser.parse_args()

    try:
        process_json(args.input_file)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
