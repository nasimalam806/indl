import os
import glob
import asyncio
import instaloader
from pyrogram import Client, filters

# ==========================================
# 1. BOT & CHANNEL CREDENTIALS (SECURE)
# ==========================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Make sure to keep the channel ID hardcoded if it doesn't change, 
# or use int(os.environ.get("CHANNEL_ID")) if you add it to variables
CHANNEL_ID = -1002443275235  

# Get Insta Session ID from Railway Environment
INSTA_SESSION = os.environ.get("INSTA_SESSION_ID")

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ==========================================
# 2. INSTALOADER SETUP & LOGIN
# ==========================================
L = instaloader.Instaloader(
    download_pictures=True, 
    download_video_thumbnails=False, 
    download_geotags=False, 
    download_comments=False, 
    save_metadata=False,
    request_timeout=300 # Timeout badha diya taaki rate limit na aaye
)

# Agar session id variable me hai, toh login inject karo
if INSTA_SESSION:
    try:
        L.context._session.cookies.set('sessionid', INSTA_SESSION, domain='instagram.com')
        # Check login status
        L.test_login()
        print("✅ Instagram Successfully Logged In using Session ID!")
    except Exception as e:
        print(f"⚠️ Instagram Login Failed. Check your Session ID. Error: {e}")
else:
    print("⚠️ No INSTA_SESSION_ID found in variables. Running anonymously (Will likely get blocked).")

# ==========================================
# 3. MAIN DOWNLOAD FUNCTION
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 Insta Profile Downloader me swagat hai!\nUsage: `/insta username`\nExample: `/insta therock`")
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
                if count >= 5: 
                    break
                L.download_post(post, target=target_username)
                count += 1
            return True, "Success"
        except Exception as e:
            return False, str(e)

    await status_msg.edit_text(f"⏳ Downloading recent 5 posts of **{target_username}** locally... (Rate limit bachane ke liye thoda aaram se kar raha hu)")
    
    success, error_msg = await asyncio.to_thread(download_posts)

    if not success:
        if "429" in error_msg or "Too Many Requests" in error_msg:
             await status_msg.edit_text(f"❌ Instagram Rate Limit Error (429).\nInstagram ne block kar diya hai. Apna INSTA_SESSION_ID Railway me check karein ya thodi der baad try karein.\nDetails: {error_msg}")
        else:
            await status_msg.edit_text(f"❌ Instagram Error: {error_msg}\n\n(Note: Private account ya rate-limit issue ho sakta hai)")
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
    print("Insta Downloader Bot Started with Secure Environment Variables!")
    app.run()
