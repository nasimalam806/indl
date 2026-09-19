import os
import glob
import asyncio
import yt_dlp
import requests
import time
import shutil
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from instagrapi import Client as InstaClient

# ==========================================
# 1. CREDENTIALS & VARIABLES
# ==========================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = -1002443275235  

INSTA_SESSION = os.environ.get("INSTA_SESSION_ID")

app = Client("insta_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# 🔥 Global variable for /stop command
STOP_PROCESS = False

# ==========================================
# 2. INSTAGRAPI SCANNER (UNLIMITED SCROLL)
# ==========================================
def extract_media_from_profile(username):
    if not INSTA_SESSION:
        raise Exception("INSTA_SESSION_ID Railway variables me nahi hai!")

    cl = InstaClient()
    try:
        cl.login_by_sessionid(INSTA_SESSION)
    except Exception as e:
        raise Exception(f"Login failed! Session ID expire ho gaya hai. Naya Session ID dalein. Error: {e}")

    try:
        user_id = cl.user_id_from_username(username)
    except Exception as e:
        raise Exception(f"Username nahi mila. Error: {e}")

    # Fetch ALL Grid Posts and ALL Reels (Limit 200 set hai, badha bhi sakte hain)
    grid_posts = cl.user_medias(user_id, amount=250)
    reels_clips = cl.user_clips(user_id, amount=250)
    
    all_media = grid_posts + reels_clips
    
    video_ig_links = []
    direct_image_urls = []

    for m in all_media:
        shortcode_url = f"https://www.instagram.com/p/{m.code}/"
        
        # 1 = Photo, 2 = Video/Reel, 8 = Carousel/Album
        if m.media_type == 1:
            direct_image_urls.append(str(m.thumbnail_url))
        elif m.media_type == 2:
            video_ig_links.append(shortcode_url)
        elif m.media_type == 8:
            has_video = False
            for res in m.resources:
                if res.media_type == 1:
                    direct_image_urls.append(str(res.thumbnail_url))
                elif res.media_type == 2:
                    has_video = True
            
            # Agar carousel me koi video hai, to yt-dlp ko shortcode de do
            if has_video:
                video_ig_links.append(shortcode_url)

    return list(set(video_ig_links)), list(set(direct_image_urls))

# ==========================================
# 3. STOP COMMAND & CHUNK HELPER
# ==========================================
@app.on_message(filters.command("stop"))
async def stop_process(client, message):
    global STOP_PROCESS
    STOP_PROCESS = True
    await message.reply_text("🛑 **STOP COMMAND RECEIVED!**\nAbhi chal raha task ruk jayega aur download hui saari files delete ho jayengi.")

def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ==========================================
# 4. YT-DLP VIDEO DOWNLOADER
# ==========================================
def download_videos_ytdl(links, username):
    if not links: return True, "No links"
        
    with open("cookies.txt", "w") as f:
        f.write(f"# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTA_SESSION}\n")
            
    ydl_opts = {
        'outtmpl': f'{username}/%(id)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'ignoreerrors': True,
        'cookiefile': 'cookies.txt',
        'sleep_interval': 1,
        'max_sleep_interval': 3,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(links)
        return True, "Success"
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists("cookies.txt"): os.remove("cookies.txt")

# ==========================================
# 5. MAIN BOT LOGIC
# ==========================================
@app.on_message(filters.command("insta") | filters.command("start"))
async def fetch_insta(client, message):
    global STOP_PROCESS
    
    if message.command[0] == "start":
        await message.reply_text("🚀 Unlimited Pro Downloader Bot!\nUsage: `/insta username`\nTo abort: `/stop`")
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Bhai, username ya link dena padega!")
        return

    STOP_PROCESS = False
    
    target_username = message.command[1].replace("https://www.instagram.com/", "").replace("/", "").split("?")[0]
    status_msg = await message.reply_text(f"🔍 **{target_username}** ki profile Instagrapi se scan ho rahi hai...\n(100% Reels aur Posts dhundh raha hu ⏳)")

    try:
        video_links, image_urls = await asyncio.to_thread(extract_media_from_profile, target_username)
    except Exception as e:
        await status_msg.edit_text(f"❌ Scanner Error: {e}")
        return

    if STOP_PROCESS:
        await status_msg.edit_text("🚫 Process Cancelled.")
        return

    if not video_links and not image_urls:
        await status_msg.edit_text(f"⚠️ Koi post ya reel nahi mili.")
        return

    await status_msg.edit_text(f"🔗 Scan Complete!\n🎥 Reels/Videos (yt-dlp): **{len(video_links)}**\n📸 Photos (Direct): **{len(image_urls)}**\n\n⏳ Ab Download aur Album Upload start ho raha hai...")

    if not os.path.exists(target_username):
        os.makedirs(target_username)

    upload_count = 0
    caption_text = f"🔥 Source: [@{target_username}](https://instagram.com/{target_username})"

    # --- PHASE A: PHOTOS UPLOAD (ALBUMS OF 10) ---
    if image_urls:
        downloaded_images = []
        for i, img_url in enumerate(image_urls):
            if STOP_PROCESS: break
            try:
                temp_img = f"{target_username}/photo_{i}_{int(time.time())}.jpg"
                dl_res = await asyncio.to_thread(requests.get, img_url, stream=True)
                if dl_res.status_code == 200:
                    with open(temp_img, 'wb') as f:
                        for chunk in dl_res.iter_content(1024): f.write(chunk)
                    downloaded_images.append(temp_img)
            except Exception as e:
                print(f"Image DL error: {e}")

        for chunk in chunk_list(downloaded_images, 10):
            if STOP_PROCESS: break
            media_group = [InputMediaPhoto(media=img_path, caption=caption_text if idx == 0 else "") for idx, img_path in enumerate(chunk)]
            
            if media_group:
                try:
                    await app.send_media_group(CHANNEL_ID, media=media_group)
                    upload_count += len(media_group)
                    await status_msg.edit_text(f"📸 Uploaded {upload_count} media files... 💤")
                    await asyncio.sleep(12) 
                except Exception as e:
                    print(f"Photo Album Upload Error: {e}")
                    
        for img_path in downloaded_images:
            if os.path.exists(img_path): os.remove(img_path)

    if STOP_PROCESS:
        shutil.rmtree(target_username, ignore_errors=True)
        await status_msg.edit_text("🚫 Process Cancelled via /stop command.")
        return

    # --- PHASE B: VIDEOS UPLOAD (ALBUMS OF 10 WITH FORCE VIDEO) ---
    if video_links:
        await status_msg.edit_text(f"📥 Videos download ho rahi hain (yt-dlp)...")
        await asyncio.to_thread(download_videos_ytdl, video_links, target_username)
            
        if STOP_PROCESS:
            shutil.rmtree(target_username, ignore_errors=True)
            await status_msg.edit_text("🚫 Process Cancelled via /stop command.")
            return

        video_files = [f for f in glob.glob(f"{target_username}/*") if f.lower().endswith(('.mp4', '.webm', '.mkv', '.mov'))]
        
        # 🔥 FIX: Ab video chunk bhi 10 ka kar diya gaya hai
        for chunk in chunk_list(video_files, 10):
            if STOP_PROCESS: break
            # 🔥 FIX: supports_streaming=True lagaya taki GIF na bane!
            media_group = [InputMediaVideo(media=vid_path, caption=caption_text if idx == 0 else "", supports_streaming=True) for idx, vid_path in enumerate(chunk)]
            
            if media_group:
                try:
                    await app.send_media_group(CHANNEL_ID, media=media_group)
                    upload_count += len(media_group)
                    await status_msg.edit_text(f"🎥 Uploaded {upload_count} media files... 💤")
                    await asyncio.sleep(15) 
                except Exception as e:
                    print(f"Video Album Upload Error: {e}")
                    # Fallback if album fails (force video here as well)
                    for vid in chunk:
                        try:
                            await app.send_video(CHANNEL_ID, video=vid, caption=caption_text, supports_streaming=True)
                            upload_count += 1
                            await asyncio.sleep(3)
                        except: pass
                    
        for vid_path in video_files:
            if os.path.exists(vid_path): os.remove(vid_path)

    shutil.rmtree(target_username, ignore_errors=True)

    if STOP_PROCESS:
        await status_msg.edit_text(f"🛑 Stopped manually! {upload_count} media files upload hui hain.")
    elif upload_count > 0:
        await status_msg.edit_text(f"✅ BINGO! **{upload_count}** Media Files channel pe Album format mein successfully upload ho chuki hain! 🚀🔥")
    else:
        await status_msg.edit_text(f"⚠️ Media mili par upload nahi ho payi. Logs check karein.")

if __name__ == "__main__":
    print("🚀 Pro Album Downloader Bot Started!")
    app.run()
