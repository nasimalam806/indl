import os
import glob
import asyncio
import instaloader
import time
import random
from pyrogram import Client, filters

# ==========================================
# 1. BOT & CHANNEL CREDENTIALS (SECURE)
# ==========================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1002443275235  

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ==========================================
# 2. INSTALOADER SETUP (FAIL-FAST)
# ==========================================
L = instaloader.Instaloader(
    download_pictures=True, 
    download_video_thumbnails=False, 
    download_geotags=False, 
    download_comments=False, 
    save_metadata=False,
    request_timeout=15,         # 🔥 300 se ghata kar 15s kar diya taaki hang na ho
    max_connection_attempts=1   # 🔥 Fail hone par infinite retry na kare, seedha error de
)

# Fake Headers
L.context._session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1'
})

# ==========================================
# 3. MAIN DOWNLOAD FUNCTION
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 Insta Profile Downloader me swagat hai (Anonymous Mode)!\nUsage: `/insta username`\nExample: `/insta therock`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!\nAise likho: `/insta therock`")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 Checking Instagram profile: **{target_username}**...")

    def download_posts():
        try:
            profile = instaloader.Profile.from_username(L.context, target_username)
            count = 0
            for post in profile.get_posts():
                if count >= 3: 
                    break
                time.sleep(random.uniform(3, 7)) 
                L.download_post(post, target=target_username)
                count += 1
            return True, "Success"
        except Exception as e:
            return False, str(e)

    await status_msg.edit_text(f"⏳ Downloading recent 3 posts of **{target_username}** locally... (Max wait: 20 seconds)")
    
    # Background process with a strict hard-timeout to prevent any frozen threads
    try:
        success, error_msg = await asyncio.wait_for(asyncio.to_thread(download_posts), timeout=60.0)
    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ Instagram ne server block kar diya hai (Timeout). Connection drop ho gaya.")
        return

    if not success:
        if "429" in error_msg or "Too Many Requests" in error_msg or "LoginRequiredException" in error_msg or "Redirected" in error_msg:
             await status_msg.edit_text(f"❌ Instagram Rate Limit/Login Error.\nBina login ke Instagram ne humari Railway IP ko block kar diya hai.\nDetails: {error_msg}")
        else:
            await status_msg.edit_text(f"❌ Instagram Error: {error_msg}\n\n(Note: Account private ya delete ho sakta hai)")
        return

    await status_msg.edit_text("📤 Uploading files to Telegram Channel...")

    # ==========================================
    # 4. UPLOAD & CLEANUP
    # ==========================================
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
                elif file.endswith(".jpg"):
                    await app.send_photo(CHANNEL_ID, photo=file, caption=caption_text)
                    upload_count += 1
                    
                os.remove(file)
            except Exception as e:
                if os.path.exists(file): os.remove(file)
        
        try: os.rmdir(folder_path)
        except: pass
            
    await status_msg.edit_text(f"✅ Success! **{upload_count}** posts/reels sent to channel.")

if __name__ == "__main__":
    app.run()
