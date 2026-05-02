# 🎬 Video Yuklovchi Telegram Bot

Instagram, YouTube va TikTok dan video yuklovchi bot.

## Qo'llab-quvvatlanadigan platformalar
- ✅ Instagram (video, rasm, reels, stories)
- ✅ YouTube (video)
- ✅ TikTok (video)

---

## 🚀 Railway.app ga deploy qilish

### 1-qadam: Bot token olish
1. Telegramda @BotFather ga yozing
2. `/newbot` buyrug'ini yuboring
3. Bot nomini kiriting (masalan: `VideoYuklovchi`)
4. Username kiriting (masalan: `video_yuklovchi_bot`)
5. Token oling — `1234567890:AABBcc...` ko'rinishida

### 2-qadam: GitHub ga yuklash
1. GitHub.com ga kiring
2. Yangi repository oching ("New repository")
3. Repository nomini kiriting (masalan: `video-bot`)
4. "Create repository" bosing
5. Barcha fayllarni yuklang:
   - `bot.py`
   - `requirements.txt`
   - `railway.toml`

### 3-qadam: Railway.app ga ulash
1. Railway.app ga kiring (GitHub bilan)
2. "New Project" bosing
3. "Deploy from GitHub repo" tanlang
4. O'z repo ingizni tanlang
5. "Add Variables" ga o'ting:
   - `BOT_TOKEN` = sizning bot tokeningiz
6. Deploy tugmachasini bosing

Bot 2-3 daqiqada ishga tushadi! ✅

---

## ⚙️ Sozlamalar (bot.py ichida)

### Majburiy obuna qo'shish
`bot.py` da `CHANNELS` listini to'ldiring:
```python
CHANNELS = [
    {
        "id": "-1001234567890",  # Kanal ID si
        "username": "kanal_username",  # @ belgisisiz
        "name": "Kanal nomi 📢"
    }
]
```

Kanal ID sini bilish uchun: @userinfobot ga kanal forward qiling.

---

## 📋 Buyruqlar
- `/start` — Botni boshlash
- `/help` — Yordam

---

## ⚠️ Eslatmalar
- Maksimal fayl hajmi: 50 MB
- Yopiq (private) sahifalar yuklanmaydi
- Bot 24/7 ishlaydi (Railway serverida)
