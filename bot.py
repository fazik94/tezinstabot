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

# Cookies fayl yo'li
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "instagram_cookies.txt")

CHANNELS = [
    {"id": "-1001886192313", "username": "ITdarslik", "name": "📚 IT kurs darsliklari"}
]

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

def download_with_ytdlp(url: str, tmpdir: str, use_cookies: bool = False):
    """yt-dlp orqali video yukla"""
    ydl_opts = {
        'outtmpl': f'{tmpdir}/%(title).50s.%(ext)s',
        'format': 'best[filesize<50M]/best',
        'quiet': True,
        'no_warnings': True,
    }

    if use_cookies and os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    files = [str(f) for f in Path(tmpdir).iterdir()
             if f.suffix.lower() in ['.mp4', '.mkv', '.webm', '.mov', '.avi', '.jpg', '.png']]

    title = (info.get('title', '') or '')[:50]
    return files, title

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Obuna tekshirish
    subscribed = await check_subscription(user.id, context.bot)
    if not subscribed:
        text = (
            f"👋 Salom, <b>{user.first_name}</b>!\n\n"
            "⚠️ Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:"
        )
        await update.message.reply_html(text, reply_markup=get_subscribe_keyboard())
        return

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

    # Start tugmalari
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Video yuklash", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("📢 Kanal", url="https://t.me/ITdarslik"),
         InlineKeyboardButton("ℹ️ Yordam", callback_data="help")],
    ])
    await update.message.reply_html(text, reply_markup=keyboard)

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
            is_instagram = 'instagram' in url
            files, title = download_with_ytdlp(url, tmpdir, use_cookies=is_instagram)

            if not files:
                raise Exception("Fayl topilmadi")

            await status_msg.edit_text("📤 Yuborilmoqda...")

            for filepath in files[:10]:
                filesize = os.path.getsize(filepath)
                if filesize > MAX_FILE_SIZE:
                    await status_msg.edit_text("❌ Fayl 50 MB dan katta.")
                    return

                ext = filepath.split('.')[-1].lower()
                caption = f"✅ <b>{platform}</b>" + (f"\n📹 {title}" if title else "")

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

            await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        err = str(e).lower()
        if 'login' in err or 'private' in err:
            msg = "❌ Bu post yopiq yoki login talab qiladi.\nFaqat ochiq postlar yuklash mumkin."
        elif 'not available' in err or 'not found' in err:
            msg = "❌ Video topilmadi yoki o'chirilgan."
        else:
            msg = "❌ Yuklab bo'lmadi. Havolani tekshiring."
        await status_msg.edit_text(msg)

    except Exception as e:
        logger.error(f"Xato: {e}")
        await status_msg.edit_text(
            "❌ Xatolik yuz berdi.\n"
            "Havolani tekshirib qaytadan yuboring."
        )

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        text = (
            "📖 <b>Yordam</b>\n\n"
            "1️⃣ Havola yuboring\n"
            "2️⃣ Bot yuklab yuboradi\n\n"
            "⚠️ <b>Eslatma:</b>\n"
            "• Faqat ochiq (public) postlar\n"
            "• Fayl 50 MB dan kichik bo'lishi kerak\n"
            "• Muammo bo'lsa /start bosing"
        )
        await query.edit_message_text(text, parse_mode='HTML')
        return

    # check_sub
    subscribed = await check_subscription(query.from_user.id, context.bot)
    if subscribed:
        user = query.from_user
        text = (
            f"✅ Obuna tasdiqlandi!\n\n"
            f"👋 Salom, <b>{user.first_name}</b>!\n\n"
            "🎬 <b>Video Yuklovchi Bot</b>\n\n"
            "📱 Qo'llab-quvvatlanadigan platformalar:\n"
            "• Instagram (video, reels)\n"
            "• TikTok (video)\n"
            "• YouTube (video)\n\n"
            "📎 Havola yuboring — men yuklab beraman!"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Kanal", url="https://t.me/ITdarslik"),
             InlineKeyboardButton("ℹ️ Yordam", callback_data="help")],
        ])
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await query.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$|^help$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
