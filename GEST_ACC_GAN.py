import sqlite3
import requests
import json
import io
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.error import Forbidden

# --- CONFIGURATION ---
# સુરક્ષા માટે: Render ના Environment Variables માં TOKEN ઉમેરવો હિતાવહ છે.
TOKEN = '8184247502:AAGsLkJUALJ4Q6KW5KG1OijuwUmTeHTrbh0' 
ADMIN_ID = 6328650912  
API_URL = "https://fffffffffffffffffffffffffffffffffff-rouge.vercel.app/gen"
CHANNELS = ["@KAMOD_CODEX", "@KAMOD_CODEX_BACKUP", "@KAMOD_LIKE_GROUP"]

# States for User
REGION, NAME, COUNT, REDEEM_INP = range(4)

# --- DATABASE SETUP ---
def get_db_connection():
    # Render પર SQLite ફાઈલ રાઈટ કરવા માટે check_same_thread=False જરૂરી છે
    conn = sqlite3.connect('kamod_bot.db', timeout=30, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL;') 
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 20, referred_by INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promo_codes 
                 (code TEXT PRIMARY KEY, value INTEGER, uses_left INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS redeemed_history 
                 (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 20))
        conn.commit()
        conn.close()
        return 20
    conn.close()
    return res[0]

def update_balance(user_id, amount):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users (balance) = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(balance) FROM users")
    res = c.fetchone()
    conn.close()
    return res[0], (res[1] or 0)

def get_all_users():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    res = c.fetchall()
    conn.close()
    return [r[0] for r in res]

# --- UTILITIES ---
async def is_subscribed(bot, user_id):
    if user_id == ADMIN_ID: return True
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

def get_join_markup():
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel 1", url="https://t.me/KAMOD_CODEX")],
        [InlineKeyboardButton("📢 Join Channel 2", url="https://t.me/KAMOD_CODEX_BACKUP")],
        [InlineKeyboardButton("📢 Join Channel 3", url="https://t.me/KAMOD_LIKE_GROUP")],
        [InlineKeyboardButton("✅ VERIFY", callback_data="verify_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_permanent_keyboard(user_id):
    keyboard = [
        ["🔥 GENERATE ACCOUNTS"],
        ["💰 BALANCE", "🎁 REDEEM"],
        ["👤 OWNER", "👥 REFER"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 ADMIN PANEL"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return 
    user = update.effective_user
    user_id = user.id
    init_db()

    # Referral system
    args = context.args
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone() is None:
        ref_id = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user_id else None
        if ref_id:
            conn.execute("UPDATE users SET balance = balance + 20 WHERE user_id = ?", (ref_id,))
            try: await context.bot.send_message(chat_id=ref_id, text="🎁 **Referral Bonus!** +20 Coins મળ્યા.")
            except: pass
        c.execute("INSERT INTO users (user_id, balance, referred_by) VALUES (?, ?, ?)", (user_id, 20, ref_id))
        conn.commit()
    conn.close()

    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text("❌ **Access Denied!** પહેલા અમારી ચેનલ જોઇન કરો.", reply_markup=get_join_markup())
        return

    welcome_text = f"👋 **Hello, {user.first_name}!**\n💰 Your Balance: `{get_user_data(user_id)}`"
    await update.message.reply_text(welcome_text, reply_markup=get_permanent_keyboard(user_id), parse_mode="Markdown")

async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    if await is_subscribed(context.bot, user_id):
        await query.message.delete()
        await context.bot.send_message(chat_id=user_id, text=f"✅ **Verified!**", reply_markup=get_permanent_keyboard(user_id))
    else:
        await query.answer("❌ હજી પણ તમે ચેનલ જોઇન નથી કરી!", show_alert=True)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "🔥 GENERATE ACCOUNTS":
        if get_user_data(user_id) <= 0:
            await update.message.reply_text("❌ Low Balance!")
            return ConversationHandler.END
        await update.message.reply_text("🌍 **Region કયું જોઈએ છે? (દા.ત. IND, BRA):**")
        return REGION
    elif text == "💰 BALANCE":
        await update.message.reply_text(f"💰 **Balance:** `{get_user_data(user_id)} Coins`")
    elif text == "🎁 REDEEM":
        await update.message.reply_text("🎁 **તમારો Redeem Code મોકલો:**")
        return REDEEM_INP
    elif text == "👤 OWNER":
        await update.message.reply_text("👤 **Owner:** TUFAN")
    elif text == "👥 REFER":
        bot_user = (await context.bot.get_me()).username
        await update.message.reply_text(f"🔗 **Refer Link:**\n`https://t.me/{bot_user}?start={user_id}`")
    elif text == "👑 ADMIN PANEL" and user_id == ADMIN_ID:
        await admin_panel(update, context)

# --- GENERATION LOGIC ---
async def fetch_acc(params):
    loop = asyncio.get_event_loop()
    try:
        r = await loop.run_in_executor(None, lambda: requests.get(API_URL, params=params, timeout=15))
        return r.json() if r.status_code == 200 else None
    except: return None

async def get_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['region'] = update.message.text
    await update.message.reply_text("👤 **નામ (Name) શું રાખવું છે?**")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("🔢 **કેટલા Accounts જોઈએ છે?**")
    return COUNT

async def get_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count_str = update.message.text
    if not count_str.isdigit(): return COUNT
    count = int(count_str)
    user_id = update.effective_user.id
    if count > get_user_data(user_id):
        await update.message.reply_text("❌ Low Balance!")
        return ConversationHandler.END

    msg = await update.message.reply_text(f"🚀 Generating... 0/{count}")
    final_accs = []
    for i in range(1, count + 1):
        res = await fetch_acc({'name': context.user_data['name'], 'count': 1, 'region': context.user_data['region']})
        if res: final_accs.append(res)
        if i % 2 == 0: await msg.edit_text(f"🚀 Generating: {i}/{count}...")
        await asyncio.sleep(1.5)

    conn = get_db_connection()
    conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (count, user_id))
    conn.commit()
    conn.close()

    f_io = io.BytesIO(json.dumps(final_accs, indent=4).encode())
    f_io.name = f"accounts_{user_id}.json"
    await update.message.reply_document(document=f_io, caption=f"✅ {len(final_accs)} Accounts Done!")
    return ConversationHandler.END

async def handle_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_txt = update.message.text.strip()
    user_id = update.effective_user.id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value, uses_left FROM promo_codes WHERE code = ?", (code_txt,))
    res = c.fetchone()
    if res and res[1] > 0:
        c.execute("SELECT 1 FROM redeemed_history WHERE user_id = ? AND code = ?", (user_id, code_txt))
        if c.fetchone():
            await update.message.reply_text("❌ Already used!")
        else:
            c.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code_txt,))
            c.execute("INSERT INTO redeemed_history VALUES (?, ?)", (user_id, code_txt))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (res[0], user_id))
            conn.commit()
            await update.message.reply_text(f"✅ Redeemed +{res[0]} Coins!")
    else:
        await update.message.reply_text("❌ Invalid code!")
    conn.close()
    return ConversationHandler.END

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📊 Stats", callback_data="admin_stats"), InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")]]
    await update.message.reply_text("👑 **ADMIN DASHBOARD**", reply_markup=InlineKeyboardMarkup(kb))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "admin_stats":
        u, b = get_stats()
        await query.answer(f"Users: {u} | Total Coins: {b}", show_alert=True)
    elif query.data == "admin_broadcast":
        await query.message.reply_text("Use: `/broadcast text`")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = " ".join(context.args)
    users = get_all_users()
    for u in users:
        try: await context.bot.send_message(chat_id=u, text=f"📢 **BROADCAST**\n\n{msg}")
        except: pass
    await update.message.reply_text("✅ Done!")

# --- MAIN ---
def main():
    init_db()
    # job_queue(None) એ Render પર થ્રેડિંગની એરર રોકે છે
    app = Application.builder().token(TOKEN).job_queue(None).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(🔥 GENERATE ACCOUNTS|🎁 REDEEM)$'), handle_buttons)],
        states={
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_region)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_count)],
            REDEEM_INP: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_redeem)],
        },
        fallbacks=[CommandHandler('start', start)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(verify_join, pattern="verify_join"))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("Bot is starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()