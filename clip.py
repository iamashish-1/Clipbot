import os
import time
import sqlite3
from urllib.parse import quote

from util import (
    get_video_for_chat,
    generate_clip_id,
    seconds_to_hms,
    send_discord_webhook,
    get_user_details_from_headers,
    get_clip_title
)

DB_PATH = "data/queries.db"
COOKIES_FILE = "/tmp/cookies.txt"

def create_clip(chat_id, query, headers):
    # Get user info from Nightbot headers
    user, level, avatar, user_id = get_user_details_from_headers(headers)

    # Resolve live stream from chat ID, fallback to user's channel if needed
    vid = get_video_for_chat(chat_id, fallback_channel_id=user_id)
    if not vid or "start_time" not in vid:
        return "⚠️ No LiveStream Found. or failed to fetch the stream. Please try again later."

    video_id = vid["original_video_id"]
    stream_start_us = int(vid["start_time"])
    now_us = int(time.time() * 1_000_000)
    delay = int(headers.get("delay", -30))

    # Calculate clip timestamp
    clip_timestamp = (now_us - stream_start_us) // 1_000_000 + delay
    hms = seconds_to_hms(clip_timestamp)

    # Clip ID
    clip_id = generate_clip_id(chat_id, clip_timestamp)

    # Clip URL
    t_param = int(clip_timestamp)
    yt_url = f"https://youtu.be/{video_id}?t={t_param}"

    # Title
    title = get_clip_title(query)

    # Store in DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS clips (id TEXT, title TEXT, ts INTEGER, url TEXT, user TEXT, avatar TEXT, video TEXT)")
    cur.execute("REPLACE INTO clips VALUES (?, ?, ?, ?, ?, ?, ?)",
                (clip_id, title, t_param, yt_url, user, avatar or "", video_id))
    conn.commit()
    conn.close()

    # Send webhook
    send_discord_webhook(clip_id, title, hms, yt_url, delay, user, level, avatar, video_id)

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

    # Delete from DB
    cur.execute("DELETE FROM clips WHERE id=?", (clip_id,))
    conn.commit()
    conn.close()

    return f"🗑️ Deleted: {clip_id}"
