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

# 🔥 Global variable to handle the /stop command
STOP_PROCESS = False

# ==========================================
# 2. APIFY DATA EXTRACTOR (FULL PAGINATION)
# ==========================================
def extract_media_from_apify(username):
    # Apify ki actor settings for full profile extraction
    run_input = {
        "directUrls": [
            f"https://www.instagram.com/{username}/",
            f"https://www.instagram.com/{username}/reels/"
        ],
        "resultsType": "posts",
        "resultsLimit": 9999,
        "searchType": "hashtag", # Fallback default
        "searchLimit": 1
    }
    
    run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)
    
    if isinstance(run, dict):
        dataset_id = run.get('defaultDatasetId') or run.get('default_dataset_id')
    else:
        dataset_id = getattr(run, 'defaultDatasetId', None) or getattr(run, 'default_dataset_id', None)

    if not dataset_id:
        raise Exception("Apify se Dataset ID nahi mili.")

    # Fetch ALL items from dataset
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
                
    return list(set(video_ig_links)), list(set(direct_image_urls))

# ==========================================
# 3. STOP COMMAND LOGIC
# ==========================================
@app.on_message(filters.command("stop"))
async def stop_process(client, message):
    global STOP_PROCESS
    STOP_PROCESS = True
    await message.reply_text("🛑 **STOP COMMAND RECEIVED!**\nAbhi chal raha task ruk jayega aur download hui saari files server se delete ho jayengi.")

# ==========================================
# 4. CHUNK HELPER FUNCTION
# ==========================================
def chunk_list(lst, n):
    """List ko n-size ke chote tukdon (albums) me divide karne ke liye"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ==========================================
# 5. MAIN BOT LOGIC
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

    # Process start karne se pehle stop flag ko reset karo
    STOP_PROCESS = False
    
    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 **{target_username}** ki poori profile aur reels fetch ho rahi hain...\n(Isme thoda time lagega ⏳)")

    try:
        video_links, image_urls = await asyncio.to_thread(extract_media_from_apify, target_username)
    except Exception as e:
        await status_msg.edit_text(f"❌ Apify Error: {e}")
        return

    if STOP_PROCESS:
        await status_msg.edit_text("🚫 Process Cancelled via /stop command.")
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
    # PHASE A: DOWNLOAD & UPLOAD PHOTOS (IN ALBUMS OF 10)
    # ==========================================
    if image_urls:
        # Download all images first
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
                print(f"Direct Image DL failed: {e}")

        # Create Albums and Upload
        for chunk in chunk_list(downloaded_images, 10):
            if STOP_PROCESS: break
            
            media_group = []
            for idx, img_path in enumerate(chunk):
                # Sirf pehli image par caption lagayenge
                cap = caption_text if idx == 0 else ""
                media_group.append(InputMediaPhoto(media=img_path, caption=cap))
            
            if media_group:
                try:
                    await app.send_media_group(CHANNEL_ID, media=media_group)
                    upload_count += len(media_group)
                    await status_msg.edit_text(f"⏳ Uploaded {upload_count} media files as Albums... 💤")
                    await asyncio.sleep(12) # Flood Wait Delay after every album
                except Exception as e:
                    print(f"Photo Album Upload Error: {e}")
                    
        # Cleanup photos after upload
        for img_path in downloaded_images:
            if os.path.exists(img_path): os.remove(img_path)

    if STOP_PROCESS:
        shutil.rmtree(target_username, ignore_errors=True)
        await status_msg.edit_text("🚫 Process Cancelled via /stop command. Saari downloaded files delete ho chuki hain.")
        return

    # ==========================================
    # PHASE B: DOWNLOAD & UPLOAD VIDEOS (IN ALBUMS OF 10)
    # ==========================================
    if video_links:
        await status_msg.edit_text(f"📥 Videos download ho rahi hain (yt-dlp)...")
        
        # Cookie file for yt-dlp
        if INSTA_SESSION:
            with open("cookies.txt", "w") as f:
                f.write(f"# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTA_SESSION}\n")
                
        ydl_opts = {
            'outtmpl': f'{target_username}/%(id)s.%(ext)s', 
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'ignoreerrors': True,
        }
        if INSTA_SESSION: ydl_opts['cookiefile'] = 'cookies.txt'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download(video_links)
        except Exception as e:
            print(f"YT-DLP Error: {e}")
        finally:
            if os.path.exists("cookies.txt"): os.remove("cookies.txt")
            
        if STOP_PROCESS:
            shutil.rmtree(target_username, ignore_errors=True)
            await status_msg.edit_text("🚫 Process Cancelled via /stop command. Saari downloaded files delete ho chuki hain.")
            return

        # Upload Videos in Albums
        video_files = glob.glob(f"{target_username}/*.mp4")
        for chunk in chunk_list(video_files, 10):
            if STOP_PROCESS: break
            
            media_group = []
            for idx, vid_path in enumerate(chunk):
                cap = caption_text if idx == 0 else ""
                media_group.append(InputMediaVideo(media=vid_path, caption=cap))
            
            if media_group:
                try:
                    await app.send_media_group(CHANNEL_ID, media=media_group)
                    upload_count += len(media_group)
                    await status_msg.edit_text(f"⏳ Uploaded {upload_count} media files as Albums... 💤")
                    await asyncio.sleep(12) # Flood Wait Delay after every album
                except Exception as e:
                    print(f"Video Album Upload Error: {e}")
                    
        # Cleanup videos
        for vid_path in video_files:
            if os.path.exists(vid_path): os.remove(vid_path)

    # Final Folder cleanup
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
    
