"""Test script for Paris MoU Data Exchange Service (DES) API.

Flow:
1. Use API key to get a temporary authorization token (valid 10 min)
2. Use auth token to list available files
3. Download the first file as a sample

Note: The API may return PHP print_r output instead of JSON.
      The server also restricts by source IP — you may need to whitelist yours.
"""

import os
import re
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://fileserver.parismou.org/api"
API_KEY = os.environ.get("PARIS_MOU_KEY")

if not API_KEY:
    raise SystemExit("PARIS_MOU_KEY not found in .env")


def parse_response(text):
    """Parse response — try JSON first, fall back to reading PHP print_r output."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Extract key info from PHP print_r format
    result = {}
    code_match = re.search(r'\[code\]\s*=>\s*(\S+)', text)
    msg_match = re.search(r'\[message\]\s*=>\s*(.+)', text)
    token_match = re.search(r'\[access_token\]\s*=>\s*(\S+)', text)
    ip_match = re.search(r'\[source_ip\]\s*=>\s*(\S+)', text)

    result["status"] = {
        "code": code_match.group(1) if code_match else "unknown",
        "message": msg_match.group(1).strip() if msg_match else "unknown",
    }
    if token_match:
        result["access_token"] = token_match.group(1)
    if ip_match:
        result["source_ip"] = ip_match.group(1)

    # Extract files array if present
    files_match = re.findall(r'\[\d+\]\s*=>\s*(.+)', text)
    if files_match:
        result["files"] = [f.strip() for f in files_match]

    return result


def get_auth_token():
    """Step 1: Exchange API key for a short-lived authorization token."""
    url = f"{BASE_URL}/{API_KEY}/getauthorizationtoken"
    print(f"\n--- Getting authorization token ---")
    resp = requests.get(url)
    print(f"HTTP {resp.status_code} | Content-Type: {resp.headers.get('Content-Type')}")

    data = parse_response(resp.text)
    print(json.dumps(data, indent=2))

    if data.get("status", {}).get("code") != "success":
        ip = data.get("source_ip", "unknown")
        msg = data.get("status", {}).get("message", "unknown error")
        raise SystemExit(
            f"\nAuth failed: {msg}\n"
            f"Your IP: {ip}\n"
            f"You may need to whitelist this IP with Paris MoU."
        )

    token = data["access_token"]
    print(f"\nToken obtained: {token[:20]}...")
    return token


def get_file_list(token):
    """Step 2: List all available files on the DES server."""
    url = f"{BASE_URL}/{token}/getfilelist"
    print(f"\n--- Getting file list ---")
    resp = requests.get(url)
    print(f"HTTP {resp.status_code}")

    data = parse_response(resp.text)

    if data.get("status", {}).get("code") != "success":
        print(json.dumps(data, indent=2))
        raise SystemExit("getfilelist failed")

    raw_files = data.get("files", [])
    # Filter out size entries ("0") and empty strings
    files = [f for f in raw_files if f and not f.strip().isdigit()]
    print(f"Found {len(files)} files on server (filtered from {len(raw_files)} raw entries)")

    # Group by prefix to show categories
    from collections import defaultdict
    categories = defaultdict(list)
    for f in files:
        # Extract prefix before the date portion
        prefix = re.split(r'_\d{8}', f)[0] if re.search(r'_\d{8}', f) else f
        categories[prefix].append(f)

    print(f"\n--- File categories ({len(categories)}) ---")
    for prefix in sorted(categories.keys()):
        samples = categories[prefix]
        print(f"\n  {prefix} ({len(samples)} files)")
        for s in samples[:3]:
            print(f"    - {s}")
        if len(samples) > 3:
            print(f"    ... and {len(samples) - 3} more")

    return files


def download_sample_file(token, filename):
    """Step 3: Download a single file to inspect its contents."""
    url = f"{BASE_URL}/{token}/getfile/{filename}"
    print(f"\n--- Downloading sample file: {filename} ---")
    resp = requests.get(url)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "paris_mou")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)

    with open(out_path, "wb") as f:
        f.write(resp.content)

    size_kb = len(resp.content) / 1024
    print(f"Saved to {out_path} ({size_kb:.1f} KB)")
    print(f"Content-Type: {resp.headers.get('Content-Type', 'unknown')}")

    if filename.endswith(".zip"):
        import zipfile, io
        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            print(f"Zip contents: {zf.namelist()}")
            for name in zf.namelist():
                if name.endswith(".xml"):
                    preview = zf.read(name)[:2000].decode("utf-8", errors="replace")
                    print(f"\n--- Preview of {name} (first 2000 chars) ---")
                    print(preview)
                    break
        except zipfile.BadZipFile:
            print("Not a valid zip file")


if __name__ == "__main__":
    token = get_auth_token()
    files = get_file_list(token)

    # Download a recent daily GetPublicFile to inspect structure
    daily_files = [f for f in files if re.match(r'GetPublicFile_\d{8}_', f)]
    if daily_files:
        # Pick a recent one
        target = daily_files[-1]
        download_sample_file(token, target)
    elif files:
        download_sample_file(token, files[0])
