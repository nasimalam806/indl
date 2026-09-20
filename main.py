import os
import glob
import asyncio
import yt_dlp
import requests
import time
import shutil
import json
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from pyrogram.errors import MessageNotModified, FloodWait
from yt_dlp.networking.impersonate import ImpersonateTarget

# ==========================================
# 1. CREDENTIALS & VARIABLES
# ==========================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = -1002443275235  

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
STOP_PROCESS = False

def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ==========================================
# 2. YT-DLP DOWNLOADER (NO SESSION ID NEEDED)
# ==========================================
def download_videos_ytdl(links, username):
    if not links: return True, "No links"
    
    # 🔥 The MAGIC: Impersonate Target for Instagram 
    ydl_opts = {
        'outtmpl': f'{username}/%(id)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'ignoreerrors': True,
        'socket_timeout': 15,
        'retries': 3,
        'impersonate': ImpersonateTarget.from_str('chrome'), # <-- This mimics a real browser!
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(links)
        return True, "Success"
    except Exception as e:
        return False, str(e)

# ==========================================
# 3. COMMANDS
# ==========================================
@app.on_message(filters.command("stop"))
async def stop_process(client, message):
    global STOP_PROCESS
    STOP_PROCESS = True
    await message.reply_text("🛑 **STOP COMMAND RECEIVED!**\nUpload ruk jayega aur files delete ho jayengi.")

@app.on_message(filters.command("start"))
async def start_msg(client, message):
    await message.reply_text("🚀 JSON Downloader Bot Active!\nApne Termux se generate ki hui `.json` file yahan send karo aur main download start kar dunga.\nRokne ke liye: `/stop`")

# ==========================================
# 4. JSON PROCESSING & ALBUM UPLOAD
# ==========================================
@app.on_message(filters.document)
async def process_json(client, message):
    global STOP_PROCESS
    if not message.document.file_name.endswith(".json"):
        await message.reply_text("⚠️ Kripya valid .json file bhejein.")
        return

    STOP_PROCESS = False
    status_msg = await message.reply_text("📥 JSON file download aur padh raha hu...")
    
    file_path = await message.download()
    
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        
        target_username = data.get("username", "unknown")
        video_links = data.get("videos", [])
        image_urls = data.get("images", [])
    except Exception as e:
        await status_msg.edit_text(f"❌ JSON padhne me error: {e}")
        os.remove(file_path)
        return

    os.remove(file_path) 
    
    await status_msg.edit_text(f"🔗 File Loaded Successfully!\n👤 Profile: **{target_username}**\n🎥 Videos: **{len(video_links)}**\n📸 Photos: **{len(image_urls)}**\n\n⏳ Ab High-Speed Server Download aur Upload start ho raha hai...")

    if not os.path.exists(target_username):
        os.makedirs(target_username)

    upload_count = 0
    caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"

    # --- PHASE A: PHOTOS (ALBUMS OF 10) ---
    if image_urls:
        downloaded_images = []
        for i, img_url in enumerate(image_urls):
            if STOP_PROCESS: break
            try:
                temp_img = f"{target_username}/photo_{i}_{int(time.time())}.jpg"
                dl_res = await asyncio.to_thread(requests.get, img_url, stream=True)
                if dl_res.status_code == 200:
                    with open(temp_img, 'wb') as f:
                        for chunk in dl_res.iter_content(1024): f.write(chunk)
                    downloaded_images.append(temp_img)
            except Exception as e:
                print(f"Image DL error: {e}")

        for chunk in chunk_list(downloaded_images, 10):
            if STOP_PROCESS: break
            media_group = [InputMediaPhoto(media=img_path, caption=caption_text if idx == 0 else "") for idx, img_path in enumerate(chunk)]
            if media_group:
                try:
                    await app.send_media_group(CHANNEL_ID, media=media_group)
                    upload_count += len(media_group)
                    await status_msg.edit_text(f"📸 Uploaded {upload_count} media files... 💤")
                    await asyncio.sleep(12) 
                except Exception as e:
                    print(f"Photo Album Upload Error: {e}")
                    
        for img_path in downloaded_images:
            if os.path.exists(img_path): os.remove(img_path)

    if STOP_PROCESS:
        shutil.rmtree(target_username, ignore_errors=True)
        await status_msg.edit_text("🚫 Process Cancelled via /stop.")
        return

    # --- PHASE B: VIDEOS (ALBUMS OF 10) ---
    if video_links:
        await status_msg.edit_text(f"📥 High-Speed Server se Videos download ho rahi hain (No Login Needed!)...")
        await asyncio.to_thread(download_videos_ytdl, video_links, target_username)
            
        if STOP_PROCESS:
            shutil.rmtree(target_username, ignore_errors=True)
            await status_msg.edit_text("🚫 Process Cancelled via /stop.")
            return

        video_files = [f for f in glob.glob(f"{target_username}/*") if f.lower().endswith(('.mp4', '.webm', '.mkv', '.mov'))]
        
        for chunk in chunk_list(video_files, 10):
            if STOP_PROCESS: break
            media_group = [InputMediaVideo(media=vid_path, caption=caption_text if idx == 0 else "", supports_streaming=True) for idx, vid_path in enumerate(chunk)]
            if media_group:
                try:
                    await app.send_media_group(CHANNEL_ID, media=media_group)
                    upload_count += len(media_group)
                    await status_msg.edit_text(f"🎥 Uploaded {upload_count} media files... 💤")
                    await asyncio.sleep(15) 
                except Exception as e:
                    print(f"Video Album Upload Error: {e}")
                    for vid in chunk:
                        try:
                            await app.send_video(CHANNEL_ID, video=vid, caption=caption_text, supports_streaming=True)
                            upload_count += 1
                            await asyncio.sleep(3)
                        except: pass
                    
        for vid_path in video_files:
            if os.path.exists(vid_path): os.remove(vid_path)

    shutil.rmtree(target_username, ignore_errors=True)

    if STOP_PROCESS:
        await status_msg.edit_text(f"🛑 Stopped manually! {upload_count} media files upload hui hain.")
    elif upload_count > 0:
        await status_msg.edit_text(f"✅ BINGO! **{upload_count}** Media Files channel pe Album format mein successfully upload ho chuki hain! 🚀🔥")
    else:
        await status_msg.edit_text(f"⚠️ Media nahi mili. Logs check karein.")

if __name__ == "__main__":
    print("🚀 Server JSON Downloader Bot Started!")
    app.run()
