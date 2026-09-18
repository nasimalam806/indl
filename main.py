import os
import glob
import asyncio
import yt_dlp
from pyrogram import Client, filters
from apify_client import ApifyClient

# ==========================================
# 1. CREDENTIALS & VARIABLES
# ==========================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1002443275235  

INSTA_SESSION = os.environ.get("INSTA_SESSION_ID")
APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN")

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# Apify Client Initialize karna
apify_client = ApifyClient(APIFY_TOKEN) if APIFY_TOKEN else None

# ==========================================
# 2. APIFY LINK EXTRACTOR FUNCTION
# ==========================================
def get_links_from_apify(username):
    # Apify ke "Instagram Scraper" actor ko call kar rahe hain
    run_input = {
        "usernames": [username],
        "resultsLimit": 5, # Top 5 posts layega
    }
    
    # Actor run karna (Background me scrape karega)
    run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)
    
    # Result dataset se links nikalna
    links = []
    for item in apify_client.dataset(run["defaultDatasetId"]).iterate_items():
        if "url" in item:
            links.append(item["url"])
            
    return links

# ==========================================
# 3. YT-DLP DOWNLOADER FUNCTION
# ==========================================
def download_with_ytdl(links, username):
    # Cookie file banana taaki IG block na kare
    if INSTA_SESSION:
        cookie_text = f"# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTA_SESSION}\n"
        with open("cookies.txt", "w") as f:
            f.write(cookie_text)
            
    ydl_opts = {
        'outtmpl': f'{username}/%(id)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
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
        await message.reply_text("🚀 Apify + yt-dlp Downloader me swagat hai!\nUsage: `/insta username`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    if not APIFY_TOKEN:
        await message.reply_text("❌ Railway mein APIFY_API_TOKEN missing hai!")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 Apify Cloud se **{target_username}** ke post links nikal raha hu... (इसमें 10-20 सेकंड लग सकते हैं)")

    # --- 1. APIFY SE LINKS NIKALNA ---
    try:
        post_links = await asyncio.to_thread(get_links_from_apify, target_username)
    except Exception as e:
        await status_msg.edit_text(f"❌ Apify Error: {e}")
        return

    if not post_links:
        await status_msg.edit_text(f"⚠️ **{target_username}** ki profile me koi post nahi mili ya account private hai.")
        return

    await status_msg.edit_text(f"🔗 **{len(post_links)}** Links successfully mil gaye!\n⏳ Ab `yt-dlp` unhe download kar raha hai...")

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
        await status_msg.edit_text(f"✅ Success! **{upload_count}** media files Apify aur yt-dlp ke zariye upload ho chuki hain! 🚀")
    else:
        await status_msg.edit_text(f"⚠️ Download failed.\nyt-dlp Error: {err}")

if __name__ == "__main__":
    print("🚀 Apify + yt-dlp Bot Started!")
    app.run()
    
