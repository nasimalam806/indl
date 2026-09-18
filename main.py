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
    # 🔥 MAX LIMIT SET: Ab ye profile ko end tak scrape karega
    run_input = {
        "directUrls": [
            f"https://www.instagram.com/{username}/",
            f"https://www.instagram.com/{username}/reels/"
        ],
        "resultsType": "posts",
        "resultsLimit": 9999  # Pura max fetch karne ke liye
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
        
        # Reels / Videos
        if item_type == "Video":
            video_ig_links.append(ig_post_url)
            
        # Single Image
        elif item_type == "Image":
            img_url = item.get("displayUrl")
            if img_url:
                direct_image_urls.append(img_url)
                
        # Carousel / Sidecar
        elif item_type == "Sidecar":
            images = item.get("images", [])
            for img in images:
                direct_image_urls.append(img)
            
            # Check for carousel video
            if item.get("videoUrl"):
                video_ig_links.append(ig_post_url)
                
    return list(set(video_ig_links)), list(set(direct_image_urls))

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
        'ignoreerrors': True,
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
        await message.reply_text("🚀 Bulk Insta Downloader Bot!\nUsage: `/insta username`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 **{target_username}** ki poori profile aur reels scan ho rahi hain...\n(Max posts hain, 1-2 minute lag sakte hain ⏳)")

    try:
        video_links, image_urls = await asyncio.to_thread(extract_media_from_apify, target_username)
    except Exception as e:
        await status_msg.edit_text(f"❌ Apify Error: {e}")
        return

    if not video_links and not image_urls:
        await status_msg.edit_text(f"⚠️ Koi post ya reel nahi mili.")
        return

    await status_msg.edit_text(f"🔗 Analysis Complete!\n🎥 Reels/Videos (yt-dlp): **{len(video_links)}**\n📸 Photos (Direct): **{len(image_urls)}**\n\n⏳ Ab Bulk Download aur Upload start ho raha hai (Flood-Wait Protection Active 🛡️)...")

    if not os.path.exists(target_username):
        os.makedirs(target_username)

    upload_count = 0
    caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"

    # ==========================================
    # 5. DOWNLOAD & UPLOAD PHOTOS (WITH BATCH DELAY)
    # ==========================================
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

                # 🔥 FLOOD WAIT PROTECTION (Every 10 uploads -> 12 sec sleep)
                if upload_count % 10 == 0:
                    await status_msg.edit_text(f"⏳ Uploaded {upload_count} files. Flood-wait se bachne ke liye 12 seconds break le raha hu... 💤")
                    await asyncio.sleep(12)
                else:
                    await asyncio.sleep(1.5) # Normal delay
        except Exception as e:
            print(f"Direct Image DL failed: {e}")

    # ==========================================
    # 6. DOWNLOAD & UPLOAD VIDEOS (WITH BATCH DELAY)
    # ==========================================
    if video_links:
        # First download all videos via yt-dlp
        await status_msg.edit_text(f"📥 Videos download ho rahi hain (yt-dlp). Uploading resume hogi jaldi hi... ({upload_count} done)")
        success, err = await asyncio.to_thread(download_videos_ytdl, video_links, target_username)
        
        video_files = glob.glob(f"{target_username}/*.mp4")
        for file in video_files:
            try:
                await app.send_video(CHANNEL_ID, video=file, caption=caption_text)
                upload_count += 1
                os.remove(file)
                
                # 🔥 FLOOD WAIT PROTECTION (Every 10 uploads -> 12 sec sleep)
                if upload_count % 10 == 0:
                    await status_msg.edit_text(f"⏳ Uploaded {upload_count} files. Flood-wait se bachne ke liye 12 seconds break le raha hu... 💤")
                    await asyncio.sleep(12)
                else:
                    await asyncio.sleep(1.5) # Normal delay
            except Exception as e:
                print(f"Video Upload Error: {e}")

    # Folder cleanup
    try: os.rmdir(target_username)
    except: pass

    if upload_count > 0:
        await status_msg.edit_text(f"✅ BINGO! **{upload_count}** Media Files (Photos + Reels) channel pe successfully upload ho chuki hain! 🚀🔥")
    else:
        await status_msg.edit_text(f"⚠️ Media mili par upload nahi ho payi. Logs check karein.")

if __name__ == "__main__":
    print("🚀 Ultimate Bulk Downloader Bot Started!")
    app.run()
