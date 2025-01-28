from flask import Flask, request, jsonify
import requests
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

YUTORAH_API_URL = "https://www.yutorah.org/Search/GetSearchResults"

def safe_join(value):
    """Ensure value is a list before joining elements."""
    if isinstance(value, list):
        return ", ".join(value)
    return str(value) if value else ""

@app.route("/search")
def search():
    query = request.args.get("q", "").strip().lower()
    teacher = request.args.get("teacher", "").strip().lower()
    category = request.args.get("category", "").strip().lower()

    if not query and not teacher:
        return jsonify({"error": "At least one of 'q' (title) or 'teacher' is required"}), 400

    results = []
    page = 1
    MAX_PAGES = 10000  # 🚀 Increased limit for deeper search
    MAX_RESULTS = 1000  # 🚀 Stop when we get enough results
    found_results = 0

    while page <= MAX_PAGES and found_results < MAX_RESULTS:
        print(f"\n🔍 Fetching page {page} for query '{query}' and teacher '{teacher}'")

        params = {
            "sort_by": "shiurdate desc",
            "organizationID": 301,
            "search_query": query if query else "",
            "page": page
        }

        headers = {
            "accept": "application/json",
            "user-agent": "Mozilla/5.0"
        }

        response = requests.get(YUTORAH_API_URL, headers=headers, params=params)
        if response.status_code != 200:
            print(f"❌ API error {response.status_code}: {response.text}")
            return jsonify({"error": f"Failed to fetch data. Status: {response.status_code}"}), 500

        data = response.json()
        if "response" not in data or "docs" not in data["response"]:
            print(f"🚫 No more results from API. Stopping pagination.")
            break  # API has no more results

        shiurim = data["response"]["docs"]
        if not shiurim:
            print(f"⚠️ No results on page {page}. Stopping.")
            break  # No more results, stop early

        print(f"📦 Retrieved {len(shiurim)} results on page {page} (before filtering)")

        page_results = []
        skipped_count = 0  # Track skipped items

        for shiur in shiurim:
            teacher_name = safe_join(shiur.get("teacherfullname", [])).lower()
            title = shiur.get("shiurtitle", "").lower()
            categories = safe_join(shiur.get("categoryname", [])).lower()

            # Step 1️⃣: First filter by Teacher (if provided)
            if teacher and teacher not in teacher_name:
                skipped_count += 1
                continue

            # Step 2️⃣: Then filter by Title (if provided)
            if query and query not in title:
                skipped_count += 1
                continue

            # ✅ If it passes all filters, add to results
            page_results.append({
                "id": shiur.get("shiurid"),
                "title": shiur.get("shiurtitle"),
                "teacher": teacher_name.title(),
                "categories": categories.title(),
                "series": safe_join(shiur.get("seriesname")),
                "duration": shiur.get("durationformatted", ""),
                "download_url": shiur.get("shiurdownloadurl"),
                "player_url": shiur.get("shiurplayerurl"),
                "date": shiur.get("shiurdateformatted"),
                "keywords": shiur.get("shiurkeywords"),
                "image": f"https://www.yutorah.org/photos/{shiur.get('photo', [''])[0]}" if shiur.get("photo") else None
            })

        results.extend(page_results)
        found_results += len(page_results)

        print(f"✅ Found {len(page_results)} matching results on page {page} (Total so far: {found_results})")

        if found_results >= MAX_RESULTS:
            print(f"🚀 Stopping early: Reached {MAX_RESULTS} results.")
            break  # Stop early once we have enough results

        page += 1  # Move to next page

    print(f"🚀 Done! Returning {len(results)} total results after filtering.\n")
    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True)