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
pip install gallery-dl
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
