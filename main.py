import os
import requests
import asyncio
import time
from pyrogram import Client, filters
from instagrapi import Client as InstaClient

# ==========================================
# 1. BOT & CHANNEL CREDENTIALS
# ==========================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1002443275235  

INSTA_SESSION = os.environ.get("INSTA_SESSION_ID")

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ==========================================
# 2. CUSTOM SCRAPER SETUP (MOBILE APP SPOOFING)
# ==========================================
cl = InstaClient()

# Human-like delay set kar rahe hain taaki IG ko shak na ho
cl.delay_range = [2, 5]

if INSTA_SESSION:
    try:
        # Session ID se direct Mobile API me login!
        cl.login_by_sessionid(INSTA_SESSION)
        print("✅ Custom Scraper: Logged in via Mobile API successfully!")
    except Exception as e:
        print(f"⚠️ Login Failed: {e}")

# ==========================================
# 3. MAIN DOWNLOAD FUNCTION
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 Custom Insta Scraper me swagat hai!\nUsage: `/insta username`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 Custom Scraper se **{target_username}** ka data nikal raha hu...")

    # Data fetch karne ka function (Background me chalega)
    def get_mobile_data():
        try:
            # Pehle mobile API se user ka hidden ID nikalna parta hai
            user_id = cl.user_id_from_username(target_username)
            # Phir uski latest 3 media fetch karte hain
            return cl.user_medias(user_id, amount=3), None
        except Exception as e:
            return None, str(e)

    medias, error = await asyncio.to_thread(get_mobile_data)

    if error:
        await status_msg.edit_text(f"❌ Custom Scraper Error: {error}\n(Shayad account private hai ya Session expire ho gaya)")
        return

    if not medias:
        await status_msg.edit_text(f"⚠️ **{target_username}** ki profile me koi post nahi mili.")
        return

    # ==========================================
    # 4. PARSE MEDIA URLS FROM MOBILE DATA
    # ==========================================
    media_list = []
    
    for m in medias:
        if m.media_type == 1:  # Single Photo
            media_list.append((str(m.thumbnail_url), 'photo'))
        elif m.media_type == 2:  # Single Video/Reel
            media_list.append((str(m.video_url), 'video'))
        elif m.media_type == 8:  # Carousel (Multiple)
            if m.resources:
                # Abhi sirf pehli slide uthayenge simplicity ke liye
                first = m.resources[0]
                if first.media_type == 1:
                    media_list.append((str(first.thumbnail_url), 'photo'))
                elif first.media_type == 2:
                    media_list.append((str(first.video_url), 'video'))

    if not media_list:
        await status_msg.edit_text("⚠️ Data mila, par download links extract nahi ho paye.")
        return

    await status_msg.edit_text(f"📥 {len(media_list)} Media files mil gayi! Server par download karke Telegram bhej raha hu...")

    # ==========================================
    # 5. DOWNLOAD & UPLOAD TO CHANNEL
    # ==========================================
    upload_count = 0
    caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"

    for index, (media_url, m_type) in enumerate(media_list):
        ext = ".mp4" if m_type == 'video' else ".jpg"
        temp_file = f"{target_username}_media_{index}_{int(time.time())}{ext}"
        
        try:
            dl_res = await asyncio.to_thread(requests.get, media_url, stream=True)
            if dl_res.status_code == 200:
                with open(temp_file, 'wb') as f:
                    for chunk in dl_res.iter_content(chunk_size=1024*1024):
                        if chunk: f.write(chunk)
            else:
                continue

            if m_type == 'video':
                await app.send_video(CHANNEL_ID, video=temp_file, caption=caption_text)
            else:
                await app.send_photo(CHANNEL_ID, photo=temp_file, caption=caption_text)
            
            upload_count += 1
            
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
            await asyncio.sleep(1.5) 
            
        except Exception as e:
            print(f"Upload Fail Hua: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
    await status_msg.edit_text(f"✅ Success! **{upload_count}** posts aapke channel pe upload ho gaye hain! 🚀")

if __name__ == "__main__":
    print("🚀 Custom Mobile Scraper Bot Started!")
    app.run()
