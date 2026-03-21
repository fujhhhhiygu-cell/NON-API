import sqlite3
import requests
import json
import io
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.error import Forbidden

# --- CONFIGURATION ---
TOKEN = '8184247502:AAGsLkJUALJ4Q6KW5KG1OijuwUmTeHTrbh0' # ⚠️ ચેતવણી: આ ટોકન કોઈને બતાવવો નહીં
ADMIN_ID = 6328650912  # તમારો Telegram ID
API_URL = "https://fffffffffffffffffffffffffffffffffff-rouge.vercel.app/gen"
CHANNELS =["@KAMOD_CODEX", "@KAMOD_CODEX_BACKUP", "@KAMOD_LIKE_GROUP"]

# States for User
REGION, NAME, COUNT, REDEEM_INP = range(4)

# --- DATABASE SETUP ---
def get_db_connection():
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
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# એડમિન માટે ડેટાબેઝ ફંક્શન
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

# --- FORCE JOIN UTILITY ---
async def is_subscribed(bot, user_id):
    if user_id == ADMIN_ID: return True
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

def get_join_markup():
    keyboard = [[InlineKeyboardButton("📢 Join Channel 1", url="https://t.me/KAMOD_CODEX")],[InlineKeyboardButton("📢 Join Channel 2", url="https://t.me/KAMOD_CODEX_BACKUP")],[InlineKeyboardButton("📢 Join Channel 3", url="https://t.me/KAMOD_LIKE_GROUP")],
        [InlineKeyboardButton("✅ VERIFY", callback_data="verify_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

# 🛑 અહી મેં એડમિન માટે અલગ કીબોર્ડ લોજીક ઉમેર્યું છે 🛑
def get_permanent_keyboard(user_id):
    keyboard =[
        ["🔥 GENERATE ACCOUNTS"],
        ["💰 BALANCE", "🎁 REDEEM"],["👤 OWNER", "👥 REFER"]
    ]
    # જો user_id એડમિનનો હોય, તો જ એડમિન પેનલનું બટન દેખાશે!
    if user_id == ADMIN_ID:
        keyboard.append(["👑 ADMIN PANEL"])
        
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- CORE HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return 
    
    user = update.effective_user
    user_id = user.id
    init_db()

    args = context.args
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone() is None:
        ref_id = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user_id else None
        if ref_id:
            update_balance(ref_id, 20)
            try: await context.bot.send_message(chat_id=ref_id, text="🎁 **Referral Bonus!** +20 Coins મળ્યા.")
            except: pass
        c.execute("INSERT INTO users (user_id, balance, referred_by) VALUES (?, ?, ?)", (user_id, 20, ref_id))
        conn.commit()
    conn.close()

    if not await is_subscribed(context.bot, user_id):
        try:
            await update.message.reply_text("❌ **Access Denied!** પહેલા અમારી ચેનલ જોઇન કરો.", reply_markup=get_join_markup())
        except Forbidden: pass
        return

    welcome_text = f"👋 **Hello, {user.first_name}!**\n💰 Your Balance: `{get_user_data(user_id)}`"
    try:
        photos = await user.get_profile_photos()
        if photos.total_count > 0:
            await update.message.reply_photo(photo=photos.photos[0][0].file_id, caption=welcome_text, reply_markup=get_permanent_keyboard(user_id), parse_mode="Markdown")
        else:
            await update.message.reply_text(welcome_text, reply_markup=get_permanent_keyboard(user_id), parse_mode="Markdown")
    except:
        try: await update.message.reply_text(welcome_text, reply_markup=get_permanent_keyboard(user_id), parse_mode="Markdown")
        except: pass

async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    if await is_subscribed(context.bot, user_id):
        try:
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text=f"✅ **Verified!**\n💰 Balance: `{get_user_data(user_id)}`", reply_markup=get_permanent_keyboard(user_id))
        except: pass
    else:
        await query.answer("❌ હજી પણ તમે ચેનલ જોઇન નથી કરી!", show_alert=True)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return 
        
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "🔥 GENERATE ACCOUNTS":
        if get_user_data(user_id) <= 0:
            await update.message.reply_text("❌ Low Balance (તમારી પાસે પૂરતા સિક્કા નથી)!")
            return ConversationHandler.END
        await update.message.reply_text("🌍 **Region કયું જોઈએ છે? (દા.ત. IND, BRA, ID):**")
        return REGION
        
    elif text == "💰 BALANCE":
        await update.message.reply_text(f"💰 **Balance:** `{get_user_data(user_id)} Coins`")
        
    elif text == "🎁 REDEEM":
        await update.message.reply_text("🎁 **તમારો Redeem Code નીચે લખીને મોકલો:**")
        return REDEEM_INP
        
    elif text == "👤 OWNER":
        await update.message.reply_text("👤 **Owner:** TUFAN")
        
    elif text == "👥 REFER":
        bot_user = (await context.bot.get_me()).username
        await update.message.reply_text(f"🔗 **Refer Link:**\n`https://t.me/{bot_user}?start={user_id}`\n\nદરેક રેફર પર **20 Coins** મળશે!")
        
    # 🛑 એડમિન બટન પર ક્લિક થતાં આ કોડ રન થશે 🛑
    elif text == "👑 ADMIN PANEL":
        if user_id == ADMIN_ID:
            await admin_panel(update, context)
        else:
            await update.message.reply_text("❌ તમે એડમિન નથી!")

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
    await update.message.reply_text("🔢 **કેટલા Accounts જોઈએ છે?**\n💳 **Cost:** `1 Coin = 1 Account`")
    return COUNT

async def get_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count_str = update.message.text
        if not count_str.isdigit():
            await update.message.reply_text("❌ કૃપા કરીને ફક્ત નંબર (આંકડા) લખો!")
            return COUNT

        count = int(count_str)
        user_id = update.effective_user.id
        balance = get_user_data(user_id)

        if count <= 0:
            await update.message.reply_text("❌ સાચો નંબર લખો!")
            return COUNT

        if count > balance:
            await update.message.reply_text("❌ Low Balance! તમારી પાસે પૂરતા Coins નથી.")
            return ConversationHandler.END

        msg = await update.message.reply_text(f"🚀 શરૂ થઈ ગયું છે... 0/{count}")
        params = {'name': context.user_data['name'], 'count': 1, 'region': context.user_data['region']}
        final_accs =[]

        for i in range(1, count + 1):
            res = await fetch_acc(params)
            if res: final_accs.append(res)
            try: await msg.edit_text(f"🚀 Generating: {i}/{count} Accounts...")
            except: pass
            if i < count: await asyncio.sleep(2)

        update_balance(user_id, -count)

        f_io = io.BytesIO(json.dumps(final_accs, indent=4).encode())
        f_io.name = f"accounts_{user_id}.json"

        try: await msg.delete()
        except: pass

        await update.message.reply_document(document=f_io, caption=f"✅ સફળતાપૂર્વક! {len(final_accs)} Accounts બની ગયા છે.")
        return ConversationHandler.END

    except Exception as e:
        print(f"Error: {e}")
        return ConversationHandler.END

async def handle_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return ConversationHandler.END
    code_txt = update.message.text.strip()
    user_id = update.effective_user.id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM redeemed_history WHERE user_id = ? AND code = ?", (user_id, code_txt))
    if c.fetchone():
        await update.message.reply_text("❌ **તમે આ કોડ પહેલેથી જ વાપરી લીધો છે!**")
        conn.close()
        return ConversationHandler.END

    c.execute("SELECT value, uses_left FROM promo_codes WHERE code = ?", (code_txt,))
    res = c.fetchone()
    if res and res[1] > 0:
        val = res[0]
        c.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code_txt,))
        c.execute("INSERT INTO redeemed_history VALUES (?, ?)", (user_id, code_txt))
        conn.commit()
        update_balance(user_id, val)
        await update.message.reply_text(f"✅ **Redeemed!** તમારા ખાતામાં +{val} Coins ઉમેરવામાં આવ્યા છે.")
    else:
        await update.message.reply_text("❌ કોડ ખોટો છે અથવા તેની લિમિટ પૂરી થઈ ગઈ છે!")
    conn.close()
    return ConversationHandler.END


# ==========================================
# 👑 ADMIN PANEL & COMMANDS 
# ==========================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    keyboard = [[InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"), InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],[InlineKeyboardButton("💰 Add/Rem Balance", callback_data="admin_balance"), InlineKeyboardButton("🎟️ Create Promo", callback_data="admin_promo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 **ADMIN DASHBOARD**\nશું કરવું છે તે પસંદ કરો:", reply_markup=reply_markup, parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ તમે એડમિન નથી!", show_alert=True)
        return
        
    data = query.data
    await query.answer()
    
    if data == "admin_stats":
        users, bal = get_stats()
        text = f"📊 **BOT STATISTICS**\n\n👥 **કુલ યુઝર્સ (Users):** {users}\n💰 **કુલ કોઈન્સ (Coins):** {bal}"
        await query.edit_message_text(text, reply_markup=query.message.reply_markup, parse_mode="Markdown")
        
    elif data == "admin_broadcast":
        text = "📢 **બ્રોડકાસ્ટ (બધાને મેસેજ) કરવા માટે આ કમાન્ડ વાપરો:**\n\n`/broadcast તમારો મેસેજ અહીં લખો`\n\nદા.ત.: `/broadcast Hello Everyone! નવા કોડ આવી ગયા છે.`"
        await query.message.reply_text(text, parse_mode="Markdown")
        
    elif data == "admin_balance":
        text = "💰 **યુઝરનું બેલેન્સ વધારવા કે ઘટાડવા માટે કમાન્ડ વાપરો:**\n\n➕ **ઉમેરવા માટે:** `/addbal <User_ID> <Amount>`\n➖ **કાઢવા માટે:** `/rembal <User_ID> <Amount>`\n\nદા.ત.: `/addbal 123456789 100`"
        await query.message.reply_text(text, parse_mode="Markdown")
        
    elif data == "admin_promo":
        text = "🎟️ **પ્રોમો કોડ (Promo Code) બનાવવા માટે કમાન્ડ વાપરો:**\n\n`/redeem <CODE> <VALUE> <LIMIT>`\n\nદા.ત.: `/redeem FREE50 50 100` (આ FREE50 કોડ 100 લોકો વાપરી શકશે અને 50 કોઈન્સ મળશે)"
        await query.message.reply_text(text, parse_mode="Markdown")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("⚠️ કૃપા કરીને મેસેજ લખો! દા.ત. `/broadcast હેલો ભાઈઓ`")
        return
        
    users = get_all_users()
    success = 0
    await update.message.reply_text("⏳ Broadcast ચાલુ છે, મહેરબાની કરીને રાહ જુઓ...")
    
    for u in users:
        try:
            await context.bot.send_message(chat_id=u, text=f"📢 **BROADCAST**\n\n{msg}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05) 
        except: pass
        
    await update.message.reply_text(f"✅ બ્રોડકાસ્ટ પૂર્ણ! {success}/{len(users)} યુઝર્સને મેસેજ પહોંચી ગયો.")

async def add_bal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid, amt = int(context.args[0]), int(context.args[1])
        update_balance(uid, amt)
        await update.message.reply_text(f"✅ User `{uid}` ના ખાતામાં {amt} Coins ઉમેરાયા.", parse_mode="Markdown")
        try: await context.bot.send_message(chat_id=uid, text=f"🎁 એડમિન દ્વારા તમારા ખાતામાં **{amt} Coins** ઉમેરવામાં આવ્યા છે!", parse_mode="Markdown")
        except: pass
    except: await update.message.reply_text("⚠️ સાચો ઉપયોગ: `/addbal <User_ID> <Amount>`")

async def rem_bal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid, amt = int(context.args[0]), int(context.args[1])
        update_balance(uid, -amt)
        await update.message.reply_text(f"✅ User `{uid}` ના ખાતામાંથી {amt} Coins કાપી લેવાયા છે.", parse_mode="Markdown")
    except: await update.message.reply_text("⚠️ સાચો ઉપયોગ: `/rembal <User_ID> <Amount>`")

async def admin_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        code, val, uses = context.args[0], int(context.args[1]), int(context.args[2])
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO promo_codes VALUES (?, ?, ?)", (code, val, uses))
        conn.commit()
        conn.close()
        
        poster = (
            "╔══════════════════════╗\n"
            "🚀  𝗡𝗘𝗪 𝗣𝗥𝗢𝗠𝗢 𝗖𝗢𝗗𝗘 𝗔𝗟𝗘𝗥𝗧  🚀\n"
            "╚══════════════════════╝\n\n"
            f"🎟️ 𝗖𝗢𝗗𝗘 ➤  `{code}`\n"
            f"💎 𝗩𝗔𝗟𝗨𝗘 ➤  {val} 𝗖𝗢𝗜𝗡𝗦\n"
            f"👥 𝗟𝗜𝗠𝗜𝗧 ➤  {uses} 𝗨𝗦𝗘𝗥𝗦\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ 𝗙𝗔𝗦𝗧 𝗥𝗘𝗗𝗘𝗘𝗠 𝗡𝗢𝗪!\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 TUFAN OFFICIAL", url="https://t.me/tufan95aura")],[InlineKeyboardButton("🤖 BOT LINK", url=f"https://t.me/FFGESTGANRETARbot?start={ADMIN_ID}")]])
        await update.message.reply_text(poster, reply_markup=kb, parse_mode="Markdown")
    except Exception: 
        await update.message.reply_text("⚠️ સાચો ઉપયોગ: `/redeem CODE VALUE LIMIT`\nદા.ત.: `/redeem FREECOIN 50 100`")

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(🔥 GENERATE ACCOUNTS|🎁 REDEEM)$'), handle_buttons)],
        states={
            REGION:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_region)],
            NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            COUNT:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_count)],
            REDEEM_INP:[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_redeem)],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True 
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel)) 
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_")) 
    app.add_handler(CallbackQueryHandler(verify_join, pattern="verify_join"))
    
    app.add_handler(CommandHandler("broadcast", broadcast_cmd)) 
    app.add_handler(CommandHandler("addbal", add_bal_cmd)) 
    app.add_handler(CommandHandler("rembal", rem_bal_cmd)) 
    app.add_handler(CommandHandler("redeem", admin_redeem))
    
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    app.add_error_handler(global_error_handler)
    
    print("Bot is LIVE (Admin Keyboard Added)...")
    app.run_polling()

if __name__ == '__main__':
    main()