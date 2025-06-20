import os
import csv
import json
import requests
import datetime
import subprocess
import gspread
import xml.etree.ElementTree as ET
from dateutil import parser
from xml.dom import minidom
from google.oauth2.service_account import Credentials

os.environ["GOOGLE_SHEETS_CREDENTIALS"] = "service_account.json"

# ---------------- CONFIG ---------------- #

SPEAKER_ID = 860
SITE_NAME = "yutorah-rss"
DEPLOY_FOLDER = "deploy_netlify"
CSV_PATH = "torahanytime_lectures.csv"
GOOGLE_SHEET_NAME = "Rav Asher Weiss Shiurim"

NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")
NETLIFY_SITE_ID = os.getenv("NETLIFY_SITE_ID")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

FEEDS = [
    {
        "type": "torahanytime",
        "rss_filename": "rav_asher_weiss.xml",
        "csv": CSV_PATH,
        "title": "Rav Asher Weiss' Torah",
        "author": "Rav Asher Weiss",
        "email": "matthewjmiller07@gmail.com"
    },
    {
        "type": "yutorah",
        "rss_filename": "hershel_schachter.xml",
        "json_file": "Rabbi_Hershel_Schachter.json",
        "title": "Rabbi Hershel Schachter Shiurim",
        "author": "Rabbi Hershel Schachter",
        "email": "matthewjmiller07@gmail.com",
        "filter_func": lambda x: True
    },
    {
        "type": "yutorah",
        "rss_filename": "efrem_goldberg_parsha.xml",
        "json_file": "Rabbi_Efrem_Goldberg.json",
        "title": "Rabbi Efrem Goldberg - Parsha Shiurim",
        "author": "Rabbi Efrem Goldberg",
        "email": "matthewjmiller07@gmail.com",
        "filter_func": lambda x: "Parsha" in x.get("categoryname", [])
    }
]

# ---------------- UTILS ---------------- #

def escape_xml(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;") \
        .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

def get_audio_file_size(url):
    try:
        r = requests.head(url, timeout=5)
        return r.headers.get("Content-Length", "0") or "0"
    except:
        return "0"

def upload_to_google_sheets(new_rows):
    if not GOOGLE_SHEETS_CREDENTIALS or not os.path.exists(GOOGLE_SHEETS_CREDENTIALS):
        print("❌ Missing Google Sheets credentials.")
        return

    creds = Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)

    try:
        sheet = client.open(GOOGLE_SHEET_NAME)
        worksheet = sheet.sheet1
    except gspread.SpreadsheetNotFound:
        sheet = client.create(GOOGLE_SHEET_NAME)
        worksheet = sheet.sheet1
        sheet.share(creds.service_account_email, perm_type="user", role="writer")

    header = ["Title", "Date", "Audio URL", "File Size", "Page URL"]
    values = worksheet.get_all_values()
    if not values or values[0] != header:
        worksheet.clear()
        worksheet.append_row(header)
        existing_keys = set()
    else:
        existing_keys = set((row[0], row[1]) for row in values[1:])

    appendable = [row for row in new_rows if (row[0], row[1]) not in existing_keys]
    if appendable:
        worksheet.append_rows(appendable, value_input_option="USER_ENTERED")
        print(f"✅ Appended {len(appendable)} new rows to Google Sheet.")
    else:
        print("✅ Google Sheet is already up to date.")

# ---------------- MAIN ---------------- #

def fetch_and_save_csv():
    url = f"https://api.torahanytime.com/speakers/{SPEAKER_ID}/lectures?limit=10000"
    res = requests.get(url)
    if res.status_code != 200:
        print(f"❌ Error: Unable to fetch data (status code {res.status_code})")
        exit()

    data = res.json().get("lecture", [])
    print(f"📥 Fetched {len(data)} lectures from TorahAnytime.")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "id", "title", "date_recorded", "duration", "language_name",
            "category", "subcategories", "thumbnail_url",
            "audio_url", "mp4_url", "m3u8_url",
            "speaker_name_first", "speaker_name_last"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for lec in data:
            writer.writerow({
                "id": lec["id"],
                "title": lec["title"],
                "date_recorded": lec["date_recorded"],
                "duration": lec["duration"],
                "language_name": lec.get("language_name", ""),
                "category": lec.get("categories", [{}])[0].get("name", ""),
                "subcategories": ", ".join([s.get("name", "") for s in lec.get("subcategories", [])]),
                "thumbnail_url": lec.get("thumbnail_url", ""),
                "audio_url": lec.get("mp3_url", ""),
                "mp4_url": lec.get("mp4_url", ""),
                "m3u8_url": lec.get("m3u8_url", ""),
                "speaker_name_first": lec.get("speaker_name_first", ""),
                "speaker_name_last": lec.get("speaker_name_last", "")
            })
    print(f"✅ Saved to {CSV_PATH}")

def generate_rss():
    os.makedirs(DEPLOY_FOLDER, exist_ok=True)
    all_sheet_data = []

    for feed in FEEDS:
        if feed["type"] == "torahanytime":
            import pandas as pd
            df = pd.read_csv(feed["csv"])
            entries = [
                {
                    "id": str(row["id"]),
                    "title": escape_xml(row["title"]),
                    "date": row["date_recorded"],
                    "audio_url": row["audio_url"],
                    "page_url": f"https://www.torahanytime.com/lectures/{row['id']}"
                }
                for _, row in df.iterrows() if row["audio_url"]
            ]
        elif feed["type"] == "yutorah":
            with open(feed["json_file"], "r", encoding="utf-8") as f:
                raw = json.load(f)
            entries = [
                {
                    "id": str(row["shiurid"]),
                    "title": escape_xml(row["shiurtitle"]),
                    "date": row["shiurdatesubmitted"],
                    "audio_url": row["shiurdownloadurl"],
                    "page_url": row["shiurplayerurl"]
                }
                for row in raw if feed["filter_func"](row) and row["shiurdownloadurl"]
            ]

        rss_path = os.path.join(DEPLOY_FOLDER, feed["rss_filename"])
        rss_url = f"https://{SITE_NAME}.netlify.app/{feed['rss_filename']}"

        rss = ET.Element("rss", {
            "version": "2.0",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:atom": "http://www.w3.org/2005/Atom"
        })
        channel = ET.SubElement(rss, "channel")

        ET.SubElement(channel, "title").text = feed["title"]
        ET.SubElement(channel, "link").text = rss_url
        ET.SubElement(channel, "atom:link", href=rss_url, rel="self", type="application/rss+xml")
        ET.SubElement(channel, "description").text = feed["title"]
        ET.SubElement(channel, "language").text = "en-us"
        ET.SubElement(channel, "itunes:author").text = feed["author"]
        ET.SubElement(channel, "itunes:summary").text = feed["title"]
        ET.SubElement(channel, "itunes:subtitle").text = feed["title"]
        ET.SubElement(channel, "itunes:explicit").text = "no"
        ET.SubElement(channel, "itunes:image", href="https://i.imgur.com/hkwQrh9.png")

        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url").text = "https://i.imgur.com/hkwQrh9.png"
        ET.SubElement(image, "title").text = feed["title"]
        ET.SubElement(image, "link").text = rss_url

        cat = ET.SubElement(channel, "itunes:category", text="Religion & Spirituality")
        ET.SubElement(cat, "itunes:category", text="Judaism")

        owner = ET.SubElement(channel, "itunes:owner")
        ET.SubElement(owner, "itunes:name").text = feed["author"]
        ET.SubElement(owner, "itunes:email").text = feed["email"]

        for entry in entries:
            try:
                pub_date = parser.parse(entry["date"]).strftime("%a, %d %b %Y %H:%M:%S +0000")
            except:
                pub_date = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = entry["title"]
            ET.SubElement(item, "guid", isPermaLink="false").text = entry["id"]
            ET.SubElement(item, "link").text = entry["page_url"]
            ET.SubElement(item, "pubDate").text = pub_date
            ET.SubElement(item, "description").text = entry["title"]
            ET.SubElement(item, "itunes:summary").text = entry["title"]
            ET.SubElement(item, "itunes:subtitle").text = entry["title"]
            ET.SubElement(item, "itunes:explicit").text = "no"
            ET.SubElement(item, "itunes:episodeType").text = "full"
            ET.SubElement(item, "itunes:duration").text = "00:45:00"

            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", entry["audio_url"])
            enclosure.set("length", get_audio_file_size(entry["audio_url"]))
            enclosure.set("type", "audio/mpeg")

        rough_string = ET.tostring(rss, encoding="utf-8")
        reparsed = minidom.parseString(rough_string)
        with open(rss_path, "w", encoding="utf-8") as f:
            f.write(reparsed.toprettyxml(indent="  "))

        print(f"📝 Created RSS feed with {len(entries)} items: {rss_url}")

        if feed["type"] == "torahanytime":
            upload_to_google_sheets([
                [e["title"], e["date"], e["audio_url"], get_audio_file_size(e["audio_url"]), e["page_url"]]
                for e in entries
            ])

    print("🚀 Deploying RSS to Netlify...")
    subprocess.run(
        ["netlify", "deploy", "--prod", "--dir", DEPLOY_FOLDER, "--site", NETLIFY_SITE_ID],
        env={**os.environ, "NETLIFY_AUTH_TOKEN": NETLIFY_AUTH_TOKEN},
        check=True
    )
    print("✅ Deployment complete!")

if __name__ == "__main__":
    fetch_and_save_csv()
    generate_rss()
