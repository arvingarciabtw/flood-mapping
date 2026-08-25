import pandas as pd

# --- CONFIGURE THESE ---
NAME = "ulysses"
PREFIX = f"./data/{NAME}"
CSV_PATH = f"{PREFIX}/{NAME}-has-image.csv"             # path to your CSV file
OUTPUT_PATH = f"{PREFIX}/{NAME}-deduplicated.csv"       # path for the output CSV
# -----------------------

df = pd.read_csv(CSV_PATH)

before = len(df)
df = df.drop_duplicates(subset="id")
after = len(df)

df.to_csv(OUTPUT_PATH, index=False)

print(f"Done! Results saved to: {OUTPUT_PATH}")
print(f"  Before : {before} rows")
print(f"  After  : {after} rows")
print(f"  Removed: {before - after} duplicates")
