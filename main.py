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
# Make sure to keep the channel ID hardcoded if it doesn't change
CHANNEL_ID = -1002443275235  

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ==========================================
# 2. INSTALOADER SETUP (ANONYMOUS & SLOW)
# ==========================================
L = instaloader.Instaloader(
    download_pictures=True, 
    download_video_thumbnails=False, 
    download_geotags=False, 
    download_comments=False, 
    save_metadata=False,
    request_timeout=300 # Timeout badha diya taaki rate limit na aaye
)

# Hum intentionally headers ko thoda modify karenge taki bot jaisa kam lage
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

print("⚠️ Running in ANONYMOUS mode (No Session ID). Rate limits may still occur.")

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
    status_msg = await message.reply_text(f"🔍 Checking Instagram profile: **{target_username}**...\n(Bina login ke kar rahe hain, isliye error aane ke chances hain)")

    def download_posts():
        try:
            # Profile fetch karne se pehle ek chota sa random delay (taki suspicious na lage)
            time.sleep(random.uniform(2, 5))
            
            profile = instaloader.Profile.from_username(L.context, target_username)
            count = 0
            
            # Post download loop
            for post in profile.get_posts():
                if count >= 3: # Limit thodi aur kam kardi (3 posts max) taki aur safe rahe
                    break
                    
                # Har download ke beech me bada delay! (Bina login wale me ye zaroori hai)
                time.sleep(random.uniform(5, 12)) 
                
                L.download_post(post, target=target_username)
                count += 1
            return True, "Success"
        except Exception as e:
            return False, str(e)

    await status_msg.edit_text(f"⏳ Downloading recent 3 posts of **{target_username}** locally... (Anonymous requests slow hoti hain, please wait)")
    
    success, error_msg = await asyncio.to_thread(download_posts)

    if not success:
        if "429" in error_msg or "Too Many Requests" in error_msg or "LoginRequiredException" in error_msg:
             await status_msg.edit_text(f"❌ Instagram Rate Limit/Login Error.\nBina login ke Instagram ab anonymous requests block kar raha hai. Yeh public profiles ke liye bhi ho sakta hai.\nDetails: {error_msg}")
        else:
            await status_msg.edit_text(f"❌ Instagram Error: {error_msg}\n\n(Note: Private account ho sakta hai)")
        return

    await status_msg.edit_text("📤 Uploading all downloaded files to your Telegram Channel...")

    # ==========================================
    # 4. UPLOAD TO CHANNEL & CLEANUP
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
                print(f"Upload fail hua: {file} - Error: {e}")
                if os.path.exists(file):
                    os.remove(file)
        
        try:
            os.rmdir(folder_path)
        except: 
            pass
            
    await status_msg.edit_text(f"✅ Success! **{upload_count}** posts/reels aapke channel pe bhej diye gaye hain.")

if __name__ == "__main__":
    print("Insta Downloader Bot Started with Secure Environment Variables (Anonymous Mode)!")
    app.run()
