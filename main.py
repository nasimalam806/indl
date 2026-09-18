import os
import glob
import asyncio
import yt_dlp
import requests
import time
import shutil
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from apify_client import ApifyClient

# ==========================================
# 1. CREDENTIALS & VARIABLES
# ==========================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = -1002443275235  

INSTA_SESSION = os.environ.get("INSTA_SESSION_ID")
APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN")

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
apify_client = ApifyClient(APIFY_TOKEN) if APIFY_TOKEN else None

# 🔥 Global variable for /stop command
STOP_PROCESS = False

# ==========================================
# 2. APIFY DATA EXTRACTOR (DEEP SCROLL)
# ==========================================
def extract_media_from_apify(username):
    # Apify ki actor settings for deeper profile extraction
    run_input = {
        "directUrls": [
            f"https://www.instagram.com/{username}/",
            f"https://www.instagram.com/{username}/reels/"
        ],
        "resultsType": "posts",
        "resultsLimit": 9999,
    }
    
    run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)
    
    if isinstance(run, dict):
        dataset_id = run.get('defaultDatasetId') or run.get('default_dataset_id')
    else:
        dataset_id = getattr(run, 'defaultDatasetId', None) or getattr(run, 'default_dataset_id', None)

    if not dataset_id:
        raise Exception("Apify se Dataset ID nahi mili.")

    items = apify_client.dataset(dataset_id).list_items().items
    
    video_ig_links = []
    direct_image_urls = []
    
    for item in items:
        item_type = item.get("type")
        ig_post_url = item.get("url")
        
        if item_type == "Video":
            video_ig_links.append(ig_post_url)
        elif item_type == "Image":
            img_url = item.get("displayUrl")
            if img_url: direct_image_urls.append(img_url)
        elif item_type == "Sidecar":
            images = item.get("images", [])
            for img in images: direct_image_urls.append(img)
            if item.get("videoUrl"):
                video_ig_links.append(ig_post_url)
                
    # Remove duplicates
    return list(set(video_ig_links)), list(set(direct_image_urls))

# ==========================================
# 3. STOP COMMAND LOGIC
# ==========================================
@app.on_message(filters.command("stop"))
async def stop_process(client, message):
    global STOP_PROCESS
    STOP_PROCESS = True
    await message.reply_text("🛑 **STOP COMMAND RECEIVED!**\nAbhi chal raha task ruk jayega aur download hui saari files delete ho jayengi.")

# ==========================================
# 4. CHUNK HELPER FUNCTION
# ==========================================
def chunk_list(lst, n):
    """List ko n-size ke albums me divide karega"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ==========================================
# 5. YT-DLP VIDEO DOWNLOADER
# ==========================================
def download_videos_ytdl(links, username):
    if not links: return True, "No links"
        
    if INSTA_SESSION:
        with open("cookies.txt", "w") as f:
            f.write(f"# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTA_SESSION}\n")
            
    ydl_opts = {
        'outtmpl': f'{username}/%(id)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # Force MP4
        'ignoreerrors': True,
        'sleep_interval': 1,     # 🔥 IG block na kare isliye har video k beech delay
        'max_sleep_interval': 3,
    }
    if INSTA_SESSION: ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(links)
        return True, "Success"
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists("cookies.txt"): os.remove("cookies.txt")

# ==========================================
# 6. MAIN BOT LOGIC
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    global STOP_PROCESS
    
    if message.command[0] == "start":
        await message.reply_text("🚀 Ultimate Album Downloader Bot!\nUsage: `/insta username`\nTo abort: `/stop`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    STOP_PROCESS = False
    
    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 **{target_username}** ki poori profile aur reels fetch ho rahi hain...\n(Deep scan chal raha hai ⏳)")

    try:
        video_links, image_urls = await asyncio.to_thread(extract_media_from_apify, target_username)
    except Exception as e:
        await status_msg.edit_text(f"❌ Apify Error: {e}")
        return

    if STOP_PROCESS:
        await status_msg.edit_text("🚫 Process Cancelled.")
        return

    if not video_links and not image_urls:
        await status_msg.edit_text(f"⚠️ Koi post ya reel nahi mili.")
        return

    await status_msg.edit_text(f"🔗 Analysis Complete!\n🎥 Reels/Videos (yt-dlp): **{len(video_links)}**\n📸 Photos (Direct): **{len(image_urls)}**\n\n⏳ Ab Download aur Album Upload start ho raha hai...")

    if not os.path.exists(target_username):
        os.makedirs(target_username)

    upload_count = 0
    caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"

    # ==========================================
    # PHASE A: PHOTOS UPLOAD (ALBUMS OF 10)
    # ==========================================
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

        # Upload Photos in Chunks of 10
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
        await status_msg.edit_text("🚫 Process Cancelled via /stop command.")
        return

    # ==========================================
    # PHASE B: VIDEOS UPLOAD (ALBUMS OF 5)
    # ==========================================
    if video_links:
        await status_msg.edit_text(f"📥 Videos download ho rahi hain (yt-dlp)...")
        
        await asyncio.to_thread(download_videos_ytdl, video_links, target_username)
            
        if STOP_PROCESS:
            shutil.rmtree(target_username, ignore_errors=True)
            await status_msg.edit_text("🚫 Process Cancelled via /stop command.")
            return

        # 🔥 FIX: Sabhi video extensions ko pakdo (.mp4, .webm, .mkv, .mov)
        video_files = [f for f in glob.glob(f"{target_username}/*") if f.lower().endswith(('.mp4', '.webm', '.mkv', '.mov'))]
        
        # 🔥 FIX: Videos ko 5-5 ki album mein bhejo taaki Telegram crash na ho
        for chunk in chunk_list(video_files, 5):
            if STOP_PROCESS: break
            
            media_group = [InputMediaVideo(media=vid_path, caption=caption_text if idx == 0 else "") for idx, vid_path in enumerate(chunk)]
            
            if media_group:
                try:
                    await app.send_media_group(CHANNEL_ID, media=media_group)
                    upload_count += len(media_group)
                    await status_msg.edit_text(f"🎥 Uploaded {upload_count} media files... 💤")
                    await asyncio.sleep(15) # Videos ke baad lamba rest
                except Exception as e:
                    print(f"Video Album Upload Error: {e}")
                    # Agar video album fail ho jaye, toh unko individually bhej do (Fallback)
                    for vid in chunk:
                        try:
                            await app.send_video(CHANNEL_ID, video=vid, caption=caption_text)
                            upload_count += 1
                            await asyncio.sleep(3)
                        except Exception as inner_e:
                            print(f"Single video fail: {inner_e}")
                    
        for vid_path in video_files:
            if os.path.exists(vid_path): os.remove(vid_path)

    shutil.rmtree(target_username, ignore_errors=True)

    if STOP_PROCESS:
        await status_msg.edit_text(f"🛑 Stopped manually! {upload_count} media files upload hui hain.")
    elif upload_count > 0:
        await status_msg.edit_text(f"✅ BINGO! **{upload_count}** Media Files channel pe Album format mein successfully upload ho chuki hain! 🚀🔥")
    else:
        await status_msg.edit_text(f"⚠️ Media mili par upload nahi ho payi. Logs check karein.")

if __name__ == "__main__":
    print("🚀 Ultimate Album Downloader Bot Started!")
    app.run()
