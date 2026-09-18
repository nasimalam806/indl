import os
import glob
import asyncio
import yt_dlp
import requests
import time
import json
from pyrogram import Client, filters
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

# ==========================================
# 2. APIFY DATA EXTRACTOR & SEPARATOR
# ==========================================
def extract_media_from_apify(username):
    # 🔥 Main Profile aur Reels dono ko target kar rahe hain
    run_input = {
        "directUrls": [
            f"https://www.instagram.com/{username}/",
            f"https://www.instagram.com/{username}/reels/"
        ],
        "resultsType": "posts",
        "resultsLimit": 10  # Dono mix karke top 10 results layega
    }
    
    run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)
    
    # Dataset ID nikalne ka bulletproof tarika
    if isinstance(run, dict):
        dataset_id = run.get('defaultDatasetId') or run.get('default_dataset_id')
    else:
        dataset_id = getattr(run, 'defaultDatasetId', None) or getattr(run, 'default_dataset_id', None)

    if not dataset_id:
        raise Exception("Apify se Dataset ID nahi mili.")

    items = apify_client.dataset(dataset_id).list_items().items
    
    video_ig_links = [] # yt-dlp ke liye (Reels & Videos)
    direct_image_urls = [] # requests/direct download ke liye (Photos)
    
    for item in items:
        item_type = item.get("type")
        ig_post_url = item.get("url")
        
        # 1. Agar Video ya Reel hai
        if item_type == "Video":
            video_ig_links.append(ig_post_url)
            
        # 2. Agar Single Image hai
        elif item_type == "Image":
            img_url = item.get("displayUrl")
            if img_url:
                direct_image_urls.append(img_url)
                
        # 3. Agar Sidecar (Carousel / Multiple Photos) hai
        elif item_type == "Sidecar":
            images = item.get("images", [])
            for img in images:
                direct_image_urls.append(img)
            # Agar sidecar me koi video bhi chupa hai
            if item.get("videoUrl"):
                video_ig_links.append(ig_post_url)
                
    # Duplicates hatane ke liye list(set())
    return list(set(video_ig_links)), list(set(direct_image_urls)), items[:1]

# ==========================================
# 3. YT-DLP VIDEO DOWNLOADER
# ==========================================
def download_videos_ytdl(links, username):
    if not links:
        return True, "No video links to download"
        
    if INSTA_SESSION:
        with open("cookies.txt", "w") as f:
            f.write(f"# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTA_SESSION}\n")
            
    ydl_opts = {
        'outtmpl': f'{username}/%(id)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'ignoreerrors': True, # Video download me chota error aaye to crash nahi hoga
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
# 4. MAIN BOT LOGIC
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 Ultimate APIFY + yt-dlp Bot!\nUsage: `/insta username`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 Apify Cloud se **{target_username}** ke Posts aur Reels dhundh raha hu...")

    # --- 1. GET DATA & SEPARATE LINKS ---
    try:
        video_links, image_urls, raw_data = await asyncio.to_thread(extract_media_from_apify, target_username)
    except Exception as e:
        await status_msg.edit_text(f"❌ Apify Error: {e}")
        return

    if not video_links and not image_urls:
        await status_msg.edit_text(f"⚠️ Koi post ya reel nahi mili.")
        return

    await status_msg.edit_text(f"🔗 Analysis Complete!\n🎥 Reels/Videos (yt-dlp): **{len(video_links)}**\n📸 Photos (Direct): **{len(image_urls)}**\n\n⏳ Ab Download aur Upload start ho raha hai...")

    if not os.path.exists(target_username):
        os.makedirs(target_username)

    upload_count = 0
    caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"

    # --- 2. FAST DIRECT DOWNLOAD FOR IMAGES ---
    for i, img_url in enumerate(image_urls):
        try:
            temp_img = f"{target_username}/photo_{i}_{int(time.time())}.jpg"
            dl_res = await asyncio.to_thread(requests.get, img_url, stream=True)
            if dl_res.status_code == 200:
                with open(temp_img, 'wb') as f:
                    for chunk in dl_res.iter_content(1024):
                        f.write(chunk)
                await app.send_photo(CHANNEL_ID, photo=temp_img, caption=caption_text)
                upload_count += 1
                os.remove(temp_img)
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Direct Image DL failed: {e}")

    # --- 3. YT-DLP DOWNLOAD FOR VIDEOS/REELS ---
    if video_links:
        success, err = await asyncio.to_thread(download_videos_ytdl, video_links, target_username)
        
        video_files = glob.glob(f"{target_username}/*.mp4")
        for file in video_files:
            try:
                await app.send_video(CHANNEL_ID, video=file, caption=caption_text)
                upload_count += 1
                os.remove(file)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Video Upload Error: {e}")

    # Folder cleanup
    try: os.rmdir(target_username)
    except: pass

    if upload_count > 0:
        await status_msg.edit_text(f"✅ Success! **{upload_count}** Media Files (Photos + Reels) channel pe upload ho chuki hain! 🚀🔥")
    else:
        await status_msg.edit_text(f"⚠️ Media mili par upload nahi ho payi. Logs check karein.")

    # Show raw JSON debug (1st post)
    try:
        raw_data_str = json.dumps(raw_data, indent=2, ensure_ascii=False)[:3500]
        await message.reply_text(f"🛠️ **APIFY RAW DATA (1 Post Sample):**\n```json\n{raw_data_str}\n```")
    except:
        pass

if __name__ == "__main__":
    print("🚀 Ultimate Apify + yt-dlp Bot Started!")
    app.run()
