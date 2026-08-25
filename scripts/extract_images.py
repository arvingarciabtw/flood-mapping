import csv
import os
import subprocess

# Config
CSV_FILE = "./data/ulysses/1k-twitter-ulysses-raw.csv"
OUTPUT_DIR = "images"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Read tweet URLs from CSV
with open(CSV_FILE, newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    urls = [row['url'] for row in reader if row.get('url')]

print(f"Found {len(urls)} tweet URLs")

success = 0
failed = 0

for i, url in enumerate(urls, 1):
    print(f"[{i}/{len(urls)}] Processing: {url}")
    result = subprocess.run(
        ["gallery-dl", "--directory", OUTPUT_DIR, url],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        success += 1
    else:
        failed += 1
        print(f"  Failed: {result.stderr.strip()}")

print(f"\nDone! Success: {success} | Failed/No image: {failed}")
