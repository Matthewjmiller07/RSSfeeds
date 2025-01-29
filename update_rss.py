import os
import subprocess
import datetime
import requests
import json
from urllib.parse import quote
from dateutil import parser

# ✅ Load Netlify Secrets
NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")
NETLIFY_SITE_ID = os.getenv("NETLIFY_SITE_ID")

if not NETLIFY_AUTH_TOKEN or not NETLIFY_SITE_ID:
    raise ValueError("❌ Missing NETLIFY_AUTH_TOKEN or NETLIFY_SITE_ID! Set them as environment variables.")

print(f"🔑 Using Netlify Site ID: {NETLIFY_SITE_ID}")

# ✅ Define Netlify Deployment Variables
site_name = "yutorah-rss"
deploy_folder = "deploy_netlify"
rss_feeds = {
    "reiss_daf_podcast.xml": {
        "search_query": "R' Reiss Dayan's Daf",
        "organizationID": 301,
        "source": "yutorah",
    },
    "rav_asher_weiss.xml": {
        "speaker_id": 860,  # TorahAnytime Speaker ID for Rav Asher Weiss
        "source": "torahanytime",
    },
    "shearim_b_tefillah.xml": {
        "search_query": "She'arim B'Tefillah",
        "organizationID": 1863,
        "source": "yutorah",
    },

# ✅ Ensure Deployment Directory Exists
os.makedirs(deploy_folder, exist_ok=True)

# ✅ Create `netlify.toml`
netlify_toml = """\
[[headers]]
  for = "/*.xml"
  [headers.values]
  Content-Type = "application/xml; charset=UTF-8"
"""
with open(os.path.join(deploy_folder, "netlify.toml"), "w") as f:
    f.write(netlify_toml)

print("✅ Created `netlify.toml`.")

# ✅ Function to Escape XML Characters
def escape_xml(text):
    if not isinstance(text, str):
        text = str(text)
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))

# ✅ Function to Get Audio File Size
def get_audio_file_size(url):
    try:
        response = requests.head(url, timeout=5)
        file_size = response.headers.get("Content-Length", "0")
        return file_size if file_size.isdigit() else "0"
    except requests.RequestException:
        return "0"

# ✅ Function to Fetch and Generate RSS Feeds
def generate_rss_feed(feed_name, feed_data):
    print(f"📡 Fetching new episodes for {feed_name}...")
    rss_file_path = os.path.join(deploy_folder, feed_name)

    if os.path.exists(rss_file_path):
        with open(rss_file_path, "r", encoding="utf-8") as f:
            existing_rss = f.read()
    else:
        existing_rss = ""

    if feed_data["source"] == "yutorah":
        base_url = "https://www.yutorah.org/Search/GetSearchResults"
        params = {
            "sort_by": "shiurdate desc",
        }

        if "organizationID" in feed_data:
            params["organizationID"] = feed_data["organizationID"]
            params["search_query"] = quote(feed_data["search_query"])

        if "teacherID" in feed_data and "collectionID" in feed_data:
            params["teacherID"] = feed_data["teacherID"]
            params["collectionID"] = feed_data["collectionID"]

        headers = {"accept": "application/json", "user-agent": "Mozilla/5.0"}
        response = requests.get(base_url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            new_episodes = data.get("response", {}).get("docs", [])
        else:
            print(f"❌ Error fetching YUTorah data: {response.status_code}")
            new_episodes = []

    elif feed_data["source"] == "torahanytime":
        speaker_id = feed_data["speaker_id"]
        url = f"https://trpc.torahanytime.com/website.speakerPage.lectureList.getLectures?batch=1&input={{\"0\":{{\"speakerId\":{speaker_id},\"limit\":10000,\"offset\":0,\"sortDirection\":\"DESC\"}}}}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            new_episodes = data[0].get("result", {}).get("data", [])
        else:
            print(f"❌ Error fetching TorahAnytime data: {response.status_code}")
            new_episodes = []

    else:
        print(f"❌ Unknown source for {feed_name}")
        return

    print(f"📡 Found {len(new_episodes)} new episodes for {feed_name}")

    # ✅ Generate RSS Content
    rss_content = f'''<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
      <channel>
        <title>{escape_xml(feed_name.replace(".xml", "").replace("_", " "))}</title>
        <link>https://{site_name}.netlify.app/{feed_name}</link>
        <description>{escape_xml(f"Shiurim by {feed_name.replace('.xml', '').replace('_', ' ')}")}</description>
        <language>en-us</language>
        <itunes:author>{escape_xml(feed_name.replace('.xml', '').replace('_', ' '))}</itunes:author>
        <itunes:explicit>no</itunes:explicit>
        <itunes:category text="Religion &amp; Spirituality">
          <itunes:category text="Judaism"/>
        </itunes:category>
    '''

    for shiur in new_episodes:
        title = escape_xml(shiur.get("shiurtitle", shiur.get("title", "Untitled Episode")))
        episode_page_url = shiur.get("shiurdownloadurl", shiur.get("media"))
        guid = str(shiur.get("shiurid", shiur.get("id", "")))

        if guid in existing_rss:
            print(f"⚠️ Skipping duplicate episode '{title}'")
            continue

        audio_url = shiur.get("shiurdownloadurl", "")
        if not audio_url:
            print(f"⚠️ Skipping '{title}' - No audio URL")
            continue

        file_size = get_audio_file_size(audio_url)
        raw_date = shiur.get("shiurdateformatted", shiur.get("date_recorded", "")).strip()

        try:
            parsed_date = parser.parse(raw_date)
            pub_date = parsed_date.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except (ValueError, TypeError):
            pub_date = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

        rss_content += f'''
        <item>
          <title>{title}</title>
          <guid isPermaLink="false">{guid}</guid>
          <link>{episode_page_url}</link>
          <enclosure url="{audio_url}" length="{file_size}" type="audio/mpeg"/>
          <itunes:duration>00:29:00</itunes:duration>
          <pubDate>{pub_date}</pubDate>
        </item>
    '''

    rss_content += '''
      </channel>
    </rss>
    '''

    with open(rss_file_path, "w", encoding="utf-8") as f:
        f.write(rss_content)

    print(f"✅ RSS Updated for {feed_name}!")

# ✅ Generate Feeds
for feed_name, feed_data in rss_feeds.items():
    generate_rss_feed(feed_name, feed_data)

# ✅ Deploy to Netlify
print("📤 Deploying Site to Netlify...")
subprocess.run(
    ["netlify", "deploy", "--prod", "--dir", deploy_folder, "--site", NETLIFY_SITE_ID],
    env={**os.environ, "NETLIFY_AUTH_TOKEN": NETLIFY_AUTH_TOKEN},
    check=True
)
print("✅ Deployment Complete!")
