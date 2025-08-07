import os
import csv
import requests
import datetime
import subprocess
import time
import gspread
import pandas as pd
import xml.etree.ElementTree as ET
from dateutil import parser
from xml.dom import minidom
from google.oauth2.service_account import Credentials

# ---------------- CONFIG ---------------- #

SITE_NAME = "yutorah-rss"
DEPLOY_FOLDER = "deploy_netlify"
GOOGLE_SHEET_NAME = "Rav Asher Weiss Shiurim"

NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")
NETLIFY_SITE_ID = os.getenv("NETLIFY_SITE_ID")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "service_account.json")

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
    """Makes a HEAD request to get the content length of a URL."""
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        r.raise_for_status()
        return r.headers.get("Content-Length", "0") or "0"
    except requests.RequestException as e:
        print(f"⚠️  Could not get file size for {url}. Error: {e}")
        return "0"

# --- NEW: ROBUST DURATION FORMATTER ---
def format_duration(raw_duration):
    """
    Safely converts a duration value into HH:MM:SS format.
    - Handles integers (total seconds).
    - Handles existing "HH:MM:SS" strings.
    - Handles None or other unexpected types gracefully.
    """
    # Case 1: Duration is an integer (e.g., 3661)
    if isinstance(raw_duration, int):
        # Use gmtime to convert seconds into a time structure, then format it
        return time.strftime('%H:%M:%S', time.gmtime(raw_duration))

    # Case 2: Duration is a string
    if isinstance(raw_duration, str):
        # If it already looks like HH:MM:SS, just return it
        if ':' in raw_duration:
            return raw_duration
        # If it's a string of digits, convert to int and then format
        elif raw_duration.isdigit():
            return time.strftime('%H:%M:%S', time.gmtime(int(raw_duration)))

    # Case 3: Handle None or any other unexpected format
    return "00:00:00"

def upload_to_google_sheets(new_rows, sheet_tab_name, sheet):
    # This function is correct and does not need changes.
    # ... (function body remains the same)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            try:
                worksheet = sheet.worksheet(sheet_tab_name)
            except gspread.WorksheetNotFound:
                print(f"📄 Tab '{sheet_tab_name}' not found. Creating it...")
                worksheet = sheet.add_worksheet(title=sheet_tab_name, rows="100", cols="6")

            header = ["Title", "Date", "Audio URL", "File Size", "Page URL", "Duration"]
            values = worksheet.get_all_values()

            if not values or values[0] != header:
                print("📋 Header is missing or incorrect. Clearing sheet and adding new header.")
                worksheet.clear()
                worksheet.append_row(header, value_input_option="USER_ENTERED")
                existing_keys = set()
            else:
                existing_keys = set((row[0], row[1]) for row in values[1:] if len(row) >= 2)

            appendable = [row for row in new_rows if (row[0], row[1]) not in existing_keys]

            if appendable:
                worksheet.append_rows(appendable, value_input_option="USER_ENTERED")
                print(f"✅ Appended {len(appendable)} new rows to sheet tab '{sheet_tab_name}'.")
            else:
                print(f"✅ Sheet tab '{sheet_tab_name}' is already up to date.")

            return # Success, exit the function

        except gspread.exceptions.APIError as e:
            if e.response.status_code in [500, 502, 503, 504] and attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                print(f"⚠️ Google Sheets API error ({e.response.status_code}). Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"❌ A critical Google Sheets API error occurred after {attempt + 1} attempts.")
                raise e
        except Exception as e:
            print(f"❌ An unexpected error occurred during Google Sheets upload: {e}")
            raise e


# ---------------- DATA FETCHING ---------------- #

def fetch_torahanytime_lectures(speaker_id):
    # This function is correct and does not need changes.
    # ... (function body remains the same)
    url = f"https://api.torahanytime.com/speakers/{speaker_id}/lectures?limit=10000"
    try:
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json().get("lecture", [])
        print(f"📥 Fetched {len(data)} lectures for speaker ID {speaker_id}.")
        return data
    except requests.RequestException as e:
        print(f"❌ Error fetching data for speaker {speaker_id}: {e}")
        return []

def fetch_yutorah_lectures(teacher_id):
    # This function is correct and does not need changes.
    # ... (function body remains the same)
    page = 1
    all_lectures = []
    while True:
        query = f"sort_by=shiurdate+desc&organizationID=301&search_query=&page={page}&facet_query=teacherid:{teacher_id},"
        url = f"https://www.yutorah.org/Search/GetSearchResults?{query}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            docs = data.get("response", {}).get("docs", [])
            if not docs:
                break
            all_lectures.extend(docs)
            print(f"📄 Fetched page {page} for teacher ID {teacher_id}")
            page += 1
        except requests.RequestException as e:
            print(f"❌ Error fetching YUTorah page {page} for teacher {teacher_id}: {e}")
            break
    return all_lectures

# ---------------- RSS & DEPLOYMENT ---------------- #

def write_rss(title, author, email, rss_url, rss_path, entries):
    # This function is correct and does not need changes.
    # ... (function body remains the same)
    rss = ET.Element("rss", {
        "version": "2.0", "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd", "xmlns:atom": "http://www.w3.org/2005/Atom"
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
        # This print statement is removed from the final script to reduce log noise
        # print(f"📝 Writing RSS item {i}/{len(entries)}: {entry['title'][:50]}...")
        pub_date_str = entry.get("date")
        pub_date = parser.parse(pub_date_str).strftime("%a, %d %b %Y %H:%M:%S +0000") if pub_date_str else datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
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
        ET.SubElement(item, "itunes:duration").text = entry.get("duration", "00:00:00")
        enclosure = ET.SubElement(item, "enclosure", {
            "url": entry["audio_url"], "length": entry["file_size"], "type": "audio/mpeg"
        })

    rough_string = ET.tostring(rss, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(reparsed.toprettyxml(indent="  "))
    print(f"✅ RSS written to {rss_path}")

def main():
    """Main function to generate RSS feeds and upload data."""
    os.makedirs(DEPLOY_FOLDER, exist_ok=True)
    
    # --- Authenticate with Google Sheets ONCE ---
    print("🔑 Authorizing with Google Sheets...")
    if not GOOGLE_SHEETS_CREDENTIALS or not os.path.exists(GOOGLE_SHEETS_CREDENTIALS):
        print("❌ Missing Google Sheets credentials. Skipping sheet uploads.")
        google_sheet = None
    else:
        try:
            creds = Credentials.from_service_account_file(
                GOOGLE_SHEETS_CREDENTIALS,
                scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
            )
            client = gspread.authorize(creds)
            google_sheet = client.open(GOOGLE_SHEET_NAME)
            print("✅ Successfully connected to Google Sheet.")
        except Exception as e:
            print(f"❌ Failed to connect to Google Sheets: {e}")
            google_sheet = None

    # --- Process TorahAnytime Speakers ---
    speakers = [
        {"id": 860, "filename": "rav_asher_weiss.xml", "title": "Rav Asher Weiss' Torah", "author": "Rav Asher Weiss", "email": "matthewjmiller07@gmail.com"},
        {"id": 982, "filename": "shmuel_fuerst.xml", "title": "Rabbi Shmuel Fuerst's Torah", "author": "Rabbi Shmuel Fuerst", "email": "matthewjmiller07@gmail.com"}
    ]
    
    for speaker in speakers:
        print(f"\n📡 Processing TorahAnytime Speaker: {speaker['author']}...")
        lectures = fetch_torahanytime_lectures(speaker['id'])
        if not lectures:
            continue

        entries = []
        for lec in lectures:
            if not lec.get("mp3_url"):
                continue
            
            # --- FIX: Use the robust formatter on the duration value ---
            clean_duration = format_duration(lec.get('duration'))
            
            entries.append({
                "id": str(lec["id"]), 
                "title": escape_xml(lec["title"]), 
                "date": lec["date_recorded"],
                "audio_url": lec["mp3_url"], 
                "page_url": f"https://www.torahanytime.com/lectures/{lec['id']}",
                "duration": clean_duration,  # <-- Use the cleaned duration here
                "file_size": get_audio_file_size(lec["mp3_url"])
            })

        rss_path = os.path.join(DEPLOY_FOLDER, speaker["filename"])
        rss_url = f"https://{SITE_NAME}.netlify.app/{speaker['filename']}"
        write_rss(speaker["title"], speaker["author"], speaker["email"], rss_url, rss_path, entries)
        
        if google_sheet:
            sheet_rows = [[e["title"], e["date"], e["audio_url"], e["file_size"], e["page_url"], e["duration"]] for e in entries]
            upload_to_google_sheets(sheet_rows, speaker["author"], google_sheet)

    # --- Process YUTorah Teachers ---
    for teacher in YUTORAH_TEACHERS:
        print(f"\n📡 Processing YUTorah Teacher: {teacher['author']}...")
        lectures = fetch_yutorah_lectures(teacher["teacher_id"])
        filtered_lectures = [lec for lec in lectures if lec.get("shiurdownloadurl") and teacher["filter_func"](lec)]
        print(f"📦 Fetched {len(lectures)} lectures, {len(filtered_lectures)} passed filters.")

        if not filtered_lectures:
            continue

        entries = []
        for lec in filtered_lectures:
            audio_url = lec.get("shiurdownloadurl")

            # --- FIX: Use the robust formatter here too for safety and consistency ---
            clean_duration = format_duration(lec.get('durationformatted'))

            entries.append({
                "id": str(lec.get("shiurid")), 
                "title": escape_xml(lec.get("shiurtitle", "")),
                "date": lec.get("shiurdatesubmitted", ""), 
                "audio_url": audio_url,
                "page_url": lec.get("shiurplayerurl", ""), 
                "duration": clean_duration, # <-- Use the cleaned duration here
                "file_size": get_audio_file_size(audio_url)
            })

        rss_path = os.path.join(DEPLOY_FOLDER, teacher["rss_filename"])
        rss_url = f"https://{SITE_NAME}.netlify.app/{teacher['rss_filename']}"
        write_rss(teacher["title"], teacher["author"], teacher["email"], rss_url, rss_path, entries)

        if google_sheet:
            sheet_rows = [[e["title"], e["date"], e["audio_url"], e["file_size"], e["page_url"], e["duration"]] for e in entries]
            upload_to_google_sheets(sheet_rows, teacher["title"], google_sheet)

    # --- Deploy to Netlify ---
    print("\n🚀 Deploying RSS to Netlify...")
    if NETLIFY_AUTH_TOKEN and NETLIFY_SITE_ID:
        try:
            subprocess.run(
                ["netlify", "deploy", "--prod", "--dir", DEPLOY_FOLDER, "--site", NETLIFY_SITE_ID],
                env={**os.environ, "NETLIFY_AUTH_TOKEN": NETLIFY_AUTH_TOKEN},
                check=True, capture_output=True, text=True
            )
            print("✅ Deployment complete!")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("❌ Deployment failed.")
            if isinstance(e, subprocess.CalledProcessError):
                print(f"Stderr: {e.stderr}")
    else:
        print("ℹ️  Skipping deployment: Netlify token or site ID not set.")


if __name__ == "__main__":
    main()
