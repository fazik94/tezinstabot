import os
import re
import logging
import tempfile
import yt_dlp
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MAX_FILE_SIZE = 50 * 1024 * 1024

CHANNELS = [
    {"id": "-1001886192313", "username": "ITdarslik", "name": "📚 IT kurs darsliklari"}
]

COOKIES_FILE = "instagram_cookies.txt"

def is_url(text):
    return bool(re.search(r'(instagram|tiktok|youtube|youtu\.be|vm\.tiktok)', text))

def platform_name(url):
    if 'instagram' in url: return 'Instagram'
    if 'tiktok' in url: return 'TikTok'
    if 'youtube' in url or 'youtu.be' in url: return 'YouTube'
    return 'Video'

async def is_subscribed(user_id, bot):
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(ch['id'], user_id)
            if m.status in ['left', 'kicked']:
                return False
        except:
            pass
    return True

def sub_keyboard():
    kb = [[InlineKeyboardButton(ch['name'], url=f"https://t.me/{ch['username']}")] for ch in CHANNELS]
    kb.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check")])
    return InlineKeyboardMarkup(kb)

def main_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Kanal", url="https://t.me/ITdarslik"),
        InlineKeyboardButton("ℹ️ Yordam", callback_data="yordam")
    ]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_subscribed(user.id, context.bot):
        await update.message.reply_html(
            f"👋 Salom <b>{user.first_name}</b>!\n\n⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:",
            reply_markup=sub_keyboard()
        )
        return
    await update.message.reply_html(
        f"👋 Salom <b>{user.first_name}</b>!\n\n🎬 <b>Video Yuklovchi Bot</b>\n\n"
        "Quyidagi platformalardan video yuklay olasiz:\n"
        "• Instagram (reels, video)\n• TikTok\n• YouTube\n\n📎 Havola yuboring!",
        reply_markup=main_keyboard()
    )

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "check":
        if await is_subscribed(q.from_user.id, context.bot):
            await q.edit_message_text(
                "✅ Obuna tasdiqlandi!\n\n🎬 Havola yuboring — yuklab beraman!",
                parse_mode='HTML', reply_markup=main_keyboard()
            )
        else:
            await q.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
    elif q.data == "yordam":
        await q.edit_message_text(
            "ℹ️ <b>Yordam</b>\n\n1️⃣ Havola yuboring\n2️⃣ Bot yuklab yuboradi\n\n"
            "⚠️ Faqat ochiq postlar\n⚠️ Max 50 MB",
            parse_mode='HTML'
        )

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_url(url):
        await update.message.reply_text("❌ Instagram, TikTok yoki YouTube havolasini yuboring.")
        return
    if not await is_subscribed(update.effective_user.id, context.bot):
        await update.message.reply_html("⚠️ Avval kanalga obuna bo'ling:", reply_markup=sub_keyboard())
        return

    pname = platform_name(url)
    msg = await update.message.reply_text(f"⏳ {pname} dan yuklanmoqda...")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            opts = {
                'outtmpl': f'{tmp}/%(title).40s.%(ext)s',
                'format': 'best[filesize<50M]/best',
                'quiet': True,
                'no_warnings': True,
            }
            if 'instagram' in url and os.path.exists(COOKIES_FILE):
                opts['cookiefile'] = COOKIES_FILE

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            files = list(Path(tmp).iterdir())
            if not files:
                raise Exception("Fayl topilmadi")

            filepath = str(files[0])
            if os.path.getsize(filepath) > MAX_FILE_SIZE:
                await msg.edit_text("❌ Fayl 50 MB dan katta.")
                return

            title = (info.get('title') or '')[:40]
            caption = f"✅ <b>{pname}</b>" + (f"\n📹 {title}" if title else "")
            await msg.edit_text("📤 Yuborilmoqda...")

            ext = filepath.split('.')[-1].lower()
            with open(filepath, 'rb') as f:
                if ext in ['mp4', 'mkv', 'webm', 'mov', 'avi']:
                    await update.message.reply_video(video=f, caption=caption, parse_mode='HTML', supports_streaming=True)
                elif ext in ['jpg', 'jpeg', 'png', 'webp']:
                    await update.message.reply_photo(photo=f, caption=caption, parse_mode='HTML')
                else:
                    await update.message.reply_document(document=f, caption=caption, parse_mode='HTML')
            await msg.delete()
    except Exception as e:
        logger.error(f"Xato: {e}")
        err = str(e).lower()
        if 'private' in err or 'login' in err:
            text = "❌ Bu post yopiq. Faqat ochiq postlar yuklanadi."
        elif 'not available' in err:
            text = "❌ Video topilmadi yoki o'chirilgan."
        else:
            text = "❌ Yuklab bo'lmadi. Havolani tekshiring."
        await msg.edit_text(text)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN yo'q!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download))
    logger.info("Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
