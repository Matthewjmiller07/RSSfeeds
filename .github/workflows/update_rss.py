import os
import subprocess
import time
import datetime
from dateutil import parser
import requests

# ✅ Set Netlify API Token (Provided by GitHub Actions)
NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")

# ✅ Define Netlify Site & RSS Feeds
site_name = "yutorah-rss"
rss_file_name = "reiss_daf_podcast.xml"
deploy_folder = "deploy_netlify"
rss_file_path = os.path.join(deploy_folder, rss_file_name)

# ✅ Ensure Temporary Deployment Directory Exists
os.makedirs(deploy_folder, exist_ok=True)

# ✅ Create `netlify.toml` to ensure XML files are served correctly
netlify_toml = """\
[[headers]]
  for = "/*.xml"
  [headers.values]
  Content-Type = "application/xml; charset=UTF-8"
"""
with open(os.path.join(deploy_folder, "netlify.toml"), "w") as f:
    f.write(netlify_toml)

print("✅ Created `netlify.toml` to serve XML files correctly.")

# ✅ Function to Escape Invalid XML Characters
def escape_xml(text):
    """Replaces invalid XML characters with safe equivalents"""
    if not isinstance(text, str):
        text = str(text)  # Ensure it's a string
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))

# ✅ Function to Get Audio File Size
def get_audio_file_size(url):
    """Fetch the file size of an MP3 from its URL for RSS compliance"""
    try:
        response = requests.head(url, timeout=5)
        file_size = response.headers.get("Content-Length", "0")
        return file_size if file_size.isdigit() else "0"
    except requests.RequestException:
        return "0"

# ✅ Fetch Latest Episodes
base_url = "https://www.yutorah.org/Search/GetSearchResults"
params = {
    "sort_by": "shiurdate desc",
    "organizationID": 301,
    "search_query": "R' Reiss Dayan's Daf",
    "page": 1
}

headers = {
    "accept": "application/json",
    "user-agent": "Mozilla/5.0",
    "x-requested-with": "XMLHttpRequest"
}

response = requests.get(base_url, headers=headers, params=params)
data = response.json()
new_episodes = data.get("response", {}).get("docs", [])

print(f"📡 Found {len(new_episodes)} new episodes from YUTorah API")

# 🔍 **Debugging: Print the first 5 fetched episodes**
for episode in new_episodes[:5]:
    print(f"🎙 Title: {episode.get('shiurtitle', 'Unknown')}")
    print(f"📅 Date: {episode.get('shiurdateformatted', 'Unknown')}")
    print(f"🔗 Audio URL: {episode.get('shiurdownloadurl', 'MISSING')}")
    print("-" * 60)

# ✅ Generate Apple-Compliant RSS Feed XML
PODCAST_TITLE = escape_xml("R' Reiss Dayan's Daf Yomi")
PODCAST_DESCRIPTION = escape_xml("Daily Daf Yomi shiurim by R' Reiss Dayan.")
PODCAST_LINK = f"https://{site_name}.netlify.app/{rss_file_name}"
PODCAST_AUTHOR = escape_xml("R' Reiss Dayan")

rss_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{PODCAST_TITLE}</title>
    <link>{PODCAST_LINK}</link>
    <description>{PODCAST_DESCRIPTION}</description>
    <language>en-us</language>
    <itunes:author>{PODCAST_AUTHOR}</itunes:author>
    <itunes:owner>
      <itunes:name>{PODCAST_AUTHOR}</itunes:name>
      <itunes:email>your-email@example.com</itunes:email>
    </itunes:owner>
    <itunes:explicit>no</itunes:explicit>
    <itunes:category text="Religion &amp; Spirituality">
      <itunes:category text="Judaism"/>
    </itunes:category>
    <itunes:image href="https://yourpodcastcoverimageurl.com/cover.jpg" />
'''

episode_count = 0
for shiur in new_episodes:
    title = escape_xml(shiur.get("shiurtitle", "Untitled Episode"))
    audio_url = shiur.get("shiurdownloadurl", "")

    if not audio_url:
        print(f"⚠️ Skipping episode '{title}' - No audio URL found!")
        continue  # Skip if no audio

    file_size = get_audio_file_size(audio_url)
    episode_page_url = f"https://www.yutorah.org/{shiur.get('shiurid', '')}/"

    raw_date = shiur.get("shiurdateformatted", "").strip()
    try:
        parsed_date = parser.parse(raw_date)
        pub_date = parsed_date.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except (ValueError, TypeError):
        print(f"⚠️ WARNING: Invalid date format for '{title}'. Using current date.")
        pub_date = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

    rss_content += f'''
    <item>
      <title>{title}</title>
      <guid isPermaLink="false">{escape_xml(str(shiur.get("shiurid", episode_count)))}</guid>
      <link>{episode_page_url}</link>
      <enclosure url="{audio_url}" length="{file_size}" type="audio/mpeg"/>
      <itunes:duration>00:29:00</itunes:duration>
      <itunes:subtitle>Summary of {title}</itunes:subtitle>
      <itunes:summary>Detailed summary of {title} episode.</itunes:summary>
      <pubDate>{pub_date}</pubDate>
    </item>
'''
    episode_count += 1

rss_content += '''
  </channel>
</rss>
'''

# ✅ Save RSS Feed to Deploy Folder
with open(rss_file_path, "w", encoding="utf-8") as f:
    f.write(rss_content)

print(f"✅ RSS Updated! Total Episodes: {episode_count}")

# ✅ Deploy to Netlify
def run_command(command, description):
    """Run a shell command with logging and failure detection"""
    print(f"🔄 {description}...")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ ERROR: {description} failed!\n{result.stderr}")
        exit(1)

    print(f"✅ {description} successful!")
    return result.stdout.strip()

# ✅ Deploy Site to Netlify
print("📤 Deploying Site to Netlify...")
deploy_output = run_command(f"netlify deploy --prod --dir='{deploy_folder}'", "Deploying Site")

# ✅ Extract & Print Deployed Site URL
site_url = None
for line in deploy_output.split("\n"):
    if "Website URL:" in line:
        site_url = line.split("Website URL:")[1].strip()
        print(f"🎙 Your RSS Feed is Live at: 🔗 {site_url}/{rss_file_name}")
        break

# ✅ Final Check
if site_url:
    print(f"✅ Deployment Successful! RSS feed available at {site_url}/{rss_file_name}")
else:
    print(f"⚠️ Deployment failed. Fetching Netlify logs for details...")
    run_command("netlify logs", "Fetching Netlify Logs")

time.sleep(5)
