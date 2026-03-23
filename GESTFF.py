import sqlite3
import json
import io
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURATION (તમારી વિગતો અહીં ભરો) ---
TOKEN = '8184247502:AAGsLkJUALJ4Q6KW5KG1OijuwUmTeHTrbh0'
ADMIN_ID = 6328650912 
API_URL = "https://ffgestapisrc.vercel.app/gen"
CHANNELS = ["@KAMOD_CODEX", "@KAMOD_CODEX_BACKUP", "@tufan95aura"] # ચેનલ એડમિન હોવી જોઈએ

# Conversation States
(GEN_REGION, GEN_NAME, GEN_COUNT, REDEEM_INP, 
 AD_BAL_ID, AD_BAL_AMT, 
 AD_CODE_NAME, AD_CODE_VAL, AD_CODE_LIM, 
 AD_BROADCAST) = range(10)

# --- DATABASE SETUP (Thread-Safe) ---
def init_db():
    conn = sqlite3.connect('kamod_bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('PRAGMA journal_mode=WAL;') # Multi-user માટે જરૂરી
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 20, ref_by INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, value INTEGER, uses_left INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS redeemed (user_id INTEGER, code TEXT, PRIMARY KEY(user_id, code))')
    conn.commit()
    conn.close()

def db_query(query, params=(), fetchone=False, fetchall=False):
    conn = sqlite3.connect('kamod_bot.db')
    c = conn.cursor()
    c.execute(query, params)
    res = None
    if fetchone: res = c.fetchone()
    elif fetchall: res = c.fetchall()
    conn.commit()
    conn.close()
    return res

# --- UTILITY FUNCTIONS ---
async def is_subscribed(bot, user_id):
    if user_id == ADMIN_ID: return True
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status in ['left', 'kicked']: return False
        except: return False
    return True

def get_main_kb(uid):
    kb = [["🔥 GENERATE ACCOUNTS"], ["💰 BALANCE", "🎁 REDEEM"], ["👤 OWNER", "👥 REFER"]]
    if uid == ADMIN_ID: kb.append(["🛠 ADMIN PANEL"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_kb():
    return ReplyKeyboardMarkup([
        ["🎟 Generate Promo", "💰 Add Balance"],
        ["📊 Stats", "📢 Broadcast"],
        ["🔙 Back to Menu"]
    ], resize_keyboard=True)

# --- START & FORCE JOIN ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_db()
    
    # Referral Logic
    args = context.args
    ref_id = int(args[0]) if args and args[0].isdigit() and int(args[0]) != uid else None
    
    if not db_query("SELECT user_id FROM users WHERE user_id=?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, balance, ref_by) VALUES (?, 20, ?)", (uid, 20, ref_id))
        if ref_id:
            db_query("UPDATE users SET balance = balance + 20 WHERE user_id=?", (ref_id,))
            try: await context.bot.send_message(ref_id, "🎁 તમારા રેફરલ લિંકથી કોઈ જોડાયું! +20 Coins મળ્યા.")
            except: pass

    if not await is_subscribed(context.bot, uid):
        btns = [[InlineKeyboardButton(f"Join {c}", url=f"https://t.me/{c[1:]}")] for c in CHANNELS]
        btns.append([InlineKeyboardButton("✅ Verify", callback_data="verify")])
        await update.message.reply_text("❌ બોટ વાપરવા માટે ચેનલ જોઈન કરો!", reply_markup=InlineKeyboardMarkup(btns))
        return
    
    await update.message.reply_text(f"👋 નમસ્તે {update.effective_user.first_name}!\nતમારી પાસે `{db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)[0]}` Coins છે.", reply_markup=get_main_kb(uid))

async def verify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if await is_subscribed(context.bot, uid):
        await q.answer("✅ સફળ!")
        await q.message.delete()
        await context.bot.send_message(uid, "વેલકમ! હવે તમે બોટ વાપરી શકો છો.", reply_markup=get_main_kb(uid))
    else:
        await q.answer("❌ હજુ બધી ચેનલ જોઈન નથી કરી!", show_alert=True)

# --- ACCOUNT GENERATION (ASYNCHRONOUS) ---
async def gen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_subscribed(context.bot, uid): return
    bal = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)[0]
    if bal < 1:
        await update.message.reply_text("❌ તમારી પાસે કોઈન્સ નથી!")
        return ConversationHandler.END
    await update.message.reply_text("🌍 કયો દેશ? (દા.ત. IND, BRA, ID):")
    return GEN_REGION

async def gen_get_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['g_region'] = update.message.text
    await update.message.reply_text("👤 એકાઉન્ટ માટે નામ લખો:")
    return GEN_NAME

async def gen_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['g_name'] = update.message.text
    await update.message.reply_text("🔢 કેટલા એકાઉન્ટ્સ જોઈએ છે? (નંબરમાં લખો):")
    return GEN_COUNT

async def gen_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        count_text = update.message.text
        if not count_text.isdigit():
            await update.message.reply_text("❌ ફક્ત આંકડા લખો!")
            return GEN_COUNT
        
        count = int(count_text)
        bal = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)[0]
        
        if count > bal or count <= 0:
            await update.message.reply_text(f"❌ ખોટી સંખ્યા અથવા ઓછું બેલેન્સ (તમારું બેલેન્સ: {bal})")
            return ConversationHandler.END

        msg = await update.message.reply_text(f"⏳ જનરેટ થઈ રહ્યું છે: 0/{count}...")
        results = []
        
        async with httpx.AsyncClient() as client:
            for i in range(count):
                try:
                    res = await client.get(API_URL, params={'name': context.user_data['g_name'], 'region': context.user_data['g_region']}, timeout=25)
                    if res.status_code == 200:
                        results.append(res.json())
                except: pass
                await msg.edit_text(f"⏳ પ્રગતિ: {len(results)}/{count}...")
                await asyncio.sleep(0.4)

        if not results:
            await msg.edit_text("❌ સર્વર ડાઉન છે અથવા API માં ભૂલ છે. ફરી પ્રયાસ કરો.")
            return ConversationHandler.END

        db_query("UPDATE users SET balance = balance - ? WHERE user_id=?", (len(results), uid))
        file_io = io.BytesIO(json.dumps(results, indent=4).encode())
        file_io.name = f"accounts_{uid}.json"
        await update.message.reply_document(document=file_io, caption=f"✅ સફળ! {len(results)} એકાઉન્ટ્સ મોકલ્યા છે.")
        await msg.delete()
    except Exception as e:
        await update.message.reply_text("❌ કાંઈક ભૂલ થઈ છે. ફરીથી ટ્રાય કરો.")
    return ConversationHandler.END

# --- REDEEM PROMO CODE ---
async def redeem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 પ્રોમો કોડ લખો:")
    return REDEEM_INP

async def redeem_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text
    uid = update.effective_user.id
    if db_query("SELECT 1 FROM redeemed WHERE user_id=? AND code=?", (uid, code), fetchone=True):
        await update.message.reply_text("❌ તમે આ કોડ વાપરી લીધો છે!")
    else:
        res = db_query("SELECT value, uses_left FROM promo_codes WHERE code=?", (code,), fetchone=True)
        if res and res[1] > 0:
            db_query("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code=?", (code,))
            db_query("INSERT INTO redeemed VALUES (?, ?)", (uid, code))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (res[0], uid))
            await update.message.reply_text(f"✅ સફળ! +{res[0]} કોઈન્સ મળ્યા.")
        else: await update.message.reply_text("❌ કોડ ખોટો છે અથવા લિમિટ પૂરી થઈ ગઈ છે.")
    return ConversationHandler.END

# --- ADMIN PANEL FUNCTIONS ---
async def ad_promo_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎟 પ્રોમો કોડનું નામ શું રાખવું છે?")
    return AD_CODE_NAME

async def ad_promo_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_pname'] = update.message.text
    await update.message.reply_text("💎 આ કોડની કિંમત (Coins) કેટલી રાખવી છે?")
    return AD_CODE_VAL

async def ad_promo_3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_pval'] = update.message.text
    await update.message.reply_text("👥 કેટલા યુઝર્સ આ વાપરી શકશે? (Limit)")
    return AD_CODE_LIM

async def ad_promo_4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        db_query("INSERT OR REPLACE INTO promo_codes VALUES (?, ?, ?)", (context.user_data['temp_pname'], int(context.user_data['temp_pval']), int(update.message.text)))
        await update.message.reply_text("✅ પ્રોમો કોડ સેવ થઈ ગયો!", reply_markup=get_admin_kb())
    except: await update.message.reply_text("❌ ભૂલ થઈ!")
    return ConversationHandler.END

async def ad_bal_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👤 યુઝરની Telegram ID લખો:")
    return AD_BAL_ID

async def ad_bal_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_uid'] = update.message.text
    await update.message.reply_text("💰 કેટલા કોઈન્સ ઉમેરવા છે?")
    return AD_BAL_AMT

async def ad_bal_3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (int(update.message.text), int(context.user_data['temp_uid'])))
        await update.message.reply_text("✅ કોઈન્સ ઉમેરાઈ ગયા!", reply_markup=get_admin_kb())
    except: await update.message.reply_text("❌ ભૂલ થઈ! ID ચેક કરો.")
    return ConversationHandler.END

async def ad_broadcast_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📢 બધાને મોકલવા માટે મેસેજ લખો:")
    return AD_BROADCAST

async def ad_broadcast_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db_query("SELECT user_id FROM users", fetchall=True)
    await update.message.reply_text(f"⏳ {len(users)} યુઝર્સને મોકલી રહ્યો છું...")
    for u in users:
        try:
            await context.bot.send_message(u[0], f"📢 **ADMIN UPDATE**\n\n{update.message.text}")
            await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text("✅ બ્રોડકાસ્ટ પૂરું!", reply_markup=get_admin_kb())
    return ConversationHandler.END

# --- GENERAL NAVIGATION ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text
    
    if txt == "💰 BALANCE":
        bal = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)[0]
        await update.message.reply_text(f"💰 તમારું બેલેન્સ: `{bal}` Coins")
    elif txt == "👤 OWNER":
        await update.message.reply_text("👤 **માલિક:** @kamod90\nકાંઈ પણ મદદ માટે મેસેજ કરો.")
    elif txt == "👥 REFER":
        bot_name = (await context.bot.get_me()).username
        await update.message.reply_text(f"🔗 **તમારી રેફરલ લિંક:**\n`https://t.me/{bot_name}?start={uid}`\n\nજો કોઈ તમારી લિંકથી જોડાશે તો તમને **20 Coins** મળશે!")
    elif txt == "🛠 ADMIN PANEL" and uid == ADMIN_ID:
        await update.message.reply_text("🛠 એડમિન મોડ એક્ટિવ:", reply_markup=get_admin_kb())
    elif txt == "🔙 Back to Menu" or txt == "🔙 રદ કરો":
        await update.message.reply_text("મેઈન મેનુ:", reply_markup=get_main_kb(uid))
    elif txt == "📊 Stats" and uid == ADMIN_ID:
        count = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        await update.message.reply_text(f"📊 **બોટ આંકડા:**\nકુલ યુઝર્સ: `{count}`")

# --- MAIN ---
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    # Conversation Handler (બધા જ ફંક્શન્સ માટે)
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^🔥 GENERATE ACCOUNTS$'), gen_start),
            MessageHandler(filters.Regex('^🎁 REDEEM$'), redeem_start),
            MessageHandler(filters.Regex('^🎟 Generate Promo$'), ad_promo_1),
            MessageHandler(filters.Regex('^💰 Add Balance$'), ad_bal_1),
            MessageHandler(filters.Regex('^📢 Broadcast$'), ad_broadcast_1),
        ],
        states={
            GEN_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, gen_get_region)],
            GEN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, gen_get_name)],
            GEN_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gen_process)],
            REDEEM_INP: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_process)],
            AD_CODE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_promo_2)],
            AD_CODE_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_promo_3)],
            AD_CODE_LIM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_promo_4)],
            AD_BAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_bal_2)],
            AD_BAL_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_bal_3)],
            AD_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_broadcast_2)],
        },
        fallbacks=[MessageHandler(filters.Regex('^🔙 Back to Menu$'), lambda u,c: ConversationHandler.END)],
        allow_reentry=True
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_cb, pattern="verify"))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("બોટ સફળતાપૂર્વક ચાલુ થઈ ગયો છે!")
    app.run_polling()

if __name__ == '__main__':
    main()