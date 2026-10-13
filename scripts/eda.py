"""Recreate the annotated text corpus and produce the Section 3.6 EDA figures.

Mirrors the cleaning/geocoding logic of data/result/flood_monitoring_result.ipynb.
The SocialCrawl labels come from data/annotated data/text/socialcrawl_annotated.csv
(restored from git; its one Excel-corrupted id is dropped). The image side is not
reproduced (the image archives are not in the repo). Outputs land in temp/.
"""

import csv
import glob
import os
import re
from collections import Counter
from itertools import combinations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from wordcloud import WordCloud

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "temp")
FIG_DIR = os.path.join(OUT_DIR, "figures")

TEXT_LABEL_MAP = {
    "MILD": "Mild",
    "MODERATE": "Moderate",
    "MODERATET": "Moderate",
    "SEVERE": "Severe",
    "NOT RELEVANT": None,
    "TEXT ONLY": None,
}
FB_TEXT_LABEL_MAP = {"IRRELEVANT": None, "MILD": "Mild", "MODERATE": "Moderate", "SEVERE": "Severe"}

CITY_TERMS = {
    "Pasig": ["Pasig", "Pasig City"],
    "Marikina": ["Marikina", "Marikina City"],
    "Manila": ["Manila", "Manila City"],
}
DISTINCTIVE_BARANGAYS = {
    "Pasig": ["Bagong Ilog", "Bagong Katipunan", "Kalawaan", "Kapasigan", "Kapitolyo", "Malinao",
              "Manggahan", "Maybunga", "Oranbo", "Palatiw", "Pinagbuhatan", "Pineda", "Sagad",
              "Santolan", "Sumilang", "Ugong", "Caniogan"],
    "Marikina": ["Barangka", "Concepcion Uno", "Concepcion Dos", "Jesus Dela Pena", "Kalumpang",
                 "Marikina Heights", "Nangka", "Tumana", "Industrial Valley", "Malanday", "Tanong"],
    "Manila": ["Binondo", "Ermita", "Intramuros", "Malate", "Pandacan", "Quiapo", "Sampaloc",
               "Santa Mesa", "Tondo", "Paco"],
}
WEAK_BARANGAYS = {
    "Pasig": ["Bambang", "Buting", "Dela Paz", "San Antonio", "San Joaquin", "San Jose",
              "San Miguel", "San Nicolas", "Santa Cruz", "Santa Lucia", "Santa Rosa", "Santo Tomas",
              "Rosario"],
    "Marikina": ["San Roque", "Santa Elena", "Santo Nino", "Parang", "Fortune"],
    "Manila": ["San Andres", "San Miguel", "San Nicolas", "Santa Ana", "Port Area"],
}

STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had", "her", "was", "one",
    "our", "out", "day", "get", "has", "him", "his", "how", "its", "new", "now", "old", "see", "two",
    "way", "who", "boy", "did", "use", "that", "with", "this", "have", "from", "they", "will", "would",
    "there", "their", "what", "about", "which", "when", "make", "like", "time", "just", "know", "take",
    "into", "your", "some", "them", "than", "then", "only", "come", "over", "also", "back", "after",
    "could", "these", "more", "very", "been", "were", "here", "still", "being", "much", "where",
    "before", "right", "going", "well", "even", "want", "because", "good", "need", "should", "may",
    "she", "him", "did", "yes", "got", "let", "put", "say", "too", "why", "own", "off", "own",
    "t", "s", "m", "re", "ve", "ll", "d", "don", "doesn", "didn", "isn", "aren", "wasn", "weren",
    "won", "wouldn", "couldn", "shouldn", "can", "cannot", "im", "ive", "id", "youre", "youve",
    "ang", "ng", "nang", "sa", "na", "at", "ay", "mga", "po", "ko", "mo", "ni", "kay", "para",
    "ito", "iyan", "yan", "naman", "din", "rin", "dito", "diyan", "doon", "kung", "lang", "daw",
    "raw", "yung", "ung", "si", "sya", "kami", "kayo", "sila", "namin", "natin", "ninyo", "nila",
    "ako", "ikaw", "ka", "niya", "may", "meron", "wala", "hindi", "oo", "pero", "dahil", "kasi",
    "tapos", "sana", "pwede", "parang", "sobrang", "medyo", "grabe", "lang", "ha", "ba", "noh",
    "pra", "pag", "taga", "buong", "bawat", "lahat", "iba", "alin", "sino", "ano", "saan", "kelan",
    "ngayon", "bukas", "kahapon", "am", "pm", "us", "php", "via", "rt", "wa", "n",
}


def extract_tweet_id(url):
    match = re.search(r"/status/(\d+)", str(url))
    return f"tw_{match.group(1)}" if match else None


def load_facebook():
    path = os.path.join(ROOT, "data", "facebook", "typhoons", "typhoons_annotated.csv")
    fb = pd.read_csv(path, dtype={"postId": str})
    fb = fb[fb["postId"].str.match(r"^\d+$")].drop_duplicates(subset=["postId"]).copy()
    fb["tweet_id"] = "fb_" + fb["postId"].astype(str)
    fb["label"] = fb["text_annotated_flood_severity"].astype(str).str.strip().str.upper().map(FB_TEXT_LABEL_MAP)
    fb["text"] = fb["postText"]
    fb["source_file"] = "typhoons_annotated.csv"
    fb["createdAt"] = pd.to_datetime(fb["timestamp"], unit="ms", errors="coerce", utc=True)
    fb["platform"] = "facebook"
    fb = fb.dropna(subset=["label", "tweet_id"])
    fb = fb[fb["text"].notna() & (fb["text"].astype(str).str.strip() != "")]
    return fb[["tweet_id", "platform", "source_file", "text", "label", "createdAt"]].copy()


def _raw_createdat_lookup(event):
    raw_path = os.path.join(ROOT, "data", "twitter", event, f"{event}-raw.csv")
    if not os.path.exists(raw_path):
        return {}
    lookup = {}
    with open(raw_path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        fields = [(f or "").strip().lstrip("\ufeff") for f in reader.fieldnames]
        for row in reader:
            row = {(k or "").strip().lstrip("\ufeff"): v for k, v in row.items()}
            rid = str(row.get("id", "")).strip()
            if rid:
                lookup[rid] = row.get("createdAt")
    return lookup


def load_twitter():
    files = [f for f in glob.glob(os.path.join(ROOT, "data", "annotated data", "text", "*.csv"))
             if "image" not in os.path.basename(f).lower()
             and not os.path.basename(f).lower().startswith("typhoons")
             and not os.path.basename(f).lower().startswith("socialcrawl")]
    frames = []
    for path in files:
        name = os.path.basename(path)
        df = pd.read_csv(path)
        df.columns = df.columns.str.strip()
        label_col = next((c for c in df.columns if c.lower() == "severity level"), None)
        if label_col is None:
            print(f"WARNING: no severity column in {name}, skipping")
            continue
        df["label"] = df[label_col].astype(str).str.strip().str.upper().map(TEXT_LABEL_MAP)
        df["raw_tweet_id"] = df["url"].apply(lambda u: (re.search(r"/status/(\d+)", str(u)) or [None, None])[1]
                                             if re.search(r"/status/(\d+)", str(u)) else None)
        df["createdAt"] = pd.to_datetime(df.get("createdAt"), errors="coerce", utc=True) if "createdAt" in df.columns else pd.NaT
        df["source_file"] = name
        frames.append(df[["raw_tweet_id", "source_file", "text", "label", "createdAt"]])

    tweets = pd.concat(frames, ignore_index=True)
    tweets["tweet_id"] = tweets["raw_tweet_id"].apply(lambda r: f"tw_{r}" if pd.notna(r) else None)
    tweets = tweets.dropna(subset=["label", "tweet_id"])
    tweets = tweets.drop_duplicates(subset=["tweet_id"]).copy()

    missing = tweets["createdAt"].isna()
    if missing.any():
        for event in tweets.loc[missing, "source_file"].str.replace("-annotated.csv", "", regex=False).unique():
            lookup = _raw_createdat_lookup(event)
            if not lookup:
                continue
            sel = missing & tweets["source_file"].str.startswith(event)
            filled = tweets.loc[sel, "raw_tweet_id"].map(lookup)
            tweets.loc[sel, "createdAt"] = pd.to_datetime(filled, errors="coerce", utc=True)

    tweets["platform"] = "twitter"
    return tweets[["tweet_id", "platform", "source_file", "text", "label", "createdAt"]].copy()


def load_socialcrawl():
    path = os.path.join(ROOT, "data", "annotated data", "text", "socialcrawl_annotated.csv")
    sc = pd.read_csv(path, dtype={"id": str})
    sc = sc[sc["id"].str.match(r"^\d+$")].copy()
    sc = sc.dropna(subset=["severity_label", "text", "id"])
    sc["tweet_id"] = "tw_" + sc["id"].astype(str)
    sc["label"] = sc["severity_label"].astype(str).str.strip()
    sc["source_file"] = "socialcrawl_annotated.csv"
    sc["createdAt"] = pd.to_datetime(sc["created_at"], errors="coerce", utc=True)
    sc["platform"] = "twitter"
    sc = sc[sc["label"] != "Not Relevant"]
    return sc[["tweet_id", "platform", "source_file", "text", "label", "createdAt"]].copy()


def _compile(terms):
    return [re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in terms]


_CITY_RE = {c: _compile(t) for c, t in CITY_TERMS.items()}
_DIST_RE = {c: list(zip(DISTINCTIVE_BARANGAYS[c], _compile(DISTINCTIVE_BARANGAYS[c]))) for c in CITY_TERMS}
_WEAK_RE = {c: list(zip(WEAK_BARANGAYS[c], _compile(WEAK_BARANGAYS[c]))) for c in CITY_TERMS}


def geocode_text(text):
    if not isinstance(text, str) or not text:
        return None, None, "none"
    best = (None, None, 0)
    for city in CITY_TERMS:
        city_rank = 3 if any(p.search(text) for p in _CITY_RE[city]) else 0
        name, rank = None, 0
        for n, p in _DIST_RE[city]:
            if p.search(text):
                name, rank = n, 2
                break
        if rank == 0:
            for n, p in _WEAK_RE[city]:
                if p.search(text):
                    name, rank = n, 1
                    break
        total = max(city_rank, rank)
        if total > best[2]:
            best = (city, name, total)
    tier = {0: "none", 1: "weak_barangay", 2: "distinctive_barangay", 3: "city_name"}[best[2]]
    return best[0], best[1], tier


def clean_tokens(text):
    text = str(text).lower()
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"@\w+", " ", text)
    text = text.replace("#", " ")
    text = re.sub(r"[^a-z\s]", " ", text)
    return [w for w in text.split() if len(w) >= 3 and w not in STOPWORDS]


def find_font():
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        if os.path.exists(p):
            return p
    return None


def build_dataset():
    fb = load_facebook()
    tw = load_twitter()
    sc = load_socialcrawl()
    print(f"Facebook text rows: {len(fb)}")
    print(f"Twitter text rows:  {len(tw)}")
    print(f"SocialCrawl rows:   {len(sc)}")
    df = pd.concat([tw, fb, sc], ignore_index=True).drop_duplicates(subset=["tweet_id"]).copy()
    print(f"Combined text rows: {len(df)}")
    print("By platform:\n" + df["platform"].value_counts().to_string())
    print("Class distribution:\n" + df["label"].value_counts().to_string())

    assert len(df) == 4997, len(df)
    assert dict(df["platform"].value_counts()) == {"facebook": 4278, "twitter": 719}
    assert dict(df["label"].value_counts()) == {"Mild": 2807, "Moderate": 1349, "Severe": 841}

    geo = df["text"].apply(geocode_text)
    df["matched_city"] = [g[0] for g in geo]
    df["matched_barangay"] = [g[1] for g in geo]
    df["geo_confidence"] = [g[2] for g in geo]
    print("Geocode tiers:\n" + df["geo_confidence"].value_counts().to_string())
    return df


def fig_class_frequency(df):
    order = ["Mild", "Moderate", "Severe"]
    counts = df["label"].value_counts().reindex(order).fillna(0)
    colors = ["#2ecc71", "#f39c12", "#e74c3c"]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    bars = ax.bar(order, counts.values, color=colors)
    for b, v in zip(bars, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{int(v)}", ha="center", va="bottom")
    ax.set_title("Class Frequency Distribution")
    ax.set_xlabel("Severity")
    ax.set_ylabel("Posts")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "class_frequency.png"), dpi=150)
    plt.close(fig)


def fig_class_frequency_by_platform(df):
    order = ["Mild", "Moderate", "Severe"]
    platforms = ["facebook", "twitter"]
    colors = ["#2ecc71", "#f39c12", "#e74c3c"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    width = 0.25
    x = range(len(platforms))
    for i, sev in enumerate(order):
        vals = [int(((df["platform"] == p) & (df["label"] == sev)).sum()) for p in platforms]
        pos = [xi + (i - 1) * width for xi in x]
        bars = ax.bar(pos, vals, width, label=sev, color=colors[i])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([p.capitalize() for p in platforms])
    ax.set_title("Class Frequency Distribution by Platform")
    ax.set_ylabel("Posts")
    ax.legend(title="Severity")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "class_frequency_by_platform.png"), dpi=150)
    plt.close(fig)


def tokens_and_counts(df):
    counter = Counter()
    for text in df["text"]:
        counter.update(clean_tokens(text))
    return counter


def fig_word_frequency(counter):
    top = counter.most_common(30)
    words = [w for w, _ in top][::-1]
    vals = [v for _, v in top][::-1]
    fig, ax = plt.subplots(figsize=(7, 9))
    ax.barh(words, vals, color="#3498db")
    ax.set_title("Word Frequency (top 30)")
    ax.set_xlabel("Frequency")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "word_frequency.png"), dpi=150)
    plt.close(fig)


def fig_word_cloud(counter):
    font = find_font()
    wc = WordCloud(width=1200, height=700, background_color="white",
                   font_path=font, colormap="viridis")
    wc.generate_from_frequencies(counter)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title("Word Cloud")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "word_cloud.png"), dpi=150)
    plt.close(fig)


def fig_ngrams(df):
    bigrams = Counter()
    trigrams = Counter()
    for text in df["text"]:
        toks = clean_tokens(text)
        bigrams.update(zip(toks, toks[1:]))
        trigrams.update(zip(toks, toks[1:], toks[2:]))
    fig, axes = plt.subplots(1, 2, figsize=(14, 8))
    for ax, ng, title, k in [(axes[0], bigrams, "Top Bigrams", 20), (axes[1], trigrams, "Top Trigrams", 15)]:
        top = ng.most_common(k)
        labels = [" ".join(t) for t, _ in top][::-1]
        vals = [v for _, v in top][::-1]
        ax.barh(labels, vals, color="#9b59b6")
        ax.set_title(title)
        ax.set_xlabel("Frequency")
    fig.suptitle("N-grams")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "ngrams.png"), dpi=150)
    plt.close(fig)


def fig_spatial(df):
    in_scope = df[df["geo_confidence"].isin(["city_name", "distinctive_barangay"])]
    city_counts = in_scope["matched_city"].value_counts().reindex(["Manila", "Marikina", "Pasig"]).fillna(0)
    barangay_counts = (in_scope[in_scope["matched_barangay"].notna()]
                       .groupby(["matched_city", "matched_barangay"]).size()
                       .sort_values(ascending=False).head(15))
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    axes[0].bar(city_counts.index, city_counts.values, color="#16a085")
    for i, v in enumerate(city_counts.values):
        axes[0].text(i, v, f"{int(v)}", ha="center", va="bottom")
    axes[0].set_title("In-scope Posts by City")
    axes[0].set_ylabel("Posts")
    labels = [f"{b} ({c})" for c, b in barangay_counts.index][::-1]
    axes[1].barh(labels, barangay_counts.values[::-1], color="#2980b9")
    axes[1].set_title("Top 15 Barangays by Post Count")
    axes[1].set_xlabel("Posts")
    fig.suptitle("Spatial Analysis: Distribution of Posts by Location")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "spatial_distribution.png"), dpi=150)
    plt.close(fig)


def fig_temporal(df):
    ts = pd.to_datetime(df["createdAt"], errors="coerce", utc=True).dropna()
    monthly = ts.dt.tz_localize(None).dt.to_period("M").value_counts().sort_index()
    if monthly.empty:
        print("No timestamps for temporal figure")
        return
    x = monthly.index.to_timestamp()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(x, monthly.values, marker="o", color="#c0392b")
    ax.set_title("Temporal Analysis: Distribution of Posts Over Time")
    ax.set_xlabel("Month")
    ax.set_ylabel("Posts")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "temporal_distribution.png"), dpi=150)
    plt.close(fig)
    print(f"Temporal range: {x.min().date()} to {x.max().date()}, {len(x)} months")


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    df = build_dataset()

    out_cols = ["tweet_id", "platform", "source_file", "text", "label", "createdAt",
                "matched_city", "matched_barangay", "geo_confidence"]
    out = df[out_cols].copy()
    out["createdAt"] = pd.to_datetime(out["createdAt"], errors="coerce", utc=True)
    out.to_csv(os.path.join(OUT_DIR, "recreated_annotated_dataset.csv"), index=False)
    print(f"Wrote {os.path.join(OUT_DIR, 'recreated_annotated_dataset.csv')} ({len(out)} rows)")

    counter = tokens_and_counts(df)
    fig_class_frequency(df)
    fig_class_frequency_by_platform(df)
    fig_word_frequency(counter)
    fig_word_cloud(counter)
    fig_ngrams(df)
    fig_spatial(df)
    fig_temporal(df)
    print(f"Figures written to {FIG_DIR}")


if __name__ == "__main__":
    main()
