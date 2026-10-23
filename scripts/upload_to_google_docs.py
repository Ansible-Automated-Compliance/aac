#!/usr/bin/env python3
"""
upload_to_google_docs.py
========================
Converts a Markdown file to DOCX (via pandoc) and uploads it to Google Drive
as a native Google Doc.

Usage:
    python3 upload_to_google_docs.py <markdown_file> [--folder-id FOLDER_ID] [--title "Custom Title"]

First run:
    Opens a browser for Google OAuth consent. Token is cached in
    ~/.config/aac/google_token.json for subsequent runs.

Requirements:
    pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib
    brew install pandoc

Setup (one-time):
    1. Go to https://console.cloud.google.com/
    2. Create or select a project
    3. Enable the Google Drive API
    4. Create OAuth credentials: APIs & Services → Credentials → Create Credentials
       → OAuth client ID → Desktop App → Download JSON
    5. Save the downloaded file as ~/.config/aac/google_client_secret.json
"""

import sys
import os
import subprocess
import tempfile
import argparse

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_PATH = os.path.expanduser("~/.config/aac/google_token.json")
CREDS_PATH = os.path.expanduser("~/.config/aac/google_client_secret.json")


def get_credentials():
    """Load cached credentials or run OAuth flow."""
    sys.path.insert(0, os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                print(f"\nERROR: Google OAuth credentials not found at:\n  {CREDS_PATH}")
                print("\nSetup instructions:")
                print("  1. Go to https://console.cloud.google.com/")
                print("  2. Enable Google Drive API")
                print("  3. Create OAuth credentials (Desktop App)")
                print(f"  4. Save the downloaded JSON as:\n     {CREDS_PATH}")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"Token cached at {TOKEN_PATH}")

    return creds


def convert_to_docx(md_path):
    """Use pandoc to convert Markdown → DOCX."""
    if not md_path.endswith(".md"):
        return md_path  # Already a non-md file; upload as-is

    tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp.close()

    result = subprocess.run(
        ["pandoc", md_path, "-o", tmp.name,
         "--from", "markdown",
         "--to", "docx",
         "--reference-doc", "/dev/null"],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        # Fallback: try without reference doc
        result = subprocess.run(
            ["pandoc", md_path, "-o", tmp.name],
            capture_output=True, text=True
        )

    if result.returncode != 0:
        print(f"pandoc error: {result.stderr}")
        sys.exit(1)

    print(f"Converted to DOCX: {tmp.name}")
    return tmp.name


def upload_to_drive(docx_path, title, folder_id=None):
    """Upload DOCX to Google Drive and convert to Google Doc format."""
    sys.path.insert(0, os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",  # Convert to Google Doc
    }
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(
        docx_path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        resumable=True,
    )

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id,name,webViewLink",
    ).execute()

    return file


def main():
    parser = argparse.ArgumentParser(
        description="Convert Markdown to DOCX and upload to Google Docs"
    )
    parser.add_argument("markdown_file", help="Path to the Markdown file to upload")
    parser.add_argument("--folder-id", help="Google Drive folder ID to upload into (optional)")
    parser.add_argument("--title", help="Document title (defaults to filename without extension)")
    args = parser.parse_args()

    md_path = os.path.expanduser(args.markdown_file)
    if not os.path.exists(md_path):
        print(f"ERROR: File not found: {md_path}")
        sys.exit(1)

    # Derive title from filename if not provided
    title = args.title or os.path.splitext(os.path.basename(md_path))[0].replace("_", " ").title()

    print(f"Document:  {md_path}")
    print(f"Title:     {title}")
    if args.folder_id:
        print(f"Folder ID: {args.folder_id}")
    print()

    # Convert to DOCX
    docx_path = convert_to_docx(md_path)
    tmp_created = docx_path != md_path

    try:
        print("Uploading to Google Drive...")
        result = upload_to_drive(docx_path, title, folder_id=args.folder_id)
        print()
        print("=" * 60)
        print("  Upload successful!")
        print(f"  Title:  {result['name']}")
        print(f"  Doc ID: {result['id']}")
        print(f"  URL:    {result['webViewLink']}")
        print("=" * 60)
    finally:
        if tmp_created and os.path.exists(docx_path):
            os.unlink(docx_path)


if __name__ == "__main__":
    main()
