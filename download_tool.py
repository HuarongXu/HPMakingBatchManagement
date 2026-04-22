"""
Download script for HP Making Batch Management Tool.
This script downloads the latest version from GitHub using a token.

Usage:
    python download_tool.py <TOKEN>
    
    where <TOKEN> is the GitHub Personal Access Token provided to you.
"""

import sys
import os
import urllib.request
import zipfile
import shutil

REPO_URL = "https://github.com/HuarongXu/HPMakingBatchManagement/archive/refs/heads/main.zip"
DOWNLOAD_FILE = "HPMakingBatchManagement.zip"
EXTRACT_DIR = "HPMakingBatchManagement"


def download(token=None):
    print("=" * 50)
    print("  HP Making Batch Management Tool - Downloader")
    print("=" * 50)
    print()

    # Build request
    req = urllib.request.Request(REPO_URL)
    if token:
        req.add_header("Authorization", f"token {token}")
        print("[INFO] Using provided token for authentication.")
    else:
        print("[INFO] No token provided, attempting public download...")

    # Download
    print(f"[1/3] Downloading from GitHub...")
    try:
        with urllib.request.urlopen(req) as response:
            with open(DOWNLOAD_FILE, "wb") as f:
                f.write(response.read())
        print(f"      Downloaded: {DOWNLOAD_FILE}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("[ERROR] Repository not found. Check if the token has 'repo' permission.")
        elif e.code == 401:
            print("[ERROR] Authentication failed. Check your token.")
        else:
            print(f"[ERROR] HTTP Error {e.code}: {e.reason}")
        return False

    # Extract
    print(f"[2/3] Extracting files...")
    if os.path.exists(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)
    
    with zipfile.ZipFile(DOWNLOAD_FILE, "r") as zip_ref:
        zip_ref.extractall(".")
    
    # The zip extracts to HPMakingBatchManagement-main/, rename it
    extracted_name = "HPMakingBatchManagement-main"
    if os.path.exists(extracted_name):
        os.rename(extracted_name, EXTRACT_DIR)
    
    # Clean up zip
    os.remove(DOWNLOAD_FILE)
    print(f"      Extracted to: {EXTRACT_DIR}/")

    # Done
    print(f"[3/3] Done!")
    print()
    print("=" * 50)
    print("  Next steps:")
    print(f"  1. cd {EXTRACT_DIR}/BatchManagementTool")
    print(f"  2. pip install -r requirements.txt")
    print(f"  3. Put your data files in the data/ folder")
    print(f"  4. python src/main.py")
    print()
    print("  Or simply double-click install_and_run.bat")
    print("=" * 50)
    return True


if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else None
    download(token)
