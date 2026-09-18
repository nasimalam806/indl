import os
import glob
import asyncio
import yt_dlp
from pyrogram import Client, filters

# ==========================================
# 1. BOT & CHANNEL CREDENTIALS
# ==========================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1002443275235  

# Sirf Insta Session ID chahiye, sab APIs ka kaam khatam!
INSTA_SESSION = os.environ.get("INSTA_SESSION_ID")

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ==========================================
# 2. YT-DLP DIRECT PROFILE EXTRACTOR & DOWNLOADER
# ==========================================
def download_profile_with_ytdl(username):
    # 1. Cookie file banana (Insta login ke liye)
    if INSTA_SESSION:
        # yt-dlp ko Netscape format ki cookies chahiye hoti hain
        cookie_text = f"# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTA_SESSION}\n"
        with open("cookies.txt", "w") as f:
            f.write(cookie_text)
    else:
        return False, "INSTA_SESSION_ID variable Railway me missing hai."
    
    # 2. yt-dlp Options
    ydl_opts = {
        'outtmpl': f'{username}/%(id)s.%(ext)s', # User ke naam ka folder banega
        'cookiefile': 'cookies.txt',             # 🔥 Cookies inject kardi!
        'playlistend': 5,                        # 🔥 Limit: Sirf Top 5 Posts/Reels hi laye
        'quiet': True,
        'no_warnings': True,
        'format': 'best'
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Seedha profile ka URL pass kar diya. 
            # yt-dlp khud profile ke andar ghusega aur posts dhundh kar download kar lega!
            ydl.download([f"https://www.instagram.com/{username}/"])
        return True, "Success"
    except Exception as e:
        return False, str(e)

# ==========================================
# 3. MAIN BOT LOGIC
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 Ultimate yt-dlp Downloader!\nUsage: `/insta username`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    
    status_msg = await message.reply_text(f"🔍 **{target_username}** ki profile par yt-dlp magic chala raha hu...\n(Ek saath saari media nikal kar download karega, thoda wait kijiye ⏳)")

    # --- YT-DLP PROFILE DOWNLOAD ---
    success, error_msg = await asyncio.to_thread(download_profile_with_ytdl, target_username)

    if not success:
        await status_msg.edit_text(f"❌ yt-dlp Error: {error_msg}\n(Session expire ho gaya hai, ya account private hai)")
        return

    await status_msg.edit_text("📤 Download complete! Telegram channel me upload ho raha hai...")

    # --- TELEGRAM PAR UPLOAD KARNA ---
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
                
                os.remove(file) # Delete immediately after upload
            except Exception as e:
                print(f"Upload Error: {e}")
                if os.path.exists(file): os.remove(file)
        
        try: os.rmdir(folder_path)
        except: pass
            
    # Cleanup cookies
    if os.path.exists("cookies.txt"):
        os.remove("cookies.txt")

    if upload_count > 0:
        await status_msg.edit_text(f"✅ Success! **{upload_count}** posts/reels yt-dlp ne sidha channel pe bhej diye! 🚀")
    else:
        await status_msg.edit_text("⚠️ Error: Shayad Instagram ne session verify nahi kiya, cookies fresh daaliye.")

if __name__ == "__main__":
    print("🚀 Ultimate yt-dlp Profile Downloader Started!")
    app.run()
