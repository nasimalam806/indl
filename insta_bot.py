import os
import glob
import asyncio
import instaloader
from pyrogram import Client, filters

# ==========================================
# 1. BOT & CHANNEL CREDENTIALS
# ==========================================
API_ID = 30072361  # Apna API ID dalein
API_HASH = "89172ae56cce451a933e4aa2557c1721"
BOT_TOKEN = "8339283061:AAEfEDxTyOtsdOZaJKDvL0MiB41WqpqcvRk"
CHANNEL_ID = -1002443275235  # YAHAN APNE TARGET CHANNEL KA ID DALEIN

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Instaloader setup (Sirf photos aur videos download karega, extra text/metadata nahi)
L = instaloader.Instaloader(
    download_pictures=True, 
    download_video_thumbnails=False, 
    download_geotags=False, 
    download_comments=False, 
    save_metadata=False
)

# ==========================================
# 2. MAIN DOWNLOAD FUNCTION
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 Insta Profile Downloader me swagat hai!\nUsage: `/insta username`\nExample: `/insta therock`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!\nAise likho: `/insta therock`")
        return

    # Link me se username nikalna (agar link diya ho toh)
    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    
    status_msg = await message.reply_text(f"🔍 Checking Instagram profile: **{target_username}**...")

    def download_posts():
        try:
            profile = instaloader.Profile.from_username(L.context, target_username)
            
            # 🔥 SAFETY LIMIT: Abhi sirf top 5 posts download karega test ke liye.
            # Agar sab ek sath karna hai, toh count wala logic hata dena.
            count = 0
            for post in profile.get_posts():
                if count >= 5: 
                    break
                L.download_post(post, target=target_username)
                count += 1
            return True, "Success"
        except Exception as e:
            return False, str(e)

    await status_msg.edit_text(f"⏳ Downloading recent posts of **{target_username}** locally... (Isme thoda time lagega)")
    
    # Run instaloader in background thread so it doesn't freeze the bot
    success, error_msg = await asyncio.to_thread(download_posts)

    if not success:
        await status_msg.edit_text(f"❌ Instagram Error: {error_msg}\n\n(Note: Private account ya rate-limit issue ho sakta hai)")
        return

    await status_msg.edit_text("📤 Uploading all downloaded files to your Telegram Channel...")

    # ==========================================
    # 3. UPLOAD TO CHANNEL & CLEANUP
    # ==========================================
    folder_path = target_username
    upload_count = 0
    
    if os.path.exists(folder_path):
        # Folder me jitni bhi videos/photos aayi hain, unko dhundho
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
                    
                # Upload hone ke baad server se delete kar do
                os.remove(file)
            except Exception as e:
                print(f"Upload fail hua: {file} - Error: {e}")
                # Text files (jaise captions) instaloader download kar leta hai, unhe ignore karke delete kar do
                if os.path.exists(file):
                    os.remove(file)
        
        # Aakhiri me khali folder delete kar do
        try:
            os.rmdir(folder_path)
        except: 
            pass
            
    await status_msg.edit_text(f"✅ Success! **{upload_count}** posts/reels aapke channel pe bhej diye gaye hain.")

if __name__ == "__main__":
    print("Insta Downloader Bot Started!")
    app.run()
  
