#!/usr/bin/env python3
"""
Test script for Paris MOU Data Exchange API.

Usage:
    python scripts/test_parismou_api.py

API docs: https://parismou.org/system/files/2021-10/API%20documentation%20v1_0.pdf

Endpoints:
    1. GET /api/{api_key}/getauthorizationtoken  -> returns access token (valid 10 min)
    2. GET /api/{token}/getfilelist               -> returns list of available files
    3. GET /api/{token}/getfile/{filename}         -> downloads a file
"""

import json
import sys
import time
import requests

BASE_URL = "https://fileserver.parismou.org/api"
API_KEY = "09bqYmVUMzAD8RhyU0"


def get_auth_token():
    """Step 1: Exchange API key for a short-lived access token."""
    url = f"{BASE_URL}/{API_KEY}/getauthorizationtoken"
    print(f"[1] GET {url}")
    resp = requests.get(url, timeout=30)
    print(f"    Status: {resp.status_code}")
    print(f"    Headers: {dict(resp.headers)}")
    print(f"    Body: {resp.text[:2000]}")
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or data.get("token") or data.get("AccessToken")
    if not token:
        print(f"    [!] Could not find token in response keys: {list(data.keys())}")
        # Try the whole response as token if it's a plain string
        if isinstance(data, str):
            token = data
        else:
            print(f"    Full response: {json.dumps(data, indent=2)}")
            sys.exit(1)
    print(f"    Token: {token[:20]}...")
    return token


def get_file_list(token):
    """Step 2: Get list of available files."""
    url = f"{BASE_URL}/{token}/getfilelist"
    print(f"\n[2] GET {url[:80]}...")
    resp = requests.get(url, timeout=60)
    print(f"    Status: {resp.status_code}")
    print(f"    Content-Type: {resp.headers.get('content-type')}")
    print(f"    Body length: {len(resp.text)} chars")
    resp.raise_for_status()

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(f"    Raw body (first 3000 chars): {resp.text[:3000]}")
        return []

    if isinstance(data, list):
        print(f"    File count: {len(data)}")
        # Show first 20 files
        for f in data[:20]:
            if isinstance(f, str):
                print(f"      - {f}")
            elif isinstance(f, dict):
                print(f"      - {json.dumps(f)}")
        if len(data) > 20:
            print(f"      ... and {len(data) - 20} more")
        # Show last 5 to see date range
        if len(data) > 25:
            print(f"    Last 5 files:")
            for f in data[-5:]:
                if isinstance(f, str):
                    print(f"      - {f}")
                elif isinstance(f, dict):
                    print(f"      - {json.dumps(f)}")
        return data
    elif isinstance(data, dict):
        print(f"    Response keys: {list(data.keys())}")
        print(f"    Full response: {json.dumps(data, indent=2)[:3000]}")
        # Try common wrapper keys
        for key in ["files", "data", "filelist", "FileList", "result", "items"]:
            if key in data:
                files = data[key]
                print(f"    Found files under '{key}': {len(files)} items")
                for f in files[:20]:
                    print(f"      - {f}")
                return files
        return []
    else:
        print(f"    Unexpected type: {type(data)}")
        print(f"    Value: {str(data)[:2000]}")
        return []


def download_sample_file(token, filename):
    """Step 3: Download a single file to inspect its contents."""
    url = f"{BASE_URL}/{token}/getfile/{filename}"
    print(f"\n[3] GET {url[:80]}...")
    resp = requests.get(url, timeout=120)
    print(f"    Status: {resp.status_code}")
    print(f"    Content-Type: {resp.headers.get('content-type')}")
    print(f"    Content-Length: {resp.headers.get('content-length', len(resp.content))} bytes")
    resp.raise_for_status()

    # Save to data/ directory
    outpath = f"data/parismou_sample_{filename}"
    with open(outpath, "wb") as f:
        f.write(resp.content)
    print(f"    Saved to: {outpath}")

    # Show first 2000 chars if text-ish
    content_type = resp.headers.get("content-type", "")
    if "xml" in content_type or "text" in content_type or "json" in content_type:
        print(f"    Content preview:\n{resp.text[:2000]}")
    else:
        # Try decoding anyway
        try:
            text = resp.content.decode("utf-8", errors="replace")
            print(f"    Content preview (decoded):\n{text[:2000]}")
        except Exception:
            print(f"    Binary content, first 200 bytes: {resp.content[:200]}")

    return resp.content


def main():
    print("=" * 60)
    print("Paris MOU Data Exchange API - Test Calls")
    print("=" * 60)

    # Step 1: Authenticate
    token = get_auth_token()

    # Step 2: List files
    files = get_file_list(token)

    if not files:
        print("\n[!] No files returned. Check the API response above.")
        return

    # Step 3: Download first file as sample
    first_file = files[0] if isinstance(files[0], str) else files[0].get("name", files[0].get("filename", str(files[0])))
    print(f"\n--- Downloading sample file: {first_file} ---")
    download_sample_file(token, first_file)

    # Also download last file to see date range
    if len(files) > 1:
        last_file = files[-1] if isinstance(files[-1], str) else files[-1].get("name", files[-1].get("filename", str(files[-1])))
        if last_file != first_file:
            print(f"\n--- Downloading last file: {last_file} ---")
            download_sample_file(token, last_file)

    print("\n" + "=" * 60)
    print("Done. Review the output above to understand:")
    print("  - File naming convention (dates, granularity)")
    print("  - File format (XML structure)")
    print("  - Data coverage (date range)")
    print("  - File sizes (for planning bulk downloads)")
    print("=" * 60)


if __name__ == "__main__":
    main()
