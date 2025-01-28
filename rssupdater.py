import xml.etree.ElementTree as ET
import re

# ✅ Set File Paths
rss_file_path = "/Users/matthewmiller/Desktop/reiss.rss"  # Input RSS file
output_file_path = "/Users/matthewmiller/Desktop/reiss_updated.rss"  # Output RSS file

# ✅ Standardized MP3 URL Format
MP3_BASE_URL = "https://download.yutorah.org/{year}/{folder_id}/{shiur_id}/{filename}.mp3"

# ✅ Extract shiur ID from URL
def extract_shiur_id(url):
    match = re.search(r"shiurID=(\d+)", url)
    return match.group(1) if match else None

# ✅ Construct MP3 URL (Year is assumed to be 2025, folder_id is unknown)
def construct_mp3_url(shiur_id):
    return MP3_BASE_URL.format(year="2025", folder_id="UNKNOWN", shiur_id=shiur_id, filename=f"{shiur_id}")

# ✅ Parse RSS XML
tree = ET.parse(rss_file_path)
root = tree.getroot()

# ✅ Iterate over all <item> elements
for item in root.findall(".//item"):
    guid = item.find("guid")
    link = item.find("link")
    
    shiur_id = None
    if guid is not None and guid.text:
        shiur_id = extract_shiur_id(guid.text)
    elif link is not None and link.text:
        shiur_id = extract_shiur_id(link.text)

    if shiur_id:
        mp3_url = construct_mp3_url(shiur_id)

        # ✅ Add <enclosure> tag if missing
        if not item.find("enclosure"):
            enclosure = ET.Element("enclosure")
            enclosure.set("url", mp3_url)
            enclosure.set("length", "0")  # You can fetch actual size if needed
            enclosure.set("type", "audio/mpeg")
            item.append(enclosure)

# ✅ Save Updated RSS
tree.write(output_file_path, encoding="utf-8", xml_declaration=True)
print(f"✅ RSS Updated! Saved to {output_file_path}")