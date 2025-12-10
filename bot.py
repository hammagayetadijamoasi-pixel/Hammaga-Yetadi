import logging
import time
import json
import urllib.parse
import os
import threading
import psycopg2 # PostgreSQL kutubxonasi
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    filters
)

# --- RENDER WEB SERVER ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running with PostgreSQL!')

def start_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"🌍 Web server {port}-portda ishga tushdi...")
    server.serve_forever()

# --- SOZLAMALAR ---
TOKEN = "8523951175:AAEw7Mfv7Y-LT3VN7GWunSkZsTmgurfl_gE"
ADMIN_ID = 6787735720
WEBAPP_URL = "https://hammagayetadijamoasi-pixel.github.io/Hammaga-Yetadi"
# Render avtomatik beradigan Baza Manzili
DB_URL = os.environ.get("DATABASE_URL")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BAZA (POSTGRESQL) ---
def get_db_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Jadvallarni yaratish (Postgres sintaksisida)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            email TEXT,
            joined_at BIGINT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ads (
            id SERIAL PRIMARY KEY,
            title TEXT,
            text TEXT,
            link TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            type TEXT,
            file_id TEXT,
            caption TEXT
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

# --- DB FUNKSIYALARI ---
def add_or_update_user(user_id, full_name, username, email=None):
    conn = get_db_connection()
    cur = conn.cursor()
    # UPSERT (Agar bor bo'lsa yangilash, yo'q bo'lsa qo'shish)
    if email:
        cur.execute("""
            INSERT INTO users (user_id, full_name, username, email, joined_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE 
            SET full_name = EXCLUDED.full_name, 
                username = EXCLUDED.username, 
                email = EXCLUDED.email;
        """, (user_id, full_name, username, email, int(time.time())))
    else:
        cur.execute("""
            INSERT INTO users (user_id, full_name, username, joined_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE 
            SET full_name = EXCLUDED.full_name, 
                username = EXCLUDED.username;
        """, (user_id, full_name, username, int(time.time())))
    conn.commit()
    cur.close()
    conn.close()

def get_user_email(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT email FROM users WHERE user_id = %s", (user_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res and res[0] else "0"

def get_all_users():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return users

# --- KANALLAR ---
def add_channel_db(cid, cname):
    conn = get_db_connection()
    cur = conn.cursor()
    clean_id = cid.replace('https://t.me/', '@')
    if not clean_id.startswith('@') and not clean_id.startswith('-100'): clean_id = '@' + clean_id
    
    cur.execute("""
        INSERT INTO channels (channel_id, channel_name) VALUES (%s, %s)
        ON CONFLICT (channel_id) DO NOTHING
    """, (clean_id, cname))
    conn.commit()
    cur.close()
    conn.close()

def del_channel_db(cid):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE channel_id = %s", (cid,))
    conn.commit()
    cur.close()
    conn.close()

def get_channels_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT channel_id, channel_name FROM channels")
    res = [{"id": r[0], "name": r[1], "url": f"https://t.me/{r[0].replace('@','')}"} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return res

# --- LINK & RESOURCE ---
def set_canva_link_db(link):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, ("canva_link", link))
    conn.commit()
    cur.close()
    conn.close()

def get_canva_link_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='canva_link'")
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else ""

def add_resource_db(name, r_type, file_id, caption):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO resources (name, type, file_id, caption) VALUES (%s, %s, %s, %s)", (name, r_type, file_id, caption))
        conn.commit()
        return True
    except: return False
    finally:
        cur.close()
        conn.close()

def get_resources_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM resources")
    res = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return res

def get_resource_by_id(r_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT type, file_id, caption FROM resources WHERE id = %s", (r_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res

# --- REKLAMA ---
def update_ad(t, x, l):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM ads") # Eskisini tozalash
    cur.execute("INSERT INTO ads (title, text, link) VALUES (%s, %s, %s)", (t, x, l))
    conn.commit()
    cur.close()
    conn.close()

def get_current_ad():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT title, text, link FROM ads LIMIT 1")
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res

# --- MANTIQ (YORDAMCHI) ---
async def check_user_subscription(user_id, bot):
    channels = get_channels_db()
    if not channels: return True, []

    not_joined = []
    status_list = []

    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                status_list.append({"name": ch["name"], "url": ch["url"], "joined": True})
            else:
                not_joined.append(ch)
                status_list.append({"name": ch["name"], "url": ch["url"], "joined": False})
        except:
            not_joined.append(ch)
            status_list.append({"name": ch["name"], "url": ch["url"], "joined": False})
            
    return len(not_joined) == 0, status_list

async def generate_channel_keyboard(status_list):
    keyboard = []
    for item in status_list:
        icon = "✅" if item["joined"] else "❌"
        keyboard.append([InlineKeyboardButton(f"{icon} {item['name']}", url=item['url'])])
    keyboard.append([InlineKeyboardButton("🔄 Tekshirish", callback_data="check_subs")])
    return InlineKeyboardMarkup(keyboard)

async def generate_webapp_url(user, bot):
    email_status = "1" if get_user_email(user.id) != "0" else "0"
    timestamp = int(time.time())
    user_name = urllib.parse.quote(user.first_name)
    
    channels_json = urllib.parse.quote(json.dumps(get_channels_db()))
    resources_json = urllib.parse.quote(json.dumps(get_resources_db()))
    canva_link = urllib.parse.quote(get_canva_link_db())
    
    base_url = f"{WEBAPP_URL}/index.html?s=11&e={email_status}&n={user_name}&id={user.id}&v={timestamp}&ch={channels_json}&rs={resources_json}&cl={canva_link}"
    
    ad = get_current_ad()
    if ad:
        base_url += f"&at={urllib.parse.quote(ad[0])}&ax={urllib.parse.quote(ad[1])}&al={urllib.parse.quote(ad[2])}"
    return base_url

# --- 1. START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_or_update_user(user.id, user.full_name, user.username)
    
    terms_text = (
        f"👋 <b>Assalomu alaykum, {user.first_name}!</b>\n"
        f"<b>Yaxshi AI & Pro</b> botiga xush kelibsiz.\n\n"
        "⚠️ <b>FOYDALANISH SHARTLARI:</b>\n\n"
        "1️⃣ <b>Homiy Kanallar:</b> Bot bepul ishlashi uchun a'zo bo'lishingiz shart.\n\n"
        "2️⃣ <b>Link Kafolati:</b> 100% kafolat yo'q, lekin biz harakat qilamiz.\n\n"
        "3️⃣ <b>Email Siyosati:</b> Agar kanaldan chiqsangiz, Emailingiz aniqlanadi va Pro dan o'chiriladi.\n\n"
        "👇 <i>Davom etish uchun rozilik bildiring:</i>"
    )
    
    keyboard = [[InlineKeyboardButton("✅ Tanishdim va Roziman", callback_data="accept_terms")]]
    
    await update.message.reply_text(text=terms_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

# --- 2. CALLBACK ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    if query.data == "accept_terms":
        await query.delete_message()
        is_joined, status_list = await check_user_subscription(user.id, context.bot)
        keyboard = await generate_channel_keyboard(status_list)
        await query.message.reply_text("📢 <b>Kanallarga a'zo bo'ling:</b>", reply_markup=keyboard, parse_mode=ParseMode.HTML)

    elif query.data == "check_subs":
        is_joined, status_list = await check_user_subscription(user.id, context.bot)
        if is_joined:
            await query.delete_message()
            has_email = get_user_email(user.id) != "0"
            btn_text = "✨ Kirish" if has_email else "📧 Email yuborish va Kirish"
            final_url = await generate_webapp_url(user, context.bot)
            kb = [[KeyboardButton(text=btn_text, web_app=WebAppInfo(url=final_url))]]
            await query.message.reply_text("✅ <b>Tabriklaymiz!</b> Pastdagi tugmani bosing 👇", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode=ParseMode.HTML)
        else:
            new_keyboard = await generate_channel_keyboard(status_list)
            try:
                await query.edit_message_reply_markup(reply_markup=new_keyboard)
                await query.answer("❌ Hali hammasiga a'zo emassiz!", show_alert=True)
            except: pass

# --- 3. POLITSIYA (AUTO-BAN) ---
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member: return
    new_status = update.chat_member.new_chat_member.status
    old_status = update.chat_member.old_chat_member.status
    user = update.chat_member.from_user
    
    # Kanaldan chiqsa
    if new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED] and old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        email = get_user_email(user.id)
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=(f"🚨 <b>DIQQAT!</b>\nSiz kanaldan chiqdingiz.\n📧 <b>Email:</b> {email}\n⛔️ <b>Pro litsenziyangiz bekor qilinmoqda.</b>"),
                parse_mode=ParseMode.HTML,
                reply_markup=json.dumps({'remove_keyboard': True})
            )
        except: pass
        try:
            await context.bot.send_message(ADMIN_ID, f"❌ <b>QOIDABUZAR!</b>\n👤 {user.full_name}\n📧 {email}\n⚠️ <i>O'chirib tashlang.</i>", parse_mode=ParseMode.HTML)
        except: pass

# --- ADMIN COMMANDS ---
async def save_kb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply qiling.")
    name = update.message.text.partition(' ')[2].strip()
    msg = update.message.reply_to_message
    r_type, file_id, caption = "text", msg.text or "", msg.caption or ""
    if msg.photo: r_type, file_id = "photo", msg.photo[-1].file_id
    elif msg.video: r_type, file_id = "video", msg.video.file_id
    elif msg.document: r_type, file_id = "document", msg.document.file_id
    if add_resource_db(name, r_type, file_id, caption): await update.message.reply_text(f"✅ {name} saqlandi.")
    else: await update.message.reply_text("❌ Xatolik.")

async def del_kb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = get_db_connection(); conn.cursor().execute("DELETE FROM resources WHERE name=%s", (update.message.text.partition(' ')[2].strip(),)); conn.commit(); conn.close()
    await update.message.reply_text("🗑 O'chirildi.")

async def set_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    set_canva_link_db(update.message.text.partition(' ')[2].strip())
    await update.message.reply_text("✅ Link yangilandi.")

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    parts = update.message.text.partition(' ')[2].split('|')
    if len(parts) != 2: return await update.message.reply_text("Xato format")
    add_channel_db(parts[0].strip(), parts[1].strip())
    await update.message.reply_text("✅ Qo'shildi.")

async def del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    del_channel_db(update.message.text.partition(' ')[2].strip())
    await update.message.reply_text("🗑 O'chirildi.")

async def set_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    raw = update.message.text.partition(' ')[2].split('|')
    if len(raw) != 3: return
    update_ad(raw[0].strip(), raw[1].strip(), raw[2].strip())
    await update.message.reply_text("✅ Reklama OK.")

async def send_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = update.message.text.partition(' ')[2]
    users = get_all_users()
    await update.message.reply_text(f"Bot yubormoqda ({len(users)})...")
    for u in users:
        try: await context.bot.send_message(u, text)
        except: pass
    await update.message.reply_text("Tugadi.")

async def send_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not update.message.reply_to_message: return
    users = get_all_users()
    await update.message.reply_text(f"Forward ({len(users)})...")
    for u in users:
        try: await context.bot.forward_message(u, update.effective_chat.id, update.message.reply_to_message.message_id)
        except: pass
    await update.message.reply_text("Tugadi.")

# --- WEB APP ---
async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    user = update.effective_user
    
    if data.startswith("get_resource:"):
        res = get_resource_by_id(data.split(":")[1])
        if res:
            try:
                if res[0]=="text": await update.message.reply_text(res[1], parse_mode=ParseMode.HTML)
                elif res[0]=="photo": await update.message.reply_photo(res[1], caption=res[2])
                elif res[0]=="video": await update.message.reply_video(res[1], caption=res[2])
                elif res[0]=="document": await update.message.reply_document(res[1], caption=res[2])
            except: await update.message.reply_text("Xatolik.")
            
    elif "@" in data:
        add_or_update_user(user.id, user.full_name, user.username, email=data)
        try: await context.bot.send_message(ADMIN_ID, f"🆕 PRO: {data}")
        except: pass
        final_url = await generate_webapp_url(user, context.bot)
        kb = [[KeyboardButton(text="✨ Yaxshi AI va Pro (Kirish)", web_app=WebAppInfo(url=final_url))]]
        await update.message.reply_text("✅ Email qabul qilindi!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

if __name__ == "__main__":
    # Avval BAZA yaratamiz
    try: init_db()
    except Exception as e: print(f"Baza xatosi: {e}")

    # Serverni ishga tushirish (Render uchun)
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CommandHandler("save_kb", save_kb))
    app.add_handler(CommandHandler("del_kb", del_kb))
    app.add_handler(CommandHandler("set_link", set_link))
    app.add_handler(CommandHandler("add_channel", add_channel))
    app.add_handler(CommandHandler("del_channel", del_channel))
    app.add_handler(CommandHandler("set_ad", set_ad))
    app.add_handler(CommandHandler("send_bot", send_bot))
    app.add_handler(CommandHandler("send_forward", send_forward))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    
    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)