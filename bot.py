import os
import re
import logging
import yt_dlp
import requests
import tempfile
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

# Majburiy obuna kanallari (bo'sh qoldirsa ham ishlaydi)
CHANNELS = [
    # {"id": "-1001234567890", "username": "kanal_username", "name": "Kanal nomi"}
]

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (Telegram limiti)

def is_supported_url(url: str) -> bool:
    patterns = [
        r'(https?://)?(www\.)?instagram\.com',
        r'(https?://)?(www\.)?youtube\.com',
        r'(https?://)?(www\.)?youtu\.be',
        r'(https?://)?(www\.)?tiktok\.com',
        r'(https?://)?vm\.tiktok\.com',
        r'(https?://)?vt\.tiktok\.com',
    ]
    return any(re.search(p, url) for p in patterns)

def get_platform(url: str) -> str:
    if 'instagram' in url:
        return 'Instagram'
    elif 'youtube' in url or 'youtu.be' in url:
        return 'YouTube'
    elif 'tiktok' in url:
        return 'TikTok'
    return 'Noma\'lum'

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
        keyboard.append([InlineKeyboardButton(
            ch['name'], url=f"https://t.me/{ch['username']}"
        )])
    keyboard.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        "🎬 Men <b>video yuklovchi botman</b>!\n\n"
        "📱 Qo'llab-quvvatlanadigan platformalar:\n"
        "• Instagram (video, rasm, reels)\n"
        "• YouTube (video)\n"
        "• TikTok (video)\n\n"
        "📎 Foydalanish: Havola yuboring, men yuklаb beraman!\n\n"
        "Misol:\n"
        "<code>https://www.instagram.com/p/...</code>\n"
        "<code>https://www.youtube.com/watch?v=...</code>\n"
        "<code>https://www.tiktok.com/@user/video/...</code>"
    )
    await update.message.reply_html(text)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>Yordam</b>\n\n"
        "1️⃣ Instagram, YouTube yoki TikTok havolasini yuboring\n"
        "2️⃣ Bot avtomatik yuklab yuboradi\n\n"
        "⚠️ <b>Eslatma:</b>\n"
        "• Fayl 50 MB dan kichik bo'lishi kerak\n"
        "• Yopiq (private) sahifalar yuklanmaydi\n"
        "• YouTube da faqat ochiq videolar\n\n"
        "❓ Muammo bo'lsa /start bosing"
    )
    await update.message.reply_html(text)

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not is_supported_url(url):
        await update.message.reply_text(
            "❌ Bu havola qo'llab-quvvatlanmaydi!\n\n"
            "Instagram, YouTube yoki TikTok havolasini yuboring."
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
    status_msg = await update.message.reply_text(
        f"⏳ {platform} dan yuklanmoqda... Biroz kuting."
    )

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
                'format': 'best[filesize<50M]/best',
                'quiet': True,
                'no_warnings': True,
                'max_filesize': MAX_FILE_SIZE,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            # Fayl topish
            files = os.listdir(tmpdir)
            if not files:
                raise Exception("Fayl yuklanmadi")

            filepath = os.path.join(tmpdir, files[0])
            filesize = os.path.getsize(filepath)

            if filesize > MAX_FILE_SIZE:
                await status_msg.edit_text(
                    "❌ Fayl juda katta (50 MB dan oshib ketdi).\n"
                    "Qisqaroq video yuboring."
                )
                return

            title = info.get('title', 'Video')[:50]
            caption = f"✅ <b>{platform}</b>\n📹 {title}"

            await status_msg.edit_text("📤 Yuborilmoqda...")

            ext = files[0].split('.')[-1].lower()
            with open(filepath, 'rb') as f:
                if ext in ['mp4', 'mkv', 'webm', 'mov', 'avi']:
                    await update.message.reply_video(
                        video=f,
                        caption=caption,
                        parse_mode='HTML',
                        supports_streaming=True
                    )
                elif ext in ['jpg', 'jpeg', 'png', 'webp']:
                    await update.message.reply_photo(
                        photo=f,
                        caption=caption,
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_document(
                        document=f,
                        caption=caption,
                        parse_mode='HTML'
                    )

            await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if 'Private' in err or 'private' in err:
            msg = "❌ Bu post yopiq (private). Ochiq postlar yuklash mumkin."
        elif 'not available' in err:
            msg = "❌ Bu video mavjud emas yoki o'chirilgan."
        else:
            msg = f"❌ Yuklab bo'lmadi.\n\nSabab: Havola noto'g'ri yoki video yopiq bo'lishi mumkin."
        await status_msg.edit_text(msg)

    except Exception as e:
        logger.error(f"Xato: {e}")
        await status_msg.edit_text(
            "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.\n"
            "Muammo davom etsa /start bosing."
        )

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    subscribed = await check_subscription(query.from_user.id, context.bot)
    if subscribed:
        await query.edit_message_text(
            "✅ Obuna tasdiqlandi!\n\n"
            "Endi Instagram, YouTube yoki TikTok havolasini yuboring."
        )
    else:
        await query.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylini tekshiring.")
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
