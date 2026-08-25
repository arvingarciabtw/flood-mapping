## Overview

This module extracts the images from the flood-related tweets for Pasig, Marikina, and Manila during Typhoon Ulysses (November 11–15, 2020).

## Project Structure

```
flood-mapping/
├── extract_images.py       # Downloads images from tweet URLs
├── data/
│   └── ulysses/
│       └── 1k-twitter-ulysses-raw.csv  # Raw scraped tweet records
├── images/                 # Downloaded tweet images (see setup)
└── venv/                   # Python virtual environment
```

## Setup

1. Clone the repo
2. Create and activate virtual environment:

```bash
python -m venv venv
source venv/bin/activate.fish  # Fish shell
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

To download images from tweet URLs:

```bash
python extract_images.py
```

Images will be saved to the `images/` folder. Make sure to change the `CSV_FILE` constant. It is a file path to the `.csv` file that you want to extract the images from.

## Data

- **Source:** X (Twitter) via Apify Tweet Scraper V2
- **Event:** Typhoon Ulysses (Nov 11–15, 2020)
- **Records:** 1,000 tweets
- **Images:** 195 downloaded
- **Cities covered:** Pasig, Marikina, Manila

## Facebook Images

`download_facebook_images.py` downloads photo attachments labeled `mild`,
`moderate`, or `severe` from `data/data-facebook/typhoons_annotated.csv`.
It skips videos, deduplicates photos by Facebook ID, validates downloaded files,
and stores resumable state under the output directory.

First, verify the input selection without making network requests:

```bash
python download_facebook_images.py --dry-run
```

Run a small authenticated pilot using a browser profile logged into Facebook:

```bash
python download_facebook_images.py \
  --cookies-from-browser zen \
  --limit 25
```

Remove `--limit` for the full run. Any unresolved download makes the command
exit nonzero and remains visible in `manifest.csv`. After fixing authentication,
waiting out a temporary block, or reviewing another extraction error, retry with:

```bash
python download_facebook_images.py \
  --cookies-from-browser zen \
  --retry-failed
```

Images, logs, SQLite state, and `manifest.csv` are written to
`images/facebook-typhoons/`, which is ignored by Git. Photos that Facebook no
longer exposes are recorded as `unavailable` without stopping the remaining
downloads.

After the initial run, retry failed photos through their row-level Facebook
post URLs. Start with a small post pilot:

```bash
python download_facebook_images.py \
  --cookies-from-browser zen \
  --recover-from-posts \
  --post-limit 5
```

Remove `--post-limit` to process all remaining failed photos. Post recovery
groups attachments by post and matches each downloaded image to its exact
Facebook photo ID. If Zen is open and its newest login cookies have not yet
been written to disk, close Zen before running the command.
