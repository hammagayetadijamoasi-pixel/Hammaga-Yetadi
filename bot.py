import logging
import sqlite3
import time
import asyncio
import json
import urllib.parse
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    filters
)

# --- SOZLAMALAR ---
TOKEN = "8523951175:AAEw7Mfv7Y-LT3VN7GWunSkZsTmgurfl_gE" # O'z tokeningiz
ADMIN_ID = 6787735720
WEBAPP_URL = "https://hammagayetadijamoasi-pixel.github.io/Hammaga-Yetadi"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BAZA ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, email TEXT, joined_at INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY, title TEXT, text TEXT, link TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, channel_name TEXT)''')
    conn.commit()
    conn.close()

def add_or_update_user(user_id, full_name, username, email=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        if email: cursor.execute('UPDATE users SET full_name=?, username=?, email=? WHERE user_id=?', (full_name, username, email, user_id))
        else: cursor.execute('UPDATE users SET full_name=?, username=? WHERE user_id=?', (full_name, username, user_id))
    else:
        cursor.execute('INSERT INTO users (user_id, full_name, username, email, joined_at) VALUES (?, ?, ?, ?, ?)', (user_id, full_name, username, email, int(time.time())))
    conn.commit()
    conn.close()

def get_user_email(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT email FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res and res[0] else "0"

def get_all_users():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    return [row[0] for row in cursor.fetchall()]

# --- KANAL & REKLAMA ---
def add_channel_db(cid, cname):
    conn = sqlite3.connect('bot_database.db')
    clean = cid.replace('https://t.me/', '@')
    if not clean.startswith('@') and not clean.startswith('-100'): clean = '@' + clean
    conn.cursor().execute('INSERT OR REPLACE INTO channels VALUES (?, ?)', (clean, cname))
    conn.commit()
    conn.close()

def del_channel_db(cid):
    conn = sqlite3.connect('bot_database.db')
    conn.cursor().execute('DELETE FROM channels WHERE channel_id = ?', (cid,))
    conn.commit()
    conn.close()

def get_channels_db():
    conn = sqlite3.connect('bot_database.db')
    cur = conn.cursor()
    cur.execute('SELECT channel_id, channel_name FROM channels')
    res = [{"id": r[0], "name": r[1], "url": f"https://t.me/{r[0].replace('@','')}"} for r in cur.fetchall()]
    conn.close()
    return res

def update_ad(t, x, l):
    conn = sqlite3.connect('bot_database.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM ads')
    cur.execute('INSERT INTO ads (title, text, link) VALUES (?, ?, ?)', (t, x, l))
    conn.commit()
    conn.close()

def get_current_ad():
    conn = sqlite3.connect('bot_database.db')
    cur = conn.cursor()
    try:
        cur.execute('SELECT title, text, link FROM ads LIMIT 1')
        ad = cur.fetchone()
    except: ad = None
    conn.close()
    return ad

init_db()

# --- MANTIQ ---
async def get_user_status_code(user_id: int, bot):
    channels = get_channels_db()
    if not channels: return "1"
    status_code = ""
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                status_code += "1"
            else: status_code += "0"
        except: status_code += "0"
    return status_code

async def generate_webapp_url(user, bot):
    status_code = await get_user_status_code(user.id, bot)
    email_status = "1" if get_user_email(user.id) != "0" else "0"
    timestamp = int(time.time())
    user_name = urllib.parse.quote(user.first_name)
    channels_json = urllib.parse.quote(json.dumps(get_channels_db()))
    
    base_url = f"{WEBAPP_URL}/index.html?s={status_code}&e={email_status}&n={user_name}&id={user.id}&v={timestamp}&ch={channels_json}"
    
    ad = get_current_ad()
    if ad:
        base_url += f"&at={urllib.parse.quote(ad[0])}&ax={urllib.parse.quote(ad[1])}&al={urllib.parse.quote(ad[2])}"
    return base_url, status_code

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_or_update_user(user.id, user.full_name, user.username)
    final_url, status_code = await generate_webapp_url(user, context.bot)
    
    if "0" not in status_code:
        btn_text = "✨ Pro Versiya (Kirish)"
        msg = f"👋 <b>Salom, {user.first_name}!</b>\n\n✅ Siz a'zosiz. Pro versiya va Yaxshi AI xizmatidan bepul foydalaning:"
    else:
        btn_text = "🔒 A'zo bo'lish va Tekshirish"
        msg = f"👋 <b>Salom, {user.first_name}!</b>\n\n🚫 Botdan foydalanish uchun kanallarga a'zo bo'ling, so'ngra tugmani bosing."

    kb = [[KeyboardButton(text=btn_text, web_app=WebAppInfo(url=final_url))]]
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode=ParseMode.HTML)

# --- WEB APP HANDLER ---
async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = update.effective_message.web_app_data.data 
    
    if data == "check":
        final_url, status_code = await generate_webapp_url(user, context.bot)
        if "0" not in status_code:
            text = "✅ <b>Tabriklaymiz!</b> Siz a'zo bo'ldingiz."
            btn = "✨ Pro Versiya (Kirish)"
        else:
            text = "❌ <b>Hali hammasiga a'zo emassiz!</b>\nQayta urinib ko'ring."
            btn = "🔒 A'zo bo'lish va Tekshirish"
        
        kb = [[KeyboardButton(text=btn, web_app=WebAppInfo(url=final_url))]]
        await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode=ParseMode.HTML)

    elif "@" in data:
        add_or_update_user(user.id, user.full_name, user.username, email=data)
        try:
            await context.bot.send_message(ADMIN_ID, f"🆕 <b>YANGI PRO USER!</b>\n👤 {user.full_name}\n🔗 @{user.username}\n🆔 <code>{user.id}</code>\n📧 {data}", parse_mode=ParseMode.HTML)
        except: pass
        
        final_url, _ = await generate_webapp_url(user, context.bot)
        kb = [[KeyboardButton(text="✨ Pro Versiya (Kirish)", web_app=WebAppInfo(url=final_url))]]
        await update.message.reply_text(f"✅ <b>Qabul qilindi!</b>\n📧 {data}\nBarcha imkoniyatlar ochildi.", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode=ParseMode.HTML)

# --- MEMBER JOIN/LEAVE (KUCHAYTIRILGAN) ---
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member: return
    
    new = update.chat_member.new_chat_member.status
    old = update.chat_member.old_chat_member.status
    user = update.chat_member.from_user
    email = get_user_email(user.id)
    
    # 1. KANALDAN CHIQSA (Left yoki Kicked)
    if new in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED] and old in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        try:
            # Userga ogohlantirish
            await context.bot.send_message(user.id, "🚨 <b>DIQQAT!</b>\n\nSiz majburiy kanaldan chiqib ketdingiz.\n<b>Pro litsenziyangiz va AI ruxsatingiz to'xtatildi!</b>\nQayta tiklash uchun /start ni bosing va a'zo bo'ling.", parse_mode=ParseMode.HTML)
        except: pass
        
        try:
            # Adminga xabar
            admin_msg = (
                f"❌ <b>KANALDAN CHIQDI (Litsenziya bekor qilinsin)!</b>\n\n"
                f"👤 <b>Ism:</b> {user.full_name}\n"
                f"🔗 <b>Link:</b> @{user.username}\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"📧 <b>Email:</b> {email}"
            )
            await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode=ParseMode.HTML)
        except: pass

    # 2. QAYTA QO'SHILSA (Join)
    elif new in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and old in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED]:
        try:
            # Adminga xabar
            join_msg = (
                f"✅ <b>FOYDALANUVCHI QAYTDI!</b>\n\n"
                f"👤 <b>Ism:</b> {user.full_name}\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"📧 <b>Email:</b> {email}\n"
                f"Status: <i>Litsenziyani qayta tiklash mumkin.</i>"
            )
            await context.bot.send_message(ADMIN_ID, join_msg, parse_mode=ParseMode.HTML)
        except: pass

# --- ADMIN COMMANDS ---
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = update.message.text.partition(' ')[2]
    parts = text.split('|')
    if len(parts) != 2: return await update.message.reply_text("Format: `/add_channel @user | Nomi`")
    add_channel_db(parts[0].strip(), parts[1].strip())
    await update.message.reply_text("✅ Kanal qo'shildi.")

async def del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    cid = update.message.text.partition(' ')[2].strip()
    del_channel_db(cid)
    await update.message.reply_text("🗑 O'chirildi.")

async def set_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    raw = update.message.text.partition(' ')[2]
    parts = raw.split('|')
    if len(parts) != 3: return await update.message.reply_text("Format: `/set_ad Title | Text | Link`")
    update_ad(parts[0].strip(), parts[1].strip(), parts[2].strip())
    await update.message.reply_text("✅ Reklama o'rnatildi.")

async def send_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply qiling.")
    users = get_all_users()
    await update.message.reply_text(f"🚀 Forward ketdi ({len(users)})...")
    for uid in users:
        try: await context.bot.forward_message(chat_id=uid, from_chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
        except: pass
    await update.message.reply_text("✅ Tugadi.")

async def send_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = update.message.text.partition(' ')[2]
    if not text: return await update.message.reply_text("Matn yozing.")
    users = get_all_users()
    await update.message.reply_text(f"🤖 Bot xabari ketdi ({len(users)})...")
    for uid in users:
        try: await context.bot.send_message(chat_id=uid, text=text)
        except: pass
    await update.message.reply_text("✅ Tugadi.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_channel", add_channel))
    app.add_handler(CommandHandler("del_channel", del_channel))
    app.add_handler(CommandHandler("set_ad", set_ad))
    app.add_handler(CommandHandler("send_forward", send_forward))
    app.add_handler(CommandHandler("send_bot", send_bot))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    print("Bot (Full Logic) ishga tushdi 🚀")
    app.run_polling()