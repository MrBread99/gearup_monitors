import requests
from datetime import datetime, timezone, timedelta

def check_epic_games_history():
    print("Checking Epic Games historical status (via archive if possible, otherwise just current to see if it supports time travel)...")
    url = "https://status.epicgames.com/api/v2/summary.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print("Successfully fetched Epic summary.")
            data = response.json()
            # Incidents usually hold recent history
            incidents = data.get('incidents', [])
            print(f"Found {len(incidents)} recent incidents in Epic API.")
            for inc in incidents:
                print(f" - {inc.get('name')} | Created at: {inc.get('created_at')}")
    except Exception as e:
        print(f"Epic Error: {e}")

def check_reddit_history():
    print("\nChecking Reddit search behavior for historical limits...")
    # Attempt to search specifically around the 14th
    # Reddit search API doesn't easily support arbitrary historical date ranges without Pushshift (which is dead) or advanced queries
    url = "https://www.reddit.com/r/GlobalOffensive/search.json?q=server+OR+ping+OR+lag&restrict_sr=on&sort=new&t=week"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Monitor/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            print(f"Successfully fetched {len(posts)} posts from past week on Reddit.")
            for post in posts[:3]: # look at the first few
                created = datetime.fromtimestamp(post['data']['created_utc'], timezone.utc)
                print(f" - Post on {created.strftime('%Y-%m-%d %H:%M:%S')}: {post['data'].get('title')[:50]}...")
    except Exception as e:
        print(f"Reddit Error: {e}")

if __name__ == "__main__":
    check_epic_games_history()
    check_reddit_history()
