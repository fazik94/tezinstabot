import os
import re
import logging
import yt_dlp
import instaloader
import tempfile
import asyncio
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
# Kanal qo'shish uchun:
# CHANNELS = [{"id": "-1001234567890", "username": "kanal_username", "name": "Kanal nomi"}]

def get_platform(url: str) -> str:
    if 'instagram' in url:
        return 'Instagram'
    elif 'tiktok' in url or 'vm.tiktok' in url:
        return 'TikTok'
    elif 'youtube' in url or 'youtu.be' in url:
        return 'YouTube'
    return 'Video'

def is_supported_url(url: str) -> bool:
    patterns = [
        r'instagram\.com',
        r'tiktok\.com',
        r'vm\.tiktok\.com',
        r'vt\.tiktok\.com',
        r'youtube\.com',
        r'youtu\.be',
    ]
    return any(re.search(p, url) for p in patterns)

def extract_instagram_shortcode(url: str):
    match = re.search(r'/(p|reel|tv)/([A-Za-z0-9_-]+)', url)
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
    if not CHANNELS:
        return None
    keyboard = []
    for ch in CHANNELS:
        keyboard.append([InlineKeyboardButton(ch['name'], url=f"https://t.me/{ch['username']}")])
    keyboard.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        "🎬 <b>Video Yuklovchi Bot</b>\n\n"
        "📱 Qo'llab-quvvatlanadigan platformalar:\n"
        "• Instagram (video, rasm, reels)\n"
        "• TikTok (video)\n"
        "• YouTube (video)\n\n"
        "📎 Foydalanish: Havola yuboring!\n\n"
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
        "• Fayl 50 MB dan kichik bo'lishi kerak\n"
        "• Yopiq (private) sahifalar yuklanmaydi\n"
        "• Muammo bo'lsa /start bosing"
    )
    await update.message.reply_html(text)

async def download_instagram(url: str, tmpdir: str):
    """Instagram dan video yoki rasm yukla"""
    shortcode = extract_instagram_shortcode(url)
    if not shortcode:
        raise Exception("Instagram havolasi noto'g'ri")

    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=tmpdir,
        filename_pattern="{shortcode}",
        quiet=True,
    )

    post = instaloader.Post.from_shortcode(L.context, shortcode)
    L.download_post(post, target=tmpdir)

    # Fayllarni topish
    files = []
    for f in Path(tmpdir).iterdir():
        if f.suffix.lower() in ['.mp4', '.jpg', '.jpeg', '.png', '.webp']:
            files.append(str(f))

    return files, post.title or "Instagram post"

async def download_tiktok_youtube(url: str, tmpdir: str):
    """TikTok va YouTube dan yukla"""
    ydl_opts = {
        'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
        'format': 'best[filesize<50M]/best',
        'quiet': True,
        'no_warnings': True,
        'max_filesize': MAX_FILE_SIZE,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    files = [str(f) for f in Path(tmpdir).iterdir()
             if f.suffix.lower() in ['.mp4', '.mkv', '.webm', '.mov', '.avi', '.jpg', '.png']]

    title = info.get('title', 'Video')[:50] if info else 'Video'
    return files, title

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
            keyboard = get_subscribe_keyboard()
            await update.message.reply_html(
                "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
                reply_markup=keyboard
            )
            return

    platform = get_platform(url)
    status_msg = await update.message.reply_text(f"⏳ {platform} dan yuklanmoqda...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            if 'instagram' in url:
                files, title = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: asyncio.run(download_instagram_sync(url, tmpdir))
                )
            else:
                files, title = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: download_tiktok_youtube_sync(url, tmpdir)
                )

            if not files:
                raise Exception("Fayl topilmadi")

            await status_msg.edit_text("📤 Yuborilmoqda...")
            caption = f"✅ <b>{platform}</b>\n📹 {title}"

            for filepath in files[:10]:  # Max 10 fayl
                filesize = os.path.getsize(filepath)
                if filesize > MAX_FILE_SIZE:
                    continue

                ext = filepath.split('.')[-1].lower()
                with open(filepath, 'rb') as f:
                    if ext in ['mp4', 'mkv', 'webm', 'mov', 'avi']:
                        await update.message.reply_video(
                            video=f,
                            caption=caption,
                            parse_mode='HTML',
                            supports_streaming=True
                        )
                    else:
                        await update.message.reply_photo(
                            photo=f,
                            caption=caption,
                            parse_mode='HTML'
                        )
                caption = ""  # Faqat birinchi faylga caption

            await status_msg.delete()

    except instaloader.exceptions.InstaloaderException as e:
        err = str(e)
        if 'Login' in err or 'login' in err:
            msg = "❌ Bu post yuklanmadi.\n\nSabab: Instagram login talab qilmoqda. Ochiq (public) postlarni yuboring."
        elif 'not found' in err.lower():
            msg = "❌ Post topilmadi yoki o'chirilgan."
        else:
            msg = "❌ Instagram dan yuklab bo'lmadi. Ochiq post havolasini yuboring."
        await status_msg.edit_text(msg)

    except yt_dlp.utils.DownloadError as e:
        err = str(e).lower()
        if 'private' in err:
            msg = "❌ Bu video yopiq (private)."
        elif 'not available' in err:
            msg = "❌ Bu video mavjud emas."
        else:
            msg = "❌ Yuklab bo'lmadi. Havolani tekshirib qaytadan yuboring."
        await status_msg.edit_text(msg)

    except Exception as e:
        logger.error(f"Xato: {e}")
        await status_msg.edit_text(
            "❌ Xatolik yuz berdi.\n"
            "Havola to'g'riligini tekshirib qaytadan yuboring."
        )

def download_instagram_sync(url, tmpdir):
    """Sinxron Instagram yuklovchi"""
    shortcode = extract_instagram_shortcode(url)
    if not shortcode:
        raise Exception("Instagram havolasi noto'g'ri")

    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    post = instaloader.Post.from_shortcode(L.context, shortcode)
    L.download_post(post, target=Path(tmpdir))

    files = []
    for f in Path(tmpdir).rglob('*'):
        if f.suffix.lower() in ['.mp4', '.jpg', '.jpeg', '.png']:
            files.append(str(f))

    return files, (post.title or "Instagram post")[:50]

def download_tiktok_youtube_sync(url, tmpdir):
    """Sinxron TikTok/YouTube yuklovchi"""
    ydl_opts = {
        'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
        'format': 'best[filesize<50M]/best',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    files = [str(f) for f in Path(tmpdir).iterdir()
             if f.suffix.lower() in ['.mp4', '.mkv', '.webm', '.mov', '.avi', '.jpg', '.png']]
    title = (info.get('title', 'Video') or 'Video')[:50]
    return files, title

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
