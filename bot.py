import os
import re
import logging
import yt_dlp
import requests
import tempfile
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

CHANNELS = []
# Kanal qo'shish:
# CHANNELS = [{"id": "-1001234567890", "username": "username", "name": "Kanal nomi"}]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def get_platform(url: str) -> str:
    if 'instagram' in url:
        return 'Instagram'
    elif 'tiktok' in url:
        return 'TikTok'
    elif 'youtube' in url or 'youtu.be' in url:
        return 'YouTube'
    return 'Video'

def is_supported_url(url: str) -> bool:
    patterns = [
        r'instagram\.com',
        r'tiktok\.com',
        r'vm\.tiktok\.com',
        r'youtube\.com',
        r'youtu\.be',
    ]
    return any(re.search(p, url) for p in patterns)

def extract_instagram_shortcode(url: str):
    match = re.search(r'/(p|reel|tv|stories)/([A-Za-z0-9_-]+)', url)
    if match:
        return match.group(2)
    return None

async def check_subscription(user_id: int, bot) -> bool:
    if not CHANNELS:
        return True
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(channel['id'], user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            pass
    return True

def get_subscribe_keyboard():
    keyboard = []
    for ch in CHANNELS:
        keyboard.append([InlineKeyboardButton(ch['name'], url=f"https://t.me/{ch['username']}")])
    keyboard.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(keyboard)

def get_instagram_url(url: str):
    """Instagram video URL ni olish — bir necha API orqali urinib ko'radi"""
    shortcode = extract_instagram_shortcode(url)
    if not shortcode:
        raise Exception("Instagram havolasi noto'g'ri")

    # 1-urinish: SaveIG API
    try:
        api_url = f"https://instagram-downloader-download-instagram-videos-stories1.p.rapidapi.com/get-info-rapidapi"
        res = requests.get(
            api_url,
            params={"url": url},
            headers={**HEADERS, "x-rapidapi-host": "instagram-downloader-download-instagram-videos-stories1.p.rapidapi.com"},
            timeout=10
        )
        data = res.json()
        if data.get("url"):
            return data["url"], "Instagram"
    except Exception as e:
        logger.warning(f"1-API xato: {e}")

    # 2-urinish: SnapSave API
    try:
        res = requests.post(
            "https://snapsave.app/action.php",
            data={"url": url},
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        # Video URL ni HTML dan chiqarib olish
        video_match = re.search(r'"(https://[^"]+\.mp4[^"]*)"', res.text)
        if video_match:
            return video_match.group(1), "Instagram"
    except Exception as e:
        logger.warning(f"2-API xato: {e}")

    # 3-urinish: SSSTik/FastDL orqali
    try:
        res = requests.post(
            "https://fastdl.app/api/convert",
            json={"url": url},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=10
        )
        data = res.json()
        if data.get("url"):
            return data["url"], "Instagram"
        # medias listdan olish
        medias = data.get("medias", [])
        if medias:
            return medias[0].get("url"), "Instagram"
    except Exception as e:
        logger.warning(f"3-API xato: {e}")

    # 4-urinish: yt-dlp bilan
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get('url'):
                return info['url'], info.get('title', 'Instagram')
    except Exception as e:
        logger.warning(f"yt-dlp xato: {e}")

    raise Exception("Instagram dan yuklab bo'lmadi")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        "🎬 <b>Video Yuklovchi Bot</b>\n\n"
        "📱 Qo'llab-quvvatlanadigan platformalar:\n"
        "• Instagram (video, reels)\n"
        "• TikTok (video)\n"
        "• YouTube (video)\n\n"
        "📎 Havola yuboring — men yuklab beraman!\n\n"
        "<b>Misol:</b>\n"
        "<code>https://www.instagram.com/reel/ABC123/</code>\n"
        "<code>https://www.tiktok.com/@user/video/123</code>"
    )
    await update.message.reply_html(text)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>Yordam</b>\n\n"
        "1️⃣ Havola yuboring\n"
        "2️⃣ Bot yuklab yuboradi\n\n"
        "⚠️ <b>Eslatma:</b>\n"
        "• Faqat ochiq (public) postlar\n"
        "• Fayl 50 MB dan kichik bo'lishi kerak\n"
        "• Muammo bo'lsa /start bosing"
    )
    await update.message.reply_html(text)

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not is_supported_url(url):
        await update.message.reply_text(
            "❌ Bu havola qo'llab-quvvatlanmaydi!\n\n"
            "Instagram, TikTok yoki YouTube havolasini yuboring."
        )
        return

    # Obuna tekshirish
    if CHANNELS:
        subscribed = await check_subscription(update.effective_user.id, context.bot)
        if not subscribed:
            await update.message.reply_html(
                "⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:",
                reply_markup=get_subscribe_keyboard()
            )
            return

    platform = get_platform(url)
    status_msg = await update.message.reply_text(f"⏳ {platform} dan yuklanmoqda...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:

            if 'instagram' in url:
                # Instagram uchun maxsus funksiya
                await status_msg.edit_text("⏳ Instagram dan yuklanmoqda...")
                try:
                    video_url, title = get_instagram_url(url)
                    # Video ni yuklab olish
                    await status_msg.edit_text("📥 Fayl yuklanmoqda...")
                    response = requests.get(video_url, headers=HEADERS, stream=True, timeout=30)
                    filepath = os.path.join(tmpdir, "instagram_video.mp4")
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    filesize = os.path.getsize(filepath)
                    if filesize > MAX_FILE_SIZE:
                        await status_msg.edit_text("❌ Fayl 50 MB dan katta.")
                        return
                    if filesize < 1000:
                        raise Exception("Fayl juda kichik — URL ishlamadi")

                    await status_msg.edit_text("📤 Yuborilmoqda...")
                    with open(filepath, 'rb') as f:
                        await update.message.reply_video(
                            video=f,
                            caption=f"✅ <b>Instagram</b>",
                            parse_mode='HTML',
                            supports_streaming=True
                        )
                    await status_msg.delete()

                except Exception as e:
                    logger.error(f"Instagram xato: {e}")
                    await status_msg.edit_text(
                        "❌ Instagram dan yuklab bo'lmadi.\n\n"
                        "Sabab: Instagram ochiq (public) postlar uchun ishlaydi.\n"
                        "Havola to'g'riligini tekshiring."
                    )

            else:
                # TikTok va YouTube uchun yt-dlp
                ydl_opts = {
                    'outtmpl': f'{tmpdir}/%(title).50s.%(ext)s',
                    'format': 'best[filesize<50M]/best',
                    'quiet': True,
                    'no_warnings': True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                files = [str(f) for f in Path(tmpdir).iterdir()
                         if f.suffix.lower() in ['.mp4', '.mkv', '.webm', '.mov', '.avi']]

                if not files:
                    raise Exception("Fayl topilmadi")

                title = (info.get('title', '') or '')[:50]
                await status_msg.edit_text("📤 Yuborilmoqda...")

                filepath = files[0]
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    await status_msg.edit_text("❌ Fayl 50 MB dan katta.")
                    return

                with open(filepath, 'rb') as f:
                    await update.message.reply_video(
                        video=f,
                        caption=f"✅ <b>{platform}</b>\n📹 {title}",
                        parse_mode='HTML',
                        supports_streaming=True
                    )
                await status_msg.delete()

    except Exception as e:
        logger.error(f"Umumiy xato: {e}")
        await status_msg.edit_text(
            "❌ Xatolik yuz berdi.\n"
            "Havola to'g'riligini tekshirib qaytadan yuboring."
        )

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subscribed = await check_subscription(query.from_user.id, context.bot)
    if subscribed:
        await query.edit_message_text("✅ Obuna tasdiqlandi!\n\nHavola yuboring.")
    else:
        await query.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
