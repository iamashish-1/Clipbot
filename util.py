import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
from chat_downloader import ChatDownloader
from chat_downloader.sites import YouTubeChatDownloader
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
    user_header = headers.get("Nightbot-User", "")
    user = "Unknown"
    level = ""
    avatar = None
    user_id = ""

    if user_header:
        try:
            parts = parse_qs(user_header)
            user = parts.get("displayName", ["Unknown"])[0].replace("+", " ")
            level = parts.get("userLevel", [""])[0].lower()
            user_id = parts.get("providerId", [""])[0]
            avatar = fetch_avatar(user_id)
        except Exception as e:
            print("Failed to parse Nightbot-User header:", e)

    return user, level, avatar, user_id

def fetch_avatar(channel_id):
    try:
        url = f"https://www.youtube.com/channel/{channel_id}"
        r = requests.get(url, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.find("meta", property="og:image")["content"]
    except Exception as e:
        print("Failed to fetch avatar:", e)
        return None

def get_video_for_chat(chat_id, fallback_channel_id=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS chat_mapping (chat TEXT, video TEXT)")
        cur.execute("SELECT video FROM chat_mapping WHERE chat=?", (chat_id,))
        row = cur.fetchone()
        conn.close()

        if row:
            vid_id = row[0]
            try:
                print("📦 Using cached mapping for chat_id:", chat_id, "→", vid_id)
                return YouTubeChatDownloader(cookies=COOKIES_FILE).get_video_data(video_id=vid_id)
            except Exception as e:
                print("❌ YouTubeChatDownloader failed (cached):", e)

    except Exception as e:
        print("DB fetch error:", e)

    # Fallback to provided channel ID only
    if fallback_channel_id:
        try:
            print(f"🔍 Checking live videos for: {fallback_channel_id}")
            vids = scrapetube.get_channel(fallback_channel_id, content_type="streams", limit=2, sleep=0)

            for vid in vids:
                if vid["thumbnailOverlays"][0]["thumbnailOverlayTimeStatusRenderer"]["style"] == "LIVE":
                    vid_id = vid["videoId"]
                    print("🎥 Live stream found:", vid_id)

                    try:
                        chat_stream = ChatDownloader().get_chat(vid_id)
                        for message in chat_stream:
                            if message.get("chat_id") == chat_id:
                                print("✅ Chat ID matched. Mapping now.")
                                conn = sqlite3.connect(DB_PATH)
                                cur = conn.cursor()
                                cur.execute("REPLACE INTO chat_mapping VALUES (?, ?)", (chat_id, vid_id))
                                conn.commit()
                                conn.close()
                                return YouTubeChatDownloader(cookies=COOKIES_FILE).get_video_data(video_id=vid_id)
                        print("⚠️ Chat ID not found in stream chat.")
                    except Exception as e:
                        print("⚠️ Failed to get chat from video:", vid_id)
                        print("❌ Error:", e)

        except Exception as e:
            print("⚠️ scrapetube or ChatDownloader outer error:", e)

    print("⚠️ No valid live video found.")
    return None


def generate_clip_id(chat_id, timestamp):
    return chat_id[-3:].upper() + str(timestamp % 100000)

def seconds_to_hms(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02}:{s:02}"

def send_discord_webhook(clip_id, title, hms, url, delay, user, level, avatar, video_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT webhook FROM settings WHERE channel=?", (video_id,))
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
