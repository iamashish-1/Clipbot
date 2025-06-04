import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
import scrapetube
from urllib.parse import parse_qs

DB_PATH = "data/queries.db"
COOKIES_FILE = "/tmp/cookies.txt"

role_icons = {
    "moderator": "🛡️",
    "owner": "👑",
    "member": "💎",
    "": ""
}

def get_user_details_from_headers(headers):
    try:
        channel = parse_qs(headers["Nightbot-Channel"])
        user = parse_qs(headers["Nightbot-User"])
    except KeyError:
        print("❌ Required Nightbot headers not found.")
        return None, None, None, None, None

    try:
        channel_id = channel.get("providerId", [None])[0]
        user_id = user.get("providerId", [None])[0]
        user_level = user.get("userLevel", [""])[0].lower()
        user_name = user.get("displayName", ["Unknown"])[0].replace("+", " ")
    except Exception as e:
        print("❌ Failed to parse Nightbot headers:", e)
        return None, None, None, None, None

    avatar = fetch_avatar(user_id) if user_id else None

    return user_name, user_level, avatar, user_id, channel_id

def fetch_avatar(channel_id):
    try:
        url = f"https://www.youtube.com/channel/{channel_id}"
        r = requests.get(url, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.find("meta", property="og:image")["content"]
    except Exception as e:
        print("Failed to fetch avatar:", e)
        return None

def get_video_for_channel(channel_id):
    try:
        print(f"🔍 Checking live videos for: {channel_id}")
        vids = scrapetube.get_channel(channel_id, content_type="streams", limit=2, sleep=0)
        for vid in vids:
            if vid["thumbnailOverlays"][0]["thumbnailOverlayTimeStatusRenderer"]["style"] == "LIVE":
                video_id = vid["videoId"]
                print("🎥 Live stream found:", video_id)
                return get_video_metadata(video_id)
        print("⚠️ No live video found for this channel.")
    except Exception as e:
        print("❌ scrapetube or yt-dlp error:", e)
    return None

def get_video_metadata(video_id):
    retries = 2
    delay_seconds = 3
    cookies_path = "/tmp/cookies.txt"  # Update if stored elsewhere

    for attempt in range(retries):
        try:
            print(f"📺 Getting metadata for video: {video_id} (Attempt {attempt + 1})")
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "cookies": cookies_path
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                start_time = int(info.get("release_timestamp", time.time()))
                return {
                    "video_id": video_id,
                    "original_video_id": video_id,
                    "start_time": start_time
                }
        except Exception as e:
            print(f"❌ yt-dlp failed (attempt {attempt + 1}):", e)
            if attempt < retries - 1:
                print(f"⏳ Retrying in {delay_seconds} seconds...")
                time.sleep(delay_seconds)

    print("❌ All attempts to fetch video metadata failed.")
    return None


def generate_clip_id(chat_id, timestamp):
    return chat_id[-3:].upper() + str(timestamp % 100000)

def seconds_to_hms(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02}:{s:02}"

def send_discord_webhook(clip_id, title, hms, url, delay, user, level, avatar, channel_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT webhook FROM settings WHERE channel=?", (channel_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return False

    webhook = row[0]
    emoji = role_icons.get(level.lower(), "")
    username = f"{user} {emoji}".strip()

    message = f"{clip_id} | {title}\n\n{hms}\n{url}\n\nDelayed by {delay} seconds."
    payload = {
        "username": username,
        "content": message
    }
    if avatar and avatar.startswith("https://"):
        payload["avatar_url"] = avatar
        print("Webhook avatar URL used:", avatar)

    try:
        r = requests.post(webhook, json=payload)
        return r.status_code in [200, 204]
    except Exception as e:
        print("Webhook send error:", e)
        return False

def get_clip_title(query):
    return query.replace("+", " ") if query else "Untitled"
