import os
import glob
import asyncio
import yt_dlp
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
# 2. APIFY LINK EXTRACTOR
# ==========================================
def get_links_from_apify(username):
    run_input = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsType": "posts",
        "resultsLimit": 5
    }
    
    run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)
    
    if isinstance(run, dict):
        dataset_id = run.get('defaultDatasetId') or run.get('default_dataset_id')
    else:
        dataset_id = getattr(run, 'defaultDatasetId', None) or getattr(run, 'default_dataset_id', None)

    if not dataset_id:
        raise Exception("Apify se Dataset ID nahi mili.")

    links = []
    items = apify_client.dataset(dataset_id).list_items().items
    
    for item in items:
        post_url = item.get("url")
        if post_url and ("instagram.com/p/" in post_url or "instagram.com/reel/" in post_url):
            links.append(post_url)
            
    # Sirf pehli 2 posts ka data return kar rahe hain debug ke liye
    return list(set(links)), items[:2] 

# ==========================================
# 3. YT-DLP DOWNLOADER FUNCTION
# ==========================================
def download_with_ytdl(links, username):
    if INSTA_SESSION:
        cookie_text = f"# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTA_SESSION}\n"
        with open("cookies.txt", "w") as f:
            f.write(cookie_text)
            
    ydl_opts = {
        'outtmpl': f'{username}/%(id)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'ignoreerrors': True, # 🔥 FIX: Photo aane par crash nahi hoga, ignore karke next par jayega
    }
    
    if INSTA_SESSION:
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(links)
        return True, "Success"
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists("cookies.txt"):
            os.remove("cookies.txt")

# ==========================================
# 4. MAIN BOT LOGIC
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 APIFY + yt-dlp Bot!\nUsage: `/insta username`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 Apify Cloud se **{target_username}** fetch kar raha hu...")

    # --- 1. APIFY SE DATA NIKALNA ---
    try:
        post_links, raw_items = await asyncio.to_thread(get_links_from_apify, target_username)
    except Exception as e:
        await status_msg.edit_text(f"❌ Apify Error: {e}")
        return

    if not post_links:
        await status_msg.edit_text(f"⚠️ Koi post nahi mili.")
        return

    # 🔥 DEBUG FEATURE: Show API Response in Telegram
    try:
        # JSON ko pretty format karke bhejenge (3500 chars limit taki message fail na ho)
        raw_data_str = json.dumps(raw_items, indent=2, ensure_ascii=False)[:3500]
        await message.reply_text(f"🛠️ **APIFY KA RAW RESPONSE (SAMPLE):**\n```json\n{raw_data_str}\n```")
    except Exception as e:
        print(f"Debug print fail: {e}")

    await status_msg.edit_text(f"🔗 **{len(post_links)}** Links mil gaye!\n⏳ Ab `yt-dlp` download kar रहा hai (Photo wali posts pe error ignore karega)...")

    # --- 2. YT-DLP SE DOWNLOAD KARNA ---
    success, err = await asyncio.to_thread(download_with_ytdl, post_links, target_username)

    await status_msg.edit_text("📤 Download complete! Telegram channel me bhej raha hu...")

    # --- 3. TELEGRAM PAR UPLOAD KARNA ---
    folder_path = target_username
    upload_count = 0
    
    if os.path.exists(folder_path):
        media_files = glob.glob(f"{folder_path}/*")
        
        for file in media_files:
            try:
                caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"
                if file.endswith(".mp4"):
                    await app.send_video(CHANNEL_ID, video=file, caption=caption_text)
                    upload_count += 1
                elif file.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    await app.send_photo(CHANNEL_ID, photo=file, caption=caption_text)
                    upload_count += 1
                
                os.remove(file)
            except Exception as e:
                print(f"Upload Error: {e}")
                if os.path.exists(file): os.remove(file)
        
        try: os.rmdir(folder_path)
        except: pass
            
    if upload_count > 0:
        await status_msg.edit_text(f"✅ Success! **{upload_count}** files upload ho chuki hain! 🚀\n*(Note: Sirf video/reels download hui hongi kyunki yt-dlp images me fail hota hai)*")
    else:
        await status_msg.edit_text(f"⚠️ yt-dlp ek bhi file download nahi kar paya. Shayad saari posts image thi ya yt-dlp block ho gaya.\nyt-dlp Error: {err}")

if __name__ == "__main__":
    app.run()
