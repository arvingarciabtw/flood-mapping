import pandas as pd
import os

# --- CONFIGURE THESE ---
NAME = "ulysses"
PREFIX = f"./data/{NAME}"
CSV_PATH = f"{PREFIX}/{NAME}-raw.csv"                       # path to your CSV file
IMAGE_DIR = f"./images/extracted-images/{NAME}-images"      # path to your images directory
OUTPUT_PATH = f"{PREFIX}/{NAME}-has-image.csv"              # path for the output CSV
# -----------------------

df = pd.read_csv(CSV_PATH)
 
def has_jpg(image_id):
    for filename in os.listdir(IMAGE_DIR):
        if filename.startswith(f"{image_id}_") and filename.endswith(".jpg"):
            return True
    return False
 
df["has_image"] = df["id"].apply(has_jpg)
 
df.to_csv(OUTPUT_PATH, index=False)
 
# Summary
total = len(df)
with_image = df["has_image"].sum()
without_image = total - with_image
 
print(f"Done! Results saved to: {OUTPUT_PATH}")
print(f"  Total records : {total}")
print(f"  Has image     : {with_image}")
print(f"  No image      : {without_image}")
 
