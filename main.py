import os
import requests
import asyncio
import time
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
# 2. MAIN DOWNLOAD FUNCTION (RAPIDAPI)
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    if message.command[0] == "start":
        await message.reply_text("🚀 API Insta Downloader me swagat hai!\nUsage: `/insta username`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!\nAise likho: `/insta therock`")
        return

    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 RapidAPI se **{target_username}** ka data nikal raha hu... (⚡ Superfast)")

    # ==========================================
    # 3. FETCH DATA FROM RAPIDAPI
    # ==========================================
    url = "https://instagram-scraper-stable-api.p.rapidapi.com/get_ig_user_posts.php"
    
    payload = {
        "username_or_url": f"https://www.instagram.com/{target_username}/",
        "amount": "5"  # Top 5 posts
    }
    
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-host": "instagram-scraper-stable-api.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    try:
        response = await asyncio.to_thread(requests.post, url, data=payload, headers=headers)
        data = response.json()
    except Exception as e:
        await status_msg.edit_text(f"❌ API Request Failed: {e}")
        return

    # ==========================================
    # 4. PARSE MEDIA URLS FROM JSON
    # ==========================================
    media_list = []
    
    posts = data.get('posts', [])
    
    if not posts:
        await status_msg.edit_text(f"⚠️ **{target_username}** ki profile me koi post nahi mili ya account private hai.")
        return

    for post_item in posts[:5]:
        node = post_item.get('node', {})
        
        # Condition 1: Agar Carousel (Multiple Photos/Videos) hai
        if node.get('carousel_media'):
            first_media = node['carousel_media'][0]
            if first_media.get('video_versions'):
                media_list.append((first_media['video_versions'][0]['url'], 'video'))
            elif first_media.get('image_versions2') and first_media['image_versions2'].get('candidates'):
                media_list.append((first_media['image_versions2']['candidates'][0]['url'], 'photo'))
        
        # Condition 2: Agar single Video/Reel hai
        elif node.get('video_versions'):
            media_list.append((node['video_versions'][0]['url'], 'video'))
            
        # Condition 3: Agar single Photo hai
        elif node.get('image_versions2') and node['image_versions2'].get('candidates'):
            media_list.append((node['image_versions2']['candidates'][0]['url'], 'photo'))

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
        # File ka extension aur naam decide karna
        ext = ".mp4" if m_type == 'video' else ".jpg"
        temp_file = f"{target_username}_media_{index}_{int(time.time())}{ext}"
        
        try:
            # 1. Instagram se file download karo
            dl_res = await asyncio.to_thread(requests.get, media_url, stream=True)
            if dl_res.status_code == 200:
                with open(temp_file, 'wb') as f:
                    for chunk in dl_res.iter_content(chunk_size=1024*1024):
                        if chunk: f.write(chunk)
            else:
                print(f"Failed to download {media_url}")
                continue

            # 2. Telegram par upload karo
            if m_type == 'video':
                await app.send_video(CHANNEL_ID, video=temp_file, caption=caption_text)
            else:
                await app.send_photo(CHANNEL_ID, photo=temp_file, caption=caption_text)
            
            upload_count += 1
            
            # 3. File upload hone ke baad server se delete kardo
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
            await asyncio.sleep(1) # Flood wait bachane ke liye chota sa delay
            
        except Exception as e:
            print(f"Upload Fail Hua: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
    await status_msg.edit_text(f"✅ Success! **{upload_count}** posts aapke channel pe upload ho gaye hain! 🚀")

if __name__ == "__main__":
    print("🚀 Bot Started with RapidAPI & Local Downloader!")
    app.run()
