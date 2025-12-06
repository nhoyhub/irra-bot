# -*- coding: utf-8 -*-
import logging
import asyncio
from datetime import datetime
import aiohttp
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- CONFIGURATION ---
BOT_TOKEN = "7586151294:AAE56w1KsB01qmfebOY4jccne2VI11ueMqM"
BOT_2_TOKEN = "7836377853:AAHvTlYlqK-TbvbwVRzvG5oPotaFdNntn3A" # Admin Bot

# Admin Chat IDs
ADMIN_CHAT_ID = "1732455712"
BOT_2_ADMIN_CHAT_ID = "1732455712"

# Link to Flask Backend (Must match app.py)
BACKEND_API_URL = "http://127.0.0.1:5000/api/v1/save_order"

# Payment Link
ABA_PAY_LINK = "https://pay.ababank.com/oRF8/2ug5pzi4"

# --- ASSET URLs ---
START_PHOTO_URL = "https://i.pinimg.com/736x/fa/af/0a/faaf0a3dbfeff4591b189d7b5016ae04.jpg"
PAYMENT_PHOTO_URL = "https://i.pinimg.com/1200x/44/4b/af/444baf1fba6fcf56f53d3740162d2e61.jpg"
QR_PHOTO_10_URL = "https://i.pinimg.com/736x/c2/c5/03/c2c50300cc357884d7819e57e4e9d860.jpg"
SUCCESS_PHOTO_URL = "https://i.pinimg.com/originals/23/50/8e/23508e8b1e8dea194d9e06ae507e4afc.gif"
REJECTED_PHOTO_URL = "https://i.pinimg.com/originals/a5/75/0b/a5750babcf0f417f30e0b4773b29e376.gif"

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- IN-MEMORY DATA ---
user_data = {}
pending_approvals = {}
completed_orders = {} 

# --- HELPER FUNCTIONS ---

async def send_alert_after_30s(user_id: int) -> None:
    await asyncio.sleep(30)

async def send_to_bot_2_for_approval(user_id: int, username: str, udid: str, payment_option: str) -> bool:
    """Send approval request to Admin Bot"""
    url = f"https://api.telegram.org/bot{BOT_2_TOKEN}/sendMessage"
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    message_text = (
        f"🔍 សំណើរស្នើសុំការអនុម័ត\n\n"
        f"👤 អ្នកប្រើប្រាស់: {username}\n"
        f"🆔 លេខសំគាល់: {user_id}\n"
        f"📱 UDID: {udid}\n"
        f"💳 តម្លៃបង់ប្រាក់: {payment_option}\n"
        f"⏰ ពេលវេលា: {current_time}\n\n"
        f"សូមពិនិត្យនិងសម្រេចចិត្ត:"
    )
    
    keyboard = [
        [
            {"text": "✅ អនុម័ត", "callback_data": f"approve_{user_id}"},
            {"text": "❌ បដិសេធ", "callback_data": f"reject_{user_id}"}
        ],
        [
            {"text": "📋 ចម្លង UDID", "callback_data": f"copyudid_{user_id}"}
        ]
    ]
    
    payload = {
        'chat_id': BOT_2_ADMIN_CHAT_ID,
        'text': message_text,
        'reply_markup': json.dumps({"inline_keyboard": keyboard})
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"Error sending to Bot 2: {e}")
        return False

async def send_response_to_user(user_id: int, approved: bool) -> bool:
    """
    1. Notify User
    2. Save to Backend Database
    """
    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    # Retrieve info from memory
    user_info = pending_approvals.get(user_id)
    
    # Fallback if memory was cleared (e.g. restart)
    if not user_info and user_id in completed_orders:
        user_info = completed_orders[user_id]
    
    if approved and user_info:
        username = user_info.get('username', 'Unknown')
        udid = user_info.get('udid', 'N/A')
        payment_option = user_info.get('payment_option', '0')
        display_name = username.replace('@', '') if username.startswith('@') else username
        photo_url = SUCCESS_PHOTO_URL
        
        # --- 🟢 IMPORTANT: SAVE TO BACKEND ---
        payload_db = {
            "user_id": user_id,
            "username": username,
            "udid": udid,
            "payment_option": payment_option,
            "completion_time": datetime.now().isoformat()
        }
        
        print(f"🔄 Sending data to Backend for User {user_id}...") 

        try:
            async with aiohttp.ClientSession() as session:
                # ✅ FIX: Added Headers to ensure Flask reads JSON correctly
                async with session.post(
                    BACKEND_API_URL, 
                    json=payload_db,
                    headers={'Content-Type': 'application/json'}
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Data saved to Web Backend for {user_id}")
                        print("✅ SUCCESS: Saved to Database!")
                    else:
                        error_msg = await resp.text()
                        logger.error(f"❌ Failed to save to DB. Status: {resp.status}. Msg: {error_msg}")
                        print(f"❌ ERROR: Backend rejected data: {error_msg}")
        except Exception as e:
            logger.error(f"❌ Connection error to Backend: {e}")
            print(f"⚠️ Check if app.py is running! Error: {e}")
        # -------------------------------------

        # Save to local cache
        completed_orders[user_id] = {
            'username': username,
            'udid': udid,
            'payment_option': payment_option,
            'completion_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        caption = (
            f"🎉 *អរគុណ {escape_markdown(display_name, version=2)}\\!* ✅\n\n"
            f"ការបញ្ជាទិញបានបញ្ចប់ហើយ\\. 🎊\n\n"
            f"📱 UDID: `{escape_markdown(udid, version=2)}`\n"
            f"💰 តម្លៃ: `${payment_option}`\n"
            f"⏳ កំពុងដំណេីរការ``\n\n"
            f"🔄 ទិញថ្មី​​ សូមចុច​​​​ /start \n"
            f"📋 ពិនិត្យការទិញបានបញ្ចប់ /Details"
        )
        asyncio.create_task(send_alert_after_30s(user_id))
        
    else:
        photo_url = REJECTED_PHOTO_URL
        caption = (
            "❌ *សំណើរមិនត្រូវបានអនុម័ត*\n\n"
            "សូមព្យាយាមម្តងទៀតឬទាក់ទងផ្នែកជំនួយ\\.\n"
            "ទិញម្តងទៀត /start  \\."
        )
    
    payload = {
        'chat_id': str(user_id),
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'MarkdownV2'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(tg_url, data=payload) as response:
                return response.status == 200
    except Exception:
        return False

def validate_udid(udid: str) -> bool:
    if not udid: return False
    return 20 <= len(udid) <= 50 and all(c in '0123456789abcdefABCDEF-' for c in udid)

# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message: return
    user = update.effective_user
    user_id = user.id

    if user_id in user_data: del user_data[user_id]

    keyboard = [[InlineKeyboardButton("📱 ទាញយក UDID Profile", url="https://udid.tech/download-profile")]]
    
    HELP_URL = "https://t.me/Irra_Esign/3"
    caption = (
        f"🎉 *ស្វាគមន៍ {escape_markdown(user.first_name, version=2)}\\!* 🎉\n\n"
        "📋 *របៀបចាប់ផ្តើម:*\n\n"
        "1️⃣ ចុចប៊ូតុងខាងក្រោមដើម្បីទាញយក UDID profile\\.\n"
        "2️⃣ ដំឡើងវានៅលើឧបករណ៍របស់អ្នក\\.\n"
        "3️⃣ ចម្លង UDID របស់អ្នកនិងផ្ញើមកខ្ញុំ\\.\n\n"
        f"💡 [{escape_markdown('របៀប​ Download UDID profile?', version=2)}]({escape_markdown(HELP_URL, version=2)}) "
    )
    
    await update.message.reply_photo(photo=START_PHOTO_URL, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')

async def details_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in completed_orders:
        await update.message.reply_text("❌ *រកមិនឃើញព័ត៌មានការបញ្ជាទិញ*\nសូមបញ្ជាទិញជាមុនសិន /start", parse_mode='MarkdownV2')
        return
    
    info = completed_orders[user_id]
    text = (
        f"📋 *ព័ត៌មានការបញ្ជាទិញ*\n\n"
        f"📱 UDID: `{escape_markdown(info['udid'], version=2)}`\n"
        f"💳 Price: `${info['payment_option']}`\n"
        f"⏰ Date: `{escape_markdown(info['completion_time'], version=2)}`"
    )
    await update.message.reply_text(text, parse_mode='MarkdownV2')

async def handle_udid_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text: return
    user_id = update.effective_user.id
    udid = update.message.text.strip()
    
    if not validate_udid(udid):
        await update.message.reply_text("❌ *ទម្រង់ UDID មិនត្រឹមត្រូវ*\nUDID ត្រូវតែមានលេខនិងអក្សរប្រវែង 20-50 តួ។", parse_mode='MarkdownV2')
        return
    
    user_data[user_id] = {'udid': udid}
    keyboard = [[InlineKeyboardButton("🟢 Esign Premium - 10$", callback_data="payment_10")]]
    
    caption = f"✅ <b>បានទទួល UDID:</b> <code>{udid}</code>\n\n👇 <b>ជ្រេីសរេីសតម្លៃ:</b>"
    await update.message.reply_photo(photo=PAYMENT_PHOTO_URL, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def handle_payment_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in user_data:
        await query.edit_message_text("❌ Session expired. សូមចុច /start ម្តងទៀត។")
        return

    payment_option = query.data.split('_')[1]
    user_data[user_id]['payment_option'] = payment_option
    
    caption = (
        f"💳 *Esign Premium \\- ${payment_option}*\n"
        f"📱 *UDID:* `{escape_markdown(user_data[user_id]['udid'], version=2)}`\n\n"
        f"1️⃣ Scan QR code ឬចុចប៊ូតុង Pay Now\n"
        f"2️⃣ ថតរូបភាពបង់ប្រាក់ \\(Screenshot\\)\n"
        f"3️⃣ ផ្ញើរូបភាពចូលក្នុង Chat នេះ\\."
    )
    
    keyboard = [
        [InlineKeyboardButton("Pay Now", url=ABA_PAY_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_caption(caption="✅ កំពុងដំណើរការ...", reply_markup=None)
    
    await query.message.reply_photo(
        photo=QR_PHOTO_10_URL, 
        caption=caption, 
        reply_markup=reply_markup, 
        parse_mode='MarkdownV2'
    )

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    
    if user_id not in user_data or 'payment_option' not in user_data[user_id]:
        await update.message.reply_text("❌ សូមចុច /start ដើម្បីចាប់ផ្តើម។")
        return
    
    if user_id in pending_approvals:
        await update.message.reply_text("⏳ សំណើររបស់អ្នកកំពុងត្រូវបានត្រួតពិនិត្យ។")
        return
        
    username = f"@{user.username}" if user.username else user.first_name
    
    pending_approvals[user_id] = {
        'username': username,
        'udid': user_data[user_id]['udid'],
        'payment_option': user_data[user_id]['payment_option'],
        'timestamp': datetime.now()
    }
    
    await update.message.reply_text("🔄 បានទទួលរូបភាព។ សូមរង់ចាំ Admin ត្រួតពិនិត្យ...")
    
    # Send to Admin Bot
    await send_to_bot_2_for_approval(user_id, username, user_data[user_id]['udid'], user_data[user_id]['payment_option'])

async def handle_bot2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Admin Actions (Approve/Reject/Copy)"""
    query = update.callback_query
    await query.answer()
    
    try:
        action, user_id_str = query.data.split('_', 1)
        user_id = int(user_id_str)
    except:
        return

    if action == "copyudid":
        user_info = pending_approvals.get(user_id)
        if user_info:
            await query.message.reply_text(f"`{user_info['udid']}`", parse_mode='MarkdownV2')
        else:
            await query.message.reply_text("រកមិនឃើញទិន្នន័យ។")
        return

    if user_id not in pending_approvals:
        await query.edit_message_text("❌ សំណើរនេះត្រូវបានដំណើរការរួចហើយ។")
        return

    approved = (action == "approve")
    
    # Notify User & Save to DB
    await send_response_to_user(user_id, approved)
    
    status = "✅ បានអនុម័ត" if approved else "❌ បានបដិសេធ"
    
    current_text = query.message.text
    await query.edit_message_text(f"{current_text}\n\nស្ថានភាព: {status}", reply_markup=None)
    
    del pending_approvals[user_id]
    if approved and user_id in user_data: del user_data[user_id]

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message: return
    text = update.message.text
    
    if 'start' in text.lower(): 
        await start(update, context)
    else: 
        await handle_udid_input(update, context)

async def main() -> None:
    app1 = Application.builder().token(BOT_TOKEN).build()
    app2 = Application.builder().token(BOT_2_TOKEN).build()
    
    # Bot 1 Handlers (User)
    app1.add_handler(CommandHandler("start", start))
    app1.add_handler(CommandHandler("details", details_order))
    app1.add_handler(CallbackQueryHandler(handle_payment_button, pattern='^payment_'))
    app1.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app1.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Bot 2 Handlers (Admin)
    app2.add_handler(CallbackQueryHandler(handle_bot2_callback))
    
    print("🚀 Bots are running...")
    print(f"🔗 Connected to Backend: {BACKEND_API_URL}")
    print(f"💰 ABA Link Active: {ABA_PAY_LINK}")
    
    async with app1, app2:
        await app1.start()
        await app2.start()
        await asyncio.gather(
            app1.updater.start_polling(),
            app2.updater.start_polling()
        )
        await asyncio.Future()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass