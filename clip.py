import os
import time
import sqlite3
from urllib.parse import quote

from util import (
    get_video_for_channel,
    generate_clip_id,
    seconds_to_hms,
    send_discord_webhook,
    get_user_details_from_headers,
    get_clip_title
)

DB_PATH = "data/queries.db"
COOKIES_FILE = "/tmp/cookies.txt"

def create_clip(chat_id, query, headers):
    user, level, avatar, user_id, channel_id = get_user_details_from_headers(headers)

    if not channel_id:
        return "❌ Missing or invalid Nightbot-Channel header."

    # Get metadata using yt-dlp
    vid = get_video_for_channel(channel_id)
    if not vid or "start_time" not in vid:
        return "⚠️ No livestream found or failed to fetch stream metadata."

    video_id = vid["original_video_id"]
    stream_start_ts = int(vid["start_time"])
    now_ts = int(time.time())
    delay = int(headers.get("delay", -30))

    # Calculate timestamp into the stream
    clip_timestamp = now_ts - stream_start_ts + delay
    hms = seconds_to_hms(clip_timestamp)

    # Generate clip ID
    clip_id = generate_clip_id(chat_id, clip_timestamp)

    # Create clip URL
    yt_url = f"https://youtu.be/{video_id}?t={clip_timestamp}"

    # Clip title
    title = get_clip_title(query)

    # Save to database
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS clips (id TEXT, title TEXT, ts INTEGER, url TEXT, user TEXT, avatar TEXT, video TEXT)")
    cur.execute("REPLACE INTO clips VALUES (?, ?, ?, ?, ?, ?, ?)",
                (clip_id, title, clip_timestamp, yt_url, user, avatar or "", video_id))
    conn.commit()
    conn.close()

    # Send Discord webhook
    send_discord_webhook(clip_id, title, hms, yt_url, delay, user, level, avatar, channel_id)

    return f"{clip_id} | {yt_url}"

def delete_clip(clip_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT url, video FROM clips WHERE id=?", (clip_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return f"❌ Clip {clip_id} not found."

    yt_url, video_id = row
    cur.execute("DELETE FROM clips WHERE id=?", (clip_id,))
    conn.commit()
    conn.close()

    return f"🗑️ Deleted: {clip_id}"
