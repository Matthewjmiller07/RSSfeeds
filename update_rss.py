import os
import csv
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

YUTORAH_TEACHERS = [
    {
        "teacher_id": 80153,
        "rss_filename": "hershel_schachter.xml",
        "title": "Rabbi Hershel Schachter Shiurim",
        "author": "Rabbi Hershel Schachter",
        "email": "matthewjmiller07@gmail.com",
        "filter_func": lambda x: True
    },
    {
        "teacher_id": 81012,
        "rss_filename": "efrem_goldberg_parsha.xml",
        "title": "Rabbi Efrem Goldberg - Parsha Shiurim",
        "author": "Rabbi Efrem Goldberg",
        "email": "matthewjmiller07@gmail.com",
        "filter_func": lambda x: "Parsha" in (x.get("categoryname") or [])
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

def upload_to_google_sheets(new_rows, sheet_tab_name="Sheet1"):
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
    except gspread.SpreadsheetNotFound:
        sheet = client.create(GOOGLE_SHEET_NAME)
        sheet.share(creds.service_account_email, perm_type="user", role="writer")

    try:
        worksheet = sheet.worksheet(sheet_tab_name)
    except gspread.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=sheet_tab_name, rows="100", cols="5")

    header = ["Title", "Date", "Audio URL", "File Size", "Page URL", "Duration"]
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
        print(f"✅ Appended {len(appendable)} new rows to sheet tab '{sheet_tab_name}'.")
    else:
        print(f"✅ Sheet tab '{sheet_tab_name}' is already up to date.")

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

def fetch_yutorah_lectures(teacher_id):
    page = 1
    all_lectures = []
    while True:
        query = f"sort_by=shiurdate+desc&organizationID=301&search_query=&page={page}&facet_query=teacherid:{teacher_id},"
        url = f"https://www.yutorah.org/Search/GetSearchResults?{query}"
        response = requests.get(url)
        if not response.ok:
            break
        data = response.json()
        docs = data.get("response", {}).get("docs", [])
        if not docs:
            break
        all_lectures.extend(docs)
        page += 1
        print(f"📄 Fetched page {page} for teacher ID {teacher_id}")
    return all_lectures

def generate_rss():
    import pandas as pd
    os.makedirs(DEPLOY_FOLDER, exist_ok=True)

    # -------- Rav Asher Weiss RSS --------
    rss_path = os.path.join(DEPLOY_FOLDER, "rav_asher_weiss.xml")
    rss_url = f"https://{SITE_NAME}.netlify.app/rav_asher_weiss.xml"
    df = pd.read_csv(CSV_PATH)
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
    write_rss("Rav Asher Weiss' Torah", "Rav Asher Weiss", "matthewjmiller07@gmail.com", rss_url, rss_path, entries)
    upload_to_google_sheets([
        [e["title"], e["date"], e["audio_url"], get_audio_file_size(e["audio_url"]), e["page_url"]] for e in entries
    ])

    # -------- YUTorah RSS Feeds --------
    for teacher in YUTORAH_TEACHERS:
        print(f"📡 Generating RSS for {teacher['title']}...")
        lectures = fetch_yutorah_lectures(teacher["teacher_id"])
        print(f"📦 Fetched {len(lectures)} lectures for {teacher['author']}")
        entries = [
            {
                "id": str(row.get("shiurid")),
                "title": escape_xml(row.get("shiurtitle", "")),
                "date": row.get("shiurdatesubmitted", ""),
                "audio_url": row.get("shiurdownloadurl", ""),
                "page_url": row.get("shiurplayerurl", ""),
                "duration": row.get("durationformatted", "00:45:00")
            }
            for row in lectures if row.get("shiurdownloadurl") and teacher["filter_func"](row)
        ]
        print(f"🔎 {len(entries)} entries passed filters for {teacher['author']}")
        rss_path = os.path.join(DEPLOY_FOLDER, teacher["rss_filename"])
        rss_url = f"https://{SITE_NAME}.netlify.app/{teacher['rss_filename']}"
        write_rss(teacher["title"], teacher["author"], teacher["email"], rss_url, rss_path, entries)
        print(f"✅ RSS written to {rss_path}")

        # Upload to dedicated Google Sheet tab
        upload_to_google_sheets([
        [e["title"], e["date"], e["audio_url"], get_audio_file_size(e["audio_url"]), e["page_url"], e["duration"]]
        for e in entries
    ], sheet_tab_name=teacher["title"])

    print("🚀 Deploying RSS to Netlify...")
    subprocess.run(
        ["netlify", "deploy", "--prod", "--dir", DEPLOY_FOLDER, "--site", NETLIFY_SITE_ID],
        env={**os.environ, "NETLIFY_AUTH_TOKEN": NETLIFY_AUTH_TOKEN},
        check=True
    )
    print("✅ Deployment complete!")

def write_rss(title, author, email, rss_url, rss_path, entries):
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:atom": "http://www.w3.org/2005/Atom"
    })
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = rss_url
    ET.SubElement(channel, "atom:link", href=rss_url, rel="self", type="application/rss+xml")
    ET.SubElement(channel, "description").text = title
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "itunes:author").text = author
    ET.SubElement(channel, "itunes:summary").text = title
    ET.SubElement(channel, "itunes:subtitle").text = title
    ET.SubElement(channel, "itunes:explicit").text = "no"
    ET.SubElement(channel, "itunes:image", href="https://i.imgur.com/hkwQrh9.png")
    image = ET.SubElement(channel, "image")
    ET.SubElement(image, "url").text = "https://i.imgur.com/hkwQrh9.png"
    ET.SubElement(image, "title").text = title
    ET.SubElement(image, "link").text = rss_url
    cat = ET.SubElement(channel, "itunes:category", text="Religion & Spirituality")
    ET.SubElement(cat, "itunes:category", text="Judaism")
    owner = ET.SubElement(channel, "itunes:owner")
    ET.SubElement(owner, "itunes:name").text = author
    ET.SubElement(owner, "itunes:email").text = email
    for i, entry in enumerate(entries, 1):
        print(f"📝 Writing RSS item {i}/{len(entries)}: {entry['title'][:50]}...")
        pub_date = parser.parse(entry["date"]).strftime("%a, %d %b %Y %H:%M:%S +0000") if entry["date"] else datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
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
        ET.SubElement(item, "itunes:duration").text = entry.get("duration", "00:45:00")
        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", entry["audio_url"])
        enclosure.set("length", get_audio_file_size(entry["audio_url"]))
        enclosure.set("type", "audio/mpeg")
    rough_string = ET.tostring(rss, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(reparsed.toprettyxml(indent="  "))

if __name__ == "__main__":
    fetch_and_save_csv()
    generate_rss()
