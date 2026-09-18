import os
import requests
import asyncio
from pyrogram import Client, filters

# ==========================================
# 1. BOT, CHANNEL & API CREDENTIALS
# ==========================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1002443275235  

# RapidAPI Key
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ==========================================
# 2. MAIN DOWNLOAD FUNCTION (RAPIDAPI METHOD)
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 API Insta Downloader me swagat hai!\nUsage: `/insta username`\nExample: `/insta therock`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!\nAise likho: `/insta therock`")
        return

    # Link ya username clean karna
    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    
    status_msg = await message.reply_text(f"🔍 RapidAPI se **{target_username}** ka data nikal raha hu... (No Blocks, Superfast ⚡)")

    # ==========================================
    # 3. FETCH DATA FROM RAPIDAPI
    # ==========================================
    url = "https://instagram-scraper-stable-api.p.rapidapi.com/get_ig_user_posts.php"
    
    payload = {
        "username_or_url": f"https://www.instagram.com/{target_username}/",
        "amount": "5"  # Abhi top 5 posts nikalenge
    }
    
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-host": "instagram-scraper-stable-api.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    try:
        # API call in background (non-blocking)
        response = await asyncio.to_thread(requests.post, url, data=payload, headers=headers)
        data = response.json()
    except Exception as e:
        await status_msg.edit_text(f"❌ API Request Failed: {e}")
        return

    # Error checking in API response
    if "error" in data or response.status_code != 200:
        await status_msg.edit_text(f"❌ API ne error diya: {data.get('message', 'Unknown Error')}")
        return

    # ==========================================
    # 4. PARSE MEDIA URLS FROM JSON
    # ==========================================
    media_list = []
    
    # API ke JSON structure se posts nikalna
    items = data.get('data', {}).get('items', []) or data.get('items', []) or data.get('data', [])
    
    if not items:
        await status_msg.edit_text(f"⚠️ **{target_username}** ki profile me koi post nahi mili ya account private hai.")
        return

    for item in items[:5]: # Top 5
        # Agar Carousel (Album/Multiple Photos) hai
        if item.get('carousel_media'):
            first_media = item['carousel_media'][0]
            if first_media.get('video_versions'):
                media_list.append((first_media['video_versions'][0]['url'], 'video'))
            elif first_media.get('image_versions2'):
                media_list.append((first_media['image_versions2']['candidates'][0]['url'], 'photo'))
        
        # Agar single Video hai
        elif item.get('video_versions'):
            media_list.append((item['video_versions'][0]['url'], 'video'))
            
        # Agar single Photo hai
        elif item.get('image_versions2'):
            media_list.append((item['image_versions2']['candidates'][0]['url'], 'photo'))

    if not media_list:
        await status_msg.edit_text("⚠️ Data toh mila, par media URLs nikalne me dikkat aayi.")
        return

    await status_msg.edit_text(f"📥 {len(media_list)} Media files mil gayi! Telegram channel me bhej raha hu...")

    # ==========================================
    # 5. UPLOAD TO CHANNEL
    # ==========================================
    upload_count = 0
    caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"

    for media_url, m_type in media_list:
        try:
            if m_type == 'video':
                await app.send_video(CHANNEL_ID, video=media_url, caption=caption_text)
            else:
                await app.send_photo(CHANNEL_ID, photo=media_url, caption=caption_text)
            upload_count += 1
            await asyncio.sleep(1) # Flood wait bachane ke liye chota sa delay
        except Exception as e:
            print(f"Failed to send to Telegram: {e}")
            
    await status_msg.edit_text(f"✅ Success! **{upload_count}** posts aapke channel pe upload ho gaye hain! 🚀")

if __name__ == "__main__":
    print("🚀 API Insta Downloader Bot Started Successfully!")
    app.run()
