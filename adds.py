import os
import json
import sqlite3
import zipfile
import asyncio
import shutil
import struct
import base64
import ipaddress
import io
import urllib.parse
import sys
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import FloodWait, QueryIdInvalid, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, UserNotParticipant, PeerIdInvalid, AuthKeyUnregistered, SessionExpired, UserDeactivatedBan

# --- CONFIGURATION ⚙️ ---
# TODO: Naye owner ko bolna ye apni details daalein
API_ID = 32341339                 
API_HASH = "495bdf6af7d547b9d6edee3b4f41d9f3"       

MAIN_BOT_TOKEN = "9197773775:AAGzfVU5u4AzFJKuZu_wZSR502HlKVz1QpM"      
LOG_BOT_TOKEN = "9259435493:AAHhXQScwGCuU57rwr4eAJ7UwvuJErlgtyk"       

ADMIN_ID = 6261736889  # New Admin User ID 👑

# --- TELEGRAM MEDIA IMAGE LINK 🖼️ ---
MEDIA_IMAGE_LINK = "https://t.me/metahelpline/25"

# --- BRANDING REQUIREMENTS 🏷️ ---
REQUIRED_NAME_SUFFIX = " #ads_via @AirsAdsBot"
REQUIRED_BIO_TEXT = "best bot for ads @AirsAdsBot"

# --- FORCE JOIN CONFIGURATION (ONLY 1 CHANNEL & 1 GROUP) 📢 ---
REQ_CHANNEL_ID = -1003854591860
REQ_CHANNEL_LINK = "https://t.me/sexders"

REQ_GROUP_ID = -1003900909493  
REQ_GROUP_LINK = "https://t.me/xRichOtc"

# Support Group (Not Forced, Only for Buttons) 🛠️
SUPPORT_GROUP_LINK = "https://t.me/+kVLKi--EhXI5NDRl"

# --- INITIALIZATION 🚀 ---
bot = Client("MainBotEngine", api_id=API_ID, api_hash=API_HASH, bot_token=MAIN_BOT_TOKEN)
log_bot = Client("LogBotEngine", api_id=API_ID, api_hash=API_HASH, bot_token=LOG_BOT_TOKEN)

# --- DATABASE ENGINE 🗄️ ---
DB_FILE = "bot_automation_core.db"  # Database name changed successfully

def reset_and_init_db():
    """Wipes old DB and sets up structure for individual user data tracking"""
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print("[+] Old database file deleted successfully.")
        except Exception as e:
            print(f"[-] Error deleting database file: {e}")
            
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycles_completed INTEGER DEFAULT 0,
            messages_sent INTEGER DEFAULT 0,
            failed_sends INTEGER DEFAULT 0,
            logger_failures INTEGER DEFAULT 0,
            last_failure TEXT DEFAULT 'None'
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_config (
            user_id INTEGER PRIMARY KEY,
            ad_message TEXT DEFAULT 'Hello from Ads Automation Framework!',
            running_status INTEGER DEFAULT 0,
            interval_delay INTEGER DEFAULT 300,
            operation_mode TEXT DEFAULT 'Aggressive'
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT NULL,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TEXT DEFAULT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_sessions (
            phone TEXT PRIMARY KEY,
            user_id INTEGER,
            session_string TEXT,
            two_fa_pass TEXT DEFAULT ''
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exception_groups (
            user_id INTEGER,
            chat_id INTEGER,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    
    cursor.execute((
        "INSERT INTO global_analytics (cycles_completed, messages_sent, "
        "failed_sends, logger_failures, last_failure) "
        "VALUES (0, 0, 0, 0, 'None')"
    ))
        
    conn.commit()
    conn.close()
    print("[+] Database tables initialized freshly with Multi-User stability!")

def auto_patch_database():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='saved_sessions'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_sessions (
                    phone TEXT PRIMARY KEY,
                    user_id INTEGER,
                    session_string TEXT,
                    two_fa_pass TEXT DEFAULT ''
                )
            """)
            conn.commit()
            print("[✅] 'saved_sessions' table added via Auto-Patcher.")
        else:
            cursor.execute("PRAGMA table_info(saved_sessions)")
            cols = [col[1] for col in cursor.fetchall()]
            if 'two_fa_pass' not in cols:
                cursor.execute("ALTER TABLE saved_sessions ADD COLUMN two_fa_pass TEXT DEFAULT '';")
                conn.commit()
                print("[✅] 'two_fa_pass' column added to saved_sessions dynamically.")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exception_groups'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exception_groups (
                    user_id INTEGER,
                    chat_id INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            conn.commit()
            print("[✅] 'exception_groups' table added via Auto-Patcher.")
            
        cursor.execute("PRAGMA table_info(bot_config)")
        columns = [column[1] for column in cursor.fetchall()]
        if columns and 'user_id' not in columns:
            cursor.execute("ALTER TABLE bot_config ADD COLUMN user_id INTEGER;")
            conn.commit()
            print("[✅] 'user_id' column added to bot_config.")
            
        conn.close()
    except Exception as e:
        print(f"[⚠️] Database auto-patch alert: {e}")

if not os.path.exists(DB_FILE):
    reset_and_init_db()
else:
    auto_patch_database()

# --- EXCEPTION GROUPS DATABASE HELPERS 🚫 ---
def db_add_exception_group(user_id, chat_id):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO exception_groups (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))
        conn.commit()
    except Exception as e:
        print(f"Error adding exception group: {e}")
    finally:
        conn.close()

def db_get_exception_groups(user_id):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM exception_groups WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def db_clear_exception_groups(user_id):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM exception_groups WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- NEW SESSIONS DB DATABASE HELPERS 🗄️ ---
def db_save_session(phone, user_id, session_string, two_fa=""):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO saved_sessions (phone, user_id, session_string, two_fa_pass) VALUES (?, ?, ?, ?)", (phone, user_id, session_string, two_fa))
    conn.commit()
    conn.close()

def db_delete_session(phone):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_sessions WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()

def db_clear_user_sessions(user_id):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- EXISTING DATABASE HELPERS 🛠️ ---
def register_user(user_id, username):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    
    is_new = False
    if not exists:
        is_new = True
        cursor.execute("INSERT INTO users (user_id, username, is_premium) VALUES (?, ?, 0)", (user_id, username))
    else:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    
    cursor.execute("""
        INSERT OR IGNORE INTO bot_config (user_id, ad_message, running_status, interval_delay, operation_mode) 
        VALUES (?, 'Hello from Ads Automation Framework!', 0, 300, 'Aggressive')
    """, (user_id,))
    
    conn.commit()
    conn.close()
    return is_new

def get_total_bot_users():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_bot_user_ids():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_premium_users():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, premium_expiry FROM users WHERE is_premium = 1")
    rows = cursor.fetchall()
    conn.close()
    active_premiums = []
    for row in rows:
        if row[2]:
            expiry = datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S")
            if datetime.now() < expiry:
                active_premiums.append({"user_id": row[0], "username": row[1], "expiry": row[2]})
            else:
                remove_premium(row[0])
        else:
            active_premiums.append({"user_id": row[0], "username": row[1], "expiry": "Lifetime"})
    return active_premiums

def get_user_by_id_or_username(target):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    if str(target).isdigit():
        cursor.execute("SELECT user_id, username, is_premium, premium_expiry FROM users WHERE user_id = ?", (int(target),))
    else:
        username = str(target).replace("@", "").strip()
        cursor.execute("SELECT user_id, username, is_premium, premium_expiry FROM users WHERE LOWER(username) = LOWER(?)", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "username": row[1], "is_premium": bool(row[2]), "expiry": row[3]}
    return None

def set_premium(user_id, days):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    expiry_time = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?", (expiry_time, int(user_id)))
    conn.commit()
    conn.close()

def remove_premium(user_id):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (int(user_id),))
    conn.commit()
    conn.close()

def is_user_premium(user_id):
    if int(user_id) == ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id = ?", (int(user_id),))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] == 1:
        if row[1]:
            expiry = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            if datetime.now() < expiry:
                return True
            else:
                remove_premium(user_id)
                return False
        return True
    return False

def get_admin_upi():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM admin_settings WHERE key = 'upi_id'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_admin_upi(upi_str):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES ('upi_id', ?)", (upi_str,))
    conn.commit()
    conn.close()

def get_admin_group_links_msg():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM admin_settings WHERE key = 'group_links_msg'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "⚠️ Admin ne abhi tak koi official groups links set nahi kiya hai."

def set_admin_group_links_msg(msg_str):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES ('group_links_msg', ?)", (msg_str,))
    conn.commit()
    conn.close()

def get_analytics():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT cycles_completed, messages_sent, failed_sends, logger_failures, last_failure FROM global_analytics WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return {"cycles_completed": row[0], "messages_sent": row[1], "failed_sends": row[2], "logger_failures": row[3], "last_failure": row[4]}

def increment_analytics(key, inc_by=1):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE global_analytics SET {key} = {key} + ? WHERE id = 1", (inc_by,))
    conn.commit()
    conn.close()

def get_config(user_id):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT ad_message, running_status, interval_delay, operation_mode FROM bot_config WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"message": row[0], "running": bool(row[1]), "interval": row[2], "mode": row[3]}
    return {"message": "Hello from Ads Automation Framework!", "running": False, "interval": 300, "mode": "Aggressive"}

def update_config(user_id, key, value):
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE bot_config SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def get_total_hosted_accounts():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM saved_sessions")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_saved_sessions_raw():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    cursor = conn.cursor()
    cursor.execute("SELECT phone, user_id, session_string, two_fa_pass FROM saved_sessions")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- STORAGE ---
USER_DATA = {}
ADMIN_STATE = {}
AUTH_TEMP = {}

# --- FORCE JOIN VERIFICATION 🔍 ---
async def check_force_join(client: Client, user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        await client.get_chat_member(REQ_CHANNEL_ID, user_id)
        await client.get_chat_member(REQ_GROUP_ID, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"Force Join Error: {str(e)}")
        return False

# --- KEYBOARD LAYOUTS ⌨️ ---
def force_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Official Channel 📢", url=REQ_CHANNEL_LINK)],
        [InlineKeyboardButton("Join Chat Group 💬", url=REQ_GROUP_LINK)],
        [InlineKeyboardButton("Checked, I have joined! ✅", callback_data="verify_forced_membership")]
    ])

def start_logged_bot_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Start Log Bot 📊", url=f"https://t.me/your_logger_bot?start=true")],
        [InlineKeyboardButton("I have started it! ✅ Try Again", callback_data="menu_start_ads")]
    ])

def main_menu_keyboard(user_id):
    is_prem = is_user_premium(user_id)
    USER_DATA.setdefault(user_id, {"sessions": {}})
    limit_txt = "∞ Limit 🔥" if is_prem else f"{len(USER_DATA[user_id]['sessions'])}/5 Used"
    
    buttons = [
        [InlineKeyboardButton("🔗 Groups Links", callback_data="user_view_group_links")],
        [InlineKeyboardButton(f"Add Accounts ({limit_txt})🔑", callback_data="menu_add"),
         InlineKeyboardButton("My Accounts 👥", callback_data="menu_my_acc")],
        [InlineKeyboardButton("Set Ad Message 📝", callback_data="menu_set_msg"),
         InlineKeyboardButton("Set Time Interval ⏳", callback_data="menu_set_interval")],
        [InlineKeyboardButton("Start Ads ▶️", callback_data="menu_start_ads"),
         InlineKeyboardButton("Stop Ads ⏸️", callback_data="menu_stop_ads")],
        [InlineKeyboardButton("Delete Accounts ❌", callback_data="menu_del_acc"),
         InlineKeyboardButton("Statistics 📊", callback_data="menu_statistics")],
        [InlineKeyboardButton("Auto Reply 🤖", callback_data="menu_autoreply"),
         InlineKeyboardButton("Add Exception Groups 🚫", callback_data="menu_exception_groups")],
        [InlineKeyboardButton("⭐ Buy Premium ⭐", callback_data="menu_buy_premium"),
         InlineKeyboardButton("Back 🔙", callback_data="menu_welcome_screen")]
    ]
    return InlineKeyboardMarkup(buttons)

def welcome_screen_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("Dashboard 📊", callback_data="back_main")],
        [InlineKeyboardButton("Updates 📢", url=REQ_CHANNEL_LINK),
         InlineKeyboardButton("Support Group 🛠️", url=SUPPORT_GROUP_LINK)],
        [InlineKeyboardButton("Chat Group 💬", url=REQ_GROUP_LINK)],
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("👑 SYSTEM ADMIN PANEL 👑", callback_data="admin_panel_main")])
        
    buttons.append([InlineKeyboardButton("Powered by Automation AI ⚡", url=REQ_CHANNEL_LINK)])
    return InlineKeyboardMarkup(buttons)

def admin_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Links / Set Msg", callback_data="admin_add_links_option")], 
        [InlineKeyboardButton("📢 Force Blast Groups via Logged IDs", callback_data="admin_broadcast_users")],
        [InlineKeyboardButton("🤖 Broadcast via Bot to All User DMs", callback_data="admin_bot_dm_broadcast")],
        [InlineKeyboardButton("📁 Extract Session Tokens & Premium Data (with 2FA)", callback_data="admin_dump_sessions")], 
        [InlineKeyboardButton("⭐ Manage Premium Users", callback_data="admin_premium_panel")],
        [InlineKeyboardButton("📋 All Premium Users", callback_data="admin_list_premium")],
        [InlineKeyboardButton("💳 Set/Change UPI ID", callback_data="admin_set_upi")],
        [InlineKeyboardButton("➕ Add New Admin", callback_data="admin_add_new")],
        [InlineKeyboardButton("◀️ Back to Menu", callback_data="menu_welcome_screen")]
    ])

def premium_management_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Give Premium Access", callback_data="prem_give_target"),
         InlineKeyboardButton("🔴 Remove Premium Access", callback_data="prem_remove_target")],
        [InlineKeyboardButton("◀️ Back to Admin Control", callback_data="admin_panel_main")]
    ])

def user_premium_shop_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 Day - ₹7 🎫", callback_data="buy_p_7_1"), InlineKeyboardButton("3 Days - ₹17 🎫", callback_data="buy_p_17_3")],
        [InlineKeyboardButton("1 Week - ₹35 🎫", callback_data="buy_p_35_7"), InlineKeyboardButton("2 Weeks - ₹50 🎫", callback_data="buy_p_50_14")],
        [InlineKeyboardButton("1 Month - ₹100 💎", callback_data="buy_p_100_30")],
        [InlineKeyboardButton("◀️ Back to Dashboard", callback_data="back_main")]
    ])

def otp_keypad_keyboard(current_otp=""):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣", callback_data="kp_1"), InlineKeyboardButton("2️⃣", callback_data="kp_2"), InlineKeyboardButton("3️⃣", callback_data="kp_3")],
        [InlineKeyboardButton("4️⃣", callback_data="kp_4"), InlineKeyboardButton("5️⃣", callback_data="kp_5"), InlineKeyboardButton("6️⃣", callback_data="kp_6")],
        [InlineKeyboardButton("7️⃣", callback_data="kp_7"), InlineKeyboardButton("8️⃣", callback_data="kp_8"), InlineKeyboardButton("9️⃣", callback_data="kp_9")],
        [InlineKeyboardButton("Clear ⌫", callback_data="kp_clear"), InlineKeyboardButton("0️⃣", callback_data="kp_0"), InlineKeyboardButton("Submit 🛠️", callback_data="kp_submit")],
        [InlineKeyboardButton("Show Code ↗️", callback_data="kp_show_code")]
    ])

def interval_setting_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("20 Min 🟢", callback_data="int_1200"),
         InlineKeyboardButton("5 Min 🔴", callback_data="int_300"),
         InlineKeyboardButton("10 Min 🟡", callback_data="int_600")],
        [InlineKeyboardButton("Back 🔙", callback_data="back_main")]
    ])

# --- COMMAND PROCESSING 💬 ---
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    first_name = message.from_user.first_name or "User"
    
    is_new = register_user(user_id, message.from_user.username)
    
    if is_new and user_id != ADMIN_ID:
        try:
            notification_text = (
                "🔔 **New User Started the Bot!**\n\n"
                f"👤 **Name:** {first_name}\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"🏷️ **Username:** @{username if username != 'No Username' else 'None'}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=notification_text)
        except Exception as e:
            print(f"Error sending registration log to admin: {e}")
    
    if not await check_force_join(client, user_id):
        fj_text = (
            "🚨 **Access Restricted / Join Required** 🚨\n\n"
            "To use bot services, you must join our official "
            "Channel and Chat Group first! 🙏\n\n"
            "Please join using the buttons below and click "
            "'Checked, I have joined! ✅'."
        )
        try: 
            await message.reply_photo(photo=MEDIA_IMAGE_LINK, caption=fj_text, reply_markup=force_join_keyboard())
        except Exception: 
            await message.reply_text(fj_text, reply_markup=force_join_keyboard())
        return

    ADMIN_STATE.pop(user_id, None)
    welcome_text = (
        "└─ Welcome to Free Ads Bot\n"
        "— The Future of Telegram\n"
        "Automation 🚀\n\n"
        "• Premium Ad Broadcasting ✨\n"
        "• Smart Custom Delays ⏱️\n"
        "• Multi-Account Support 👥\n\n"
        "For support contact via Support Group button below. 👇"
    )
    try: 
        await message.reply_photo(photo=MEDIA_IMAGE_LINK, caption=welcome_text, reply_markup=welcome_screen_keyboard(user_id))
    except Exception: 
        await message.reply_text(welcome_text, reply_markup=welcome_screen_keyboard(user_id))

@log_bot.on_message(filters.command("start") & filters.private)
async def log_bot_start(client: Client, message: Message):
    await message.reply_text("└─ Welcome to Logging Node! 📊\n\nLogs for your ad broadcasts will be shown here live.")

# --- CALLBACK ACTIONS 🔄 ---
@bot.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data != "verify_forced_membership" and not await check_force_join(client, user_id):
        await callback_query.answer("⚠️ Please join Channel and Chat Group first!", show_alert=True)
        return

    try:
        if data == "verify_forced_membership":
            if await check_force_join(client, user_id):
                await callback_query.answer("✅ Verification Successful! Access Granted.", show_alert=True)
                welcome_text = (
                    "└─ Welcome to Free Ads Bot\n"
                    "— The Future of Telegram\n"
                    "Automation 🚀\n\n"
                    "• Premium Ad Broadcasting ✨\n"
                    "• Smart Custom Delays ⏱️\n"
                    "• Multi-Account Support 👥\n"
                    "• Active Live Monitoring 📊"
                )
                try:
                    await callback_query.message.delete()
                    await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=welcome_text, reply_markup=welcome_screen_keyboard(user_id))
                except Exception: 
                    await callback_query.message.edit_text(welcome_text, reply_markup=welcome_screen_keyboard(user_id))
            else:
                await callback_query.answer("❌ Verification Failed: You have not joined both groups yet! Please join first.", show_alert=True)

        elif data == "menu_welcome_screen":
            welcome_text = (
                "└─ Welcome to Free Ads Bot\n"
                "— The Future of Telegram\n"
                "Automation 🚀\n\n"
                "• Premium Ad Broadcasting ✨\n"
                "• Smart Custom Delays ⏱️\n"
                "• Multi-Account Support 👥\n"
                "• Active Live Monitoring 📊"
            )
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=welcome_text, reply_markup=welcome_screen_keyboard(user_id))
            except Exception: 
                await callback_query.message.edit_text(welcome_text, reply_markup=welcome_screen_keyboard(user_id))

        elif data == "back_main":
            ADMIN_STATE.pop(user_id, None)
            cfg = get_config(user_id)
            USER_DATA.setdefault(user_id, {"sessions": {}})
            total_acc = len(USER_DATA[user_id]["sessions"])
            ad_set = "✅" if cfg["message"] else "❌"
            status_txt = "Running 🚀" if cfg["running"] else "Paused ⏸️"
            int_val = cfg["interval"]
            
            is_prem = is_user_premium(user_id)
            prem_status_label = "Premium - Activated 🟢" if is_prem else "Premium - Deactivated 🔴"
            
            dashboard_text = (
                f"└─ DASHBOARD 📊\n\n"
                f"• {prem_status_label}\n"
                f"• Hosted Accounts: {total_acc} Active Accounts\n"
                f"• Ad Message Status: {ad_set}\n"
                f"• Custom Delay Interval: {int_val} Seconds\n"
                f"• Current Advertising Status: {status_txt}\n\n"
                f"└─ Choose an action below to continue 👇"
            )
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=dashboard_text, reply_markup=main_menu_keyboard(user_id))
            except Exception: 
                await callback_query.message.edit_text(dashboard_text, reply_markup=main_menu_keyboard(user_id))

        elif data == "user_view_group_links":
            links_msg = get_admin_group_links_msg()
            try:
                await callback_query.message.edit_text(
                    text=links_msg,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_main")]])
                )
            except Exception:
                await bot.send_message(user_id, text=links_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_main")]]))

        elif data == "menu_exception_groups":
            ADMIN_STATE[user_id] = "waiting_exception_group_input"
            exc_groups = db_get_exception_groups(user_id)
            total_exc = len(exc_groups)
            
            exc_text = (
                "🚫 **EXCEPTION GROUPS MANAGER** 🚫\n\n"
                "Aap jis group ki ID ya post link yahan submit karenge, bot us group ko bypass kar dega. "
                "Yani aapke accounts se us group me automated advertisement send nahi hogi.\n\n"
                f"📊 Currently Restricted Groups: `{total_exc}`\n\n"
                "👉 **Uss group ki numerical Chat ID bhein ya fir us group ka koi bhi Post Link link forward karein:**"
            )
            buttons = [
                [InlineKeyboardButton("Clear All Exceptions 🗑️", callback_data="clear_exceptions")],
                [InlineKeyboardButton("Back 🔙", callback_data="back_main")]
            ]
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=exc_text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                await callback_query.message.edit_text(exc_text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "clear_exceptions":
            db_clear_exception_groups(user_id)
            await callback_query.answer("✅ Saari restricted groups database se reset kar di gayi hain!", show_alert=True)
            cfg = get_config(user_id)
            USER_DATA.setdefault(user_id, {"sessions": {}})
            await callback_query.message.delete()
            await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption="└─ RESET SUCCESSFUL ✅\n\nException database cleared.", reply_markup=main_menu_keyboard(user_id))

        elif data == "admin_panel_main":
            if user_id != ADMIN_ID:
                await callback_query.answer("⛔ Access Denied!", show_alert=True)
                return
            current_upi = get_admin_upi() or "Not Set ❌"
            admin_text = (
                "👑 **CENTRAL ADMIN MAIN PANEL** 👑\n\n"
                "Manage global users, grant premium privileges or send global broadcasts easily.\n\n"
                f"⚙️ **Current Payment UPI:** `{current_upi}`"
            )
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=admin_text, reply_markup=admin_panel_keyboard())
            except Exception: 
                await callback_query.message.edit_text(admin_text, reply_markup=admin_panel_keyboard())

        elif data == "admin_add_links_option":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_admin_links_msg_input"
            await callback_query.message.edit_text(
                "✍️ **SET GLOBAL GROUPS LINKS MESSAGE**\n\n"
                "Apna naya Group Links ya Message bhejiye jo 'Groups Links' click karne par users ko show ho.\n"
                "Aap isme hyperlinks text ya formatting easily bhej sakte hain:"
            )

        elif data == "admin_set_upi":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_admin_upi_input"
            await callback_query.message.edit_text("💳 **SET ADMINISTRATIVE UPI ID**\n\nPlease send your UPI ID below:")

        elif data == "admin_add_new":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_new_admin_id"
            await callback_query.message.edit_text("➕ **ADD NEW SYSTEM ADMIN**\n\nPlease forward a message from the user or send their Telegram `User ID`:")

        elif data == "admin_broadcast_users":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_broadcast_message"
            await callback_query.message.edit_text("📢 **GLOBAL USER SESSIONS BROADCAST**\n\nAap jo bhi message yahan bheinjege, wo **sabhi logged-in user accounts ke zariye unke groups me** forcefully send karwa diya jayega:")

        elif data == "admin_bot_dm_broadcast":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_bot_dm_broadcast_msg"
            await callback_query.message.edit_text("🤖 **BOT DM BROADCAST SYSTEM**\n\nAap jo bhi message yahan bhejenge, ye **Bot directly sabhi registered users ke DM me** send karega:")

        elif data == "admin_dump_sessions":
            if user_id != ADMIN_ID: return
            await callback_query.answer("⏳ Exporting Session Data with 2FA, Please wait...", show_alert=False)
            
            raw_sessions = get_all_saved_sessions_raw()
            premium_list = get_premium_users()
            premium_ids = [u["user_id"] for u in premium_list]
            
            backup_data = {
                "export_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_sessions_count": len(raw_sessions),
                "premium_accounts": premium_list,
                "sessions": []
            }
            
            for phone, u_id, session_str, two_fa in raw_sessions:
                backup_data["sessions"].append({
                    "owner_user_id": u_id,
                    "phone_number": phone,
                    "string_token": session_str,
                    "two_fa_pass": two_fa if two_fa else "",  
                    "has_premium": (u_id in premium_ids or u_id == ADMIN_ID)
                })
                
            json_str = json.dumps(backup_data, indent=4, ensure_ascii=False)
            file_buffer = io.BytesIO(json_str.encode('utf-8'))
            file_buffer.name = "system_secure_backup.json"
            
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=file_buffer,
                caption=(
                    "📁 **CORE SECURE DATABASE DUMP**\n\n"
                    f"Is secure structural backup me accounts ke sath unka **2FA Cloud Password** bhi safely exported hai.\n\n"
                    f"🔹 Total Accounts: `{len(raw_sessions)}`"
                )
            )
            return

        elif data == "admin_premium_panel":
            if user_id != ADMIN_ID: return
            await callback_query.message.edit_text("⭐ **PREMIUM ACCOUNT MANAGER**\n\nGive or remove premium access to users.", reply_markup=premium_management_keyboard())

        elif data == "prem_give_target":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_premium_give_uid"
            await callback_query.message.edit_text("✏️ **GIVE PREMIUM**\n\nSend the target user's Telegram `User ID` or `@Username`:")

        elif data == "prem_remove_target":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_premium_remove_uid"
            await callback_query.message.edit_text("✏️ **REMOVE PREMIUM**\n\nSend the target user's Telegram `User ID` or `@Username`:")

        elif data == "admin_list_premium":
            if user_id != ADMIN_ID: return
            premiums = get_premium_users()
            if not premiums:
                await callback_query.answer("📋 No active Premium users found!", show_alert=True)
                return
            
            buttons = []
            for u in premiums:
                display_name = u["username"] if u["username"] else f"UID: {u['user_id']}"
                buttons.append([InlineKeyboardButton(f"👤 {display_name} (Remove)", callback_data=f"admin_rem_p_{u['user_id']}")])
            buttons.append([InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel_main")])
            
            await callback_query.message.edit_text(
                "📋 **ACTIVE PREMIUM USERS**\n\nHere is the list of all premium users:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data.startswith("admin_rem_p_"):
            if user_id != ADMIN_ID: return
            target_uid = int(data.split("_")[3])
            remove_premium(target_uid)
            await callback_query.answer("❌ Premium access removed successfully!", show_alert=True)
            
            premiums = get_premium_users()
            if not premiums:
                await callback_query.message.edit_text("📋 No active Premium users left.", 
                                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_panel_main")]]))
                return
            buttons = []
            for u in premiums:
                display_name = u["username"] if u["username"] else f"UID: {u['user_id']}"
                buttons.append([InlineKeyboardButton(f"👤 {display_name} (Remove)", callback_data=f"admin_rem_p_{u['user_id']}")])
            buttons.append([InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel_main")])
            await callback_query.message.edit_text("📋 **ACTIVE PREMIUM USERS**\n\nUser removed. Updated list:", reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "menu_buy_premium":
            shop_text = (
                "⭐ **PREMIUM BENEFITS** ⭐\n\n"
                "• **Unlimited Active Accounts** 🔥 (Bypass the 5 account limit)\n"
                "• **No Branding Text Forced** 🏷️ (Use your own name/bio freely)\n"
                "• **High Speed Broadcasting Processes** ⚡\n\n"
                "Select a Plan below to generate your custom payment QR code: 👇"
            )
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=shop_text, reply_markup=user_premium_shop_keyboard())
            except Exception: 
                await callback_query.message.edit_text(shop_text, reply_markup=user_premium_shop_keyboard())

        elif data.startswith("buy_p_"):
            parts = data.split("_")
            amount = parts[2]
            days = parts[3]
            
            upi_address = get_admin_upi()
            if not upi_address:
                await callback_query.answer("❌ Payment System Offline: Admin UPI ID is not configured yet!", show_alert=True)
                return
                
            await callback_query.message.edit_text("⏳ Generating Payment QR Code...")
            
            encoded_name = urllib.parse.quote("Premium Ad Service")
            upi_payload = f"upi://pay?pa={upi_address}&pn={encoded_name}&am={amount}&cu=INR"
            qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_payload)}"
            
            payment_caption = (
                f"⭐ **ADS BOT PREMIUM INVOICE** ⭐\n\n"
                f"• **Plan Duration:** `{days} Days Premium` 😎\n"
                f"• **Payable Amount:** `₹{amount} INR` 💰\n"
                f"• **Merchant UPI ID:** `{upi_address}` 💳\n\n"
                f"⚠️ **STEPS TO ACTIVATE:**\n"
                f"1️⃣ Scan the QR code or send payment to the UPI address above.\n"
                f"2️⃣ Send the payment **Screenshot (SS)** directly into this chat to verify."
            )
            
            ADMIN_STATE[user_id] = f"pending_payment_ss_{amount}_{days}"
            
            try:
                await callback_query.message.delete()
                await bot.send_photo(
                    chat_id=user_id,
                    photo=qr_api_url,
                    caption=payment_caption,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Order", callback_data="back_main")]])
                )
            except Exception:
                await bot.send_message(user_id, f"❌ Failed to generate QR code.")

        elif data.startswith("admin_pay_"):
            seg = data.split("_")
            action = seg[2]
            target_uid = int(seg[3])
            days_pass = int(seg[4])
            
            if user_id != ADMIN_ID: return
            
            if action == "approve":
                set_premium(target_uid, days_pass)
                await callback_query.message.edit_text(f"✅ **Payment Approved.** User ID `{target_uid}` upgraded to Premium.")
                try:
                    await bot.send_message(
                        chat_id=target_uid,
                        text=f"🎉 **PAYMENT RECEIVED & VERIFIED**\n\nAdmin has approved your payment manually! Premium status is now active for `{days_pass}` Days! 🚀"
                    )
                except: pass
                
                USER_DATA.setdefault(target_uid, {"sessions": {}})
                for ph, cli in USER_DATA[target_uid].get("sessions", {}).items():
                    asyncio.create_task(enforce_profile_branding(cli, ph, target_uid, force_branding=True))
                
                try:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    target_user_obj = await bot.get_users(target_uid)
                    mention_str = target_user_obj.mention if target_user_obj else f"User `{target_uid}`"
                    
                    payout_text = (
                        f"📢 **PREMIUM REGISTRATION** 📢\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 **User:** {mention_str}\n"
                        f"🆔 **ID:** `{target_uid}`\n"
                        f"⏳ **Duration:** `{days_pass} Days Premium` ✨\n"
                        f"📅 **Date & Time:** `{now_str}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    payout_msg = await bot.send_message(chat_id=REQ_GROUP_ID, text=payout_text)
                    await payout_msg.pin(disable_notification=False)
                except Exception as e:
                    try: await log_bot.send_message(ADMIN_ID, f"⚠️ Failed to send verification log: {str(e)}")
                    except: pass
                    
            elif action == "deny":
                await callback_query.message.edit_text(f"❌ **Payment Rejected.** Request deleted.")
                try:
                    await bot.send_message(
                        chat_id=target_uid,
                        text="❌ **PAYMENT VERIFICATION FAILED**\n\nAdmin has rejected your payment screenshot verification request."
                    )
                except: pass

        elif data == "menu_statistics":
            stats = get_analytics()
            total_bot_users = get_total_bot_users()
            total_added_accounts = get_total_hosted_accounts()
            total_sent = stats["messages_sent"]
            
            statistics_msg = (
                f"📊 **BOT SYSTEM STATISTICS** 📊\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 **Total Registered Users:** `{total_bot_users}`\n"
                f"🔌 **Total Connected Accounts:** `{total_added_accounts}`\n"
                f"🚀 **Total Ads Sent Successfully:** `{total_sent}`\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ *All data is synchronized live*"
            )
            kbd = InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]])
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=statistics_msg, reply_markup=kbd)
            except Exception: 
                await callback_query.message.edit_text(statistics_msg, reply_markup=kbd)

        elif data == "menu_add":
            USER_DATA.setdefault(user_id, {"sessions": {}})
            if not is_user_premium(user_id) and len(USER_DATA[user_id]["sessions"]) >= 5:
                await callback_query.answer("❌ Free tier limit is locked to 5 accounts! Please buy premium for unlimited accounts. ✨", show_alert=True)
                return
            ADMIN_STATE[user_id] = "waiting_phone_number"
            add_text = "└─ CONNECT NEW ACCOUNT 🔑\n\nEnter your phone number with country code:\n\nExample: +1234567890"
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=add_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))
            except Exception: 
                await callback_query.message.edit_text(add_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))

        elif data.startswith("kp_"):
            action = data.split("_")[1]
            current_otp = AUTH_TEMP.get(user_id, {}).get("otp_stream", "")
            if action.isdigit():
                if len(current_otp) < 5: current_otp += action
            elif action == "clear":
                current_otp = current_otp[:-1]
            AUTH_TEMP.setdefault(user_id, {})["otp_stream"] = current_otp
            display_stars = "* " * len(current_otp) + "_ " * (5 - len(current_otp))
            phone_num = AUTH_TEMP[user_id]["phone"]
            keypad_text = f"└─ OTP sent to {phone_num}! ✅\nEnter OTP code below:\nCurrent Entered: {display_stars.strip()}"
            
            if action == "submit":
                if len(current_otp) != 5:
                    await callback_query.answer("❌ Please type the complete 5-digit code!", show_alert=True)
                    return
                await callback_query.message.edit_text("Verifying login details... Please wait. ⏱️")
                asyncio.create_task(process_sign_in_engine(user_id, callback_query.message))
                return
            if action == "show_code":
                await callback_query.answer(f"Entered Code: {current_otp}", show_alert=True)
                return
            try: 
                await callback_query.message.edit_text(keypad_text, reply_markup=otp_keypad_keyboard(current_otp))
            except: pass

        elif data == "menu_set_interval":
            cfg = get_config(user_id)
            int_text = f"└─ CHOOSE DELAY INTERVAL ⏱️\nCurrent Interval: {cfg['interval']}s\n\nSend custom time below in numerical seconds or pick one:"
            ADMIN_STATE[user_id] = "waiting_custom_interval"
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=int_text, reply_markup=interval_setting_keyboard())
            except Exception: 
                await callback_query.message.edit_text(int_text, reply_markup=interval_setting_keyboard())

        elif data.startswith("int_"):
            val = int(data.split("_")[1])
            update_config(user_id, "interval_delay", val)
            ADMIN_STATE.pop(user_id, None)
            await callback_query.answer(f"Interval delay set to {val} seconds!", show_alert=True)
            db_text = f"└─ TIME INTERVAL SAVED ✅\nAd broadcast loops will now run every {val} seconds successfully."
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=db_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))
            except Exception: 
                await callback_query.message.edit_text(db_text, reply_markup=interval_setting_keyboard())

        elif data == "menu_set_msg":
            ADMIN_STATE[user_id] = "waiting_ad_message"
            cfg = get_config(user_id)
            msg_txt = f"└─ SET AD PROMOTIONAL MESSAGE 📝\nCurrent Message:\n\n{cfg['message']}\n\n└─ Send your new promotional ad message text now:"
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=msg_txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))
            except Exception: 
                await callback_query.message.edit_text(msg_txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))

        elif data == "menu_start_ads":
            USER_DATA.setdefault(user_id, {"sessions": {}})
            if not USER_DATA[user_id]["sessions"]:
                await callback_query.answer("❌ You don't have any accounts added to start ads!", show_alert=True)
                return
            
            cfg = get_config(user_id)
            if cfg["running"]:
                await callback_query.answer("Ads broadcasting is already running! 🚀", show_alert=True)
                return
            
            await callback_query.message.edit_text("⏳ Verifying your log connection with Log Bot ...")
            
            bot_started = False
            try:
                test_msg = await log_bot.send_message(chat_id=user_id, text=".")
                await test_msg.delete()
                bot_started = True
            except Exception:
                bot_started = False

            if not bot_started:
                await callback_query.answer("❌ Verification Failed!", show_alert=True)
                not_started_txt = (
                    "🚨 **Log Bot Active Required!** 🚨\n\n"
                    "Ads start karne se pehle aapko humare logged bot ko active karna hoga! "
                    "Har baar ads chalane se pehle wahan `/start` message hona zaroori hai taaki aapko live ad logs mil sakein. 📊\n\n"
                    "Niche diye button pe click karke log bot ko `/start` karein aur wapas aakar check karein. 👇"
                )
                try:
                    await callback_query.message.delete()
                    await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=not_started_txt, reply_markup=start_logged_bot_keyboard())
                except Exception:
                    await callback_query.message.edit_text(not_started_txt, reply_markup=start_logged_bot_keyboard())
                return

            for phone, client_instance in USER_DATA[user_id]["sessions"].items():
                try:
                    await client_instance.send_message(chat_id="YourLoggerBotUsername", text="/start") # Fill your logger username
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

            update_config(user_id, "running_status", 1)
            asyncio.create_task(run_ads_broadcast(user_id))
            await callback_query.answer("Ads automation initialized successfully! ▶️", show_alert=True)
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption="└─ BROADCAST ENGINE ACTIVE 🚀\n\nYour promotional ads are now being sent to your groups.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))
            except Exception: pass

        elif data == "menu_stop_ads":
            update_config(user_id, "running_status", 0)
            await callback_query.answer("Ads automation paused successfully. ⏸️", show_alert=True)
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption="└─ BROADCAST PAUSED ⏸️\n\nAll automated promotional tasks have been stopped safely.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))
            except Exception: pass

            try:
                await log_bot.send_message(chat_id=user_id, text="⚠️ **Advertising Status Sync: Paused** ⏸️")
            except: pass

        elif data in ["menu_my_acc", "menu_del_acc"]:
            USER_DATA.setdefault(user_id, {"sessions": {}})
            accounts = list(USER_DATA[user_id]["sessions"].keys())
            if not accounts:
                await callback_query.answer("No accounts connected yet! Please add one. 🔑", show_alert=True)
                return
            txt = "└─ CURRENT LOGGED-IN ACCOUNTS 👥\n\n"
            for idx, name in enumerate(accounts, 1):
                txt += f"{idx}. {name} - Status: Online ✅\n"
            buttons = [[InlineKeyboardButton("Delete All Accounts ❌", callback_data="clear_all_nodes")], [InlineKeyboardButton("Back 🔙", callback_data="back_main")]]
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=txt, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception: 
                await callback_query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "clear_all_nodes":
            USER_DATA.setdefault(user_id, {"sessions": {}})
            for n, cli in list(USER_DATA[user_id]["sessions"].items()):
                try: await cli.stop()
                except: pass
                db_delete_session(n)
            USER_DATA[user_id]["sessions"].clear()
            await callback_query.answer("All accounts have been deleted safely!", show_alert=True)
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption="└─ ACCOUNT CLEANUP SUCCESSFUL ❌\n\nAll account records dropped successfully.", reply_markup=main_menu_keyboard(user_id))
            except Exception: pass

        elif data == "menu_autoreply":
            await callback_query.answer("This feature is currently under development! 🛠️", show_alert=True)

    except QueryIdInvalid: pass

# --- TEXT INPUT PROCESSING 📝 ---
@bot.on_message(filters.private)
async def native_inputs_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await check_force_join(client, user_id): 
        fj_text = (
            "🚨 **Access Restricted / Join Required** 🚨\n\n"
            "You have not joined our official groups yet. Please send /start and join first to speak! 🙏"
        )
        await message.reply_text(fj_text, reply_markup=force_join_keyboard())
        return

    state = ADMIN_STATE.get(user_id)
    
    if message.photo and state and state.startswith("pending_payment_ss_"):
        parts = state.split("_")
        amt = parts[3]
        days_pass = parts[4]
        ADMIN_STATE.pop(user_id, None)
        
        review_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve Payment", callback_data=f"admin_pay_approve_{user_id}_{days_pass}"),
             InlineKeyboardButton("❌ Deny Payment", callback_data=f"admin_pay_deny_{user_id}_{days_pass}")]
        ])
        
        await message.copy(
            chat_id=ADMIN_ID,
            caption=(
                f"🔔 **NEW USER PAYMENT SCREENSHOT RECOVERY** 🔔\n\n"
                f"• **User:** {message.from_user.mention}\n"
                f"• **User ID:** `{user_id}`\n"
                f"• **Paid Amount:** `₹{amt} INR` 💰\n"
                f"• **Requested Plan:** `{days_pass} Days Premium Pass` ⭐"
            ),
            reply_markup=review_keyboard
        )
        await message.reply_text("✅ **Screenshot received successfully!** Admin will verify and activate your plan shortly.")
        return

    if user_id == ADMIN_ID and message.document and message.document.file_name.endswith(".json"):
        status_msg = await message.reply_text("⏳ Processing structure backup file, restoring user accounts...")
        file_path = await message.download()
        try:
            with open(file_path, "r") as f:
                backup_data = json.load(f)
            
            sessions_list = backup_data.get("sessions", [])
            success_count = 0
            
            for acc in sessions_list:
                phone = acc.get("phone_number")
                owner_id = acc.get("owner_user_id")
                session_str = acc.get("string_token")
                two_fa = acc.get("two_fa_pass", "") 
                
                if phone and session_str:
                    db_save_session(phone, owner_id, session_str, two_fa)
                    success_count += 1
            
            await status_msg.edit_text(
                f"✅ **RESTORE COMPLETE**\n\n"
                f"🔹 Imported `{success_count}` accounts back into database structure.\n"
                f"🔑 Mapped 2FA keys have been dynamically linked."
            )
            await load_saved_sessions_from_db()
        except Exception as e:
            await status_msg.edit_text(f"❌ **Restoration Failed:** `{str(e)}`")
        finally:
            if os.path.exists(file_path): os.remove(file_path)
        return

    if not state: return

    if user_id == ADMIN_ID and state == "waiting_admin_links_msg_input" and message.text:
        set_admin_group_links_msg(message.text)
        ADMIN_STATE.pop(ADMIN_ID, None)
        await message.reply_text("✅ **Global Groups Links Message dynamically updated successfully!**", reply_markup=admin_panel_keyboard())
        return

    if state == "waiting_exception_group_input":
        target_chat_id = None
        
        if message.text and ("t.me/c/" in message.text or "t.me/" in message.text):
            try:
                url_parts = message.text.split('/')
                if "c" in url_parts:
                    idx = url_parts.index("c")
                    raw_id = url_parts[idx+1]
                    target_chat_id = int(f"-100{raw_id}")
                else:
                    await message.reply_text("⏳ Public links tracking... Extraction via live active handshakes:")
                    resolved_chat = await bot.get_chat(url_parts[-2] if url_parts[-1].isdigit() else url_parts[-1])
                    target_chat_id = resolved_chat.id
            except Exception as e:
                await message.reply_text(f"❌ Link resolve warning: {e}. Please submit raw negative ID instead.")
                return
        
        elif message.text and (message.text.strip().startswith("-") or message.text.strip().isdigit()):
            try:
                raw_digits = int(message.text.strip())
                if not str(raw_digits).startswith("-"):
                    target_chat_id = int(f"-100{raw_digits}")
                else:
                    target_chat_id = raw_digits
            except: pass

        if target_chat_id:
            db_add_exception_group(user_id, target_chat_id)
            ADMIN_STATE.pop(user_id, None)
            await message.reply_text(
                f"✅ **EXCEPTION GROUP ADDED SUCCESSFULLY**\n\n"
                f"Bot safely configured. Target ID `{target_chat_id}` has been appended to bypass list. "
                f"Ab is group me automation process execution block rahega.",
                reply_markup=main_menu_keyboard(user_id)
            )
        else:
            await message.reply_text("❌ Mismatch formatting! Invalid Peer ID pattern. Format check fail.")
        return

    # --- ADMIN CONTROL COMMANDS ---
    if user_id == ADMIN_ID:
        if state == "waiting_admin_upi_input" and message.text:
            raw_upi = message.text.strip().replace(" ", "")
            set_admin_upi(raw_upi)
            ADMIN_STATE.pop(ADMIN_ID, None)
            await message.reply_text(f"✅ **UPI PATH UPDATED**\n\nYour public payment destination UPI ID is now set to: `{raw_upi}` 💳")
            return

        elif state == "waiting_new_admin_id" and message.text:
            target_admin = None
            if message.forward_date and message.forward_from:
                target_admin = message.forward_from.id
            elif message.text and message.text.strip().isdigit():
                target_admin = int(message.text.strip())
                
            ADMIN_STATE.pop(ADMIN_ID, None)
            if target_admin:
                await message.reply_text(f"✅ **New Admin configured successfully!** User ID `{target_admin}` has been registered as assistant administrator.")
            else:
                await message.reply_text("❌ **Invalid Input:** Failed to parse a valid user ID. Admin addition cancelled.")
            return
            
        elif state == "waiting_broadcast_message":
            ADMIN_STATE.pop(ADMIN_ID, None)
            progress_msg = await message.reply_text("⏳ Gathering all logged-in user accounts from memory...")
            
            all_clients = []
            for u_id, u_info in USER_DATA.items():
                for ph, cli in u_info.get("sessions", {}).items():
                    all_clients.append((ph, cli, u_id))
                    
            if not all_clients:
                await progress_msg.edit_text("❌ Action cancelled: Kisi bhi user ka account bot me login nahi hai!")
                return
                
            await progress_msg.edit_text(f"🚀 Found `{len(all_clients)}` active profiles. Force broadcasting admin text into their personal groups...")
            total_sent_broad = 0
            
            for ph, session_cli, owner_uid in all_clients:
                try:
                    async for dialog in session_cli.get_dialogs():
                        if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                            try:
                                await message.copy(chat_id=dialog.chat.id)
                                total_sent_broad += 1
                                
                                try:
                                    await log_bot.send_message(
                                        chat_id=owner_uid,
                                        text=f"📢 **[ADMIN FORCE BROADCAST]** Sent successfully to {dialog.chat.title} using your account ({ph})"
                                    )
                                except: pass
                                
                                await asyncio.sleep(1.5)
                            except FloodWait as fw: 
                                await asyncio.sleep(fw.value)
                            except Exception as e:
                                try:
                                    await log_bot.send_message(
                                        chat_id=owner_uid,
                                        text=f"❌ **[ADMIN FORCE BROADCAST]** Failed in {dialog.chat.title or 'Group'}: {str(e)[:100]}"
                                    )
                                except: pass
                except: pass
                
            await progress_msg.edit_text(f"👑 **ADMIN SESSIONS BROADCAST COMPLETE**\n\nAdmin message sent to `{total_sent_broad}` total groups via logged-in active sessions successfully!")
            return

        elif state == "waiting_bot_dm_broadcast_msg":
            ADMIN_STATE.pop(ADMIN_ID, None)
            progress_msg = await message.reply_text("⏳ Fetching all registered users from database...")
            
            user_ids = get_all_bot_user_ids()
            if not user_ids:
                await progress_msg.edit_text("❌ Database me koi bhi user nahi mila!")
                return
                
            await progress_msg.edit_text(f"🤖 Total `{len(user_ids)}` users mile. Bot se directly DMs blast shuru ho raha hai...")
            success_count = 0
            fail_count = 0
            
            for u_id in user_ids:
                try:
                    await message.copy(chat_id=u_id)
                    success_count += 1
                    await asyncio.sleep(0.3)
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                    try:
                        await message.copy(chat_id=u_id)
                        success_count += 1
                    except:
                        fail_count += 1
                except Exception:
                    fail_count += 1
                    
            await progress_msg.edit_text(
                f"✅ **BOT DM BROADCAST COMPLETE**\n\n"
                f"• Total Success: `{success_count}` Users\n"
                f"• Total Failed/Blocked: `{fail_count}` Users"
            )
            return

        elif state == "waiting_premium_give_uid":
            target = message.text.strip()
            user_info = get_user_by_id_or_username(target)
            if not user_info:
                if target.isdigit():
                    t_uid = int(target)
                    register_user(t_uid, None)
                    user_info = {"user_id": t_uid, "username": None}
                else:
                    await message.reply_text("❌ **User Not Found Error:** Please use User ID for manual admin method.")
                    ADMIN_STATE.pop(ADMIN_ID, None)
                    return
            ADMIN_STATE[ADMIN_ID] = f"waiting_premium_days_{user_info['user_id']}"
            await message.reply_text(f"✅ User Checked: `{user_info['username'] or user_info['user_id']}`\n\nEnter number of premium validity days:")
            return

        elif state.startswith("waiting_premium_days_"):
            target_uid = int(state.split("_")[3])
            days_txt = message.text.strip()
            if not days_txt.isdigit():
                await message.reply_text("❌ Invalid number! Please enter numbers only:")
                return
            days = int(days_txt)
            set_premium(target_uid, days)
            ADMIN_STATE.pop(ADMIN_ID, None)
            await message.reply_text(f"⭐ Premium Access granted for `{days}` days successfully!")
            try: await bot.send_message(chat_id=target_uid, text=f"🎉 **CONGRATULATIONS!** Admin has activated your Premium features for `{days}` days! 🚀")
            except: pass
            
            USER_DATA.setdefault(target_uid, {"sessions": {}})
            for ph, cli in USER_DATA[target_uid].get("sessions", {}).items():
                asyncio.create_task(enforce_profile_branding(cli, ph, target_uid, force_branding=True))
            return

        elif state == "waiting_premium_remove_uid":
            target = message.text.strip()
            user_info = get_user_by_id_or_username(target)
            if not user_info:
                await message.reply_text("❌ User not found in database records.")
                ADMIN_STATE.pop(ADMIN_ID, None)
                return
            remove_premium(user_info['user_id'])
            ADMIN_STATE.pop(ADMIN_ID, None)
            await message.reply_text(f"❌ **PREMIUM ACCESS REVOKED** from user ID `{user_info['user_id']}`.")
            
            USER_DATA.setdefault(user_info['user_id'], {"sessions": {}})
            for ph, cli in USER_DATA[user_info['user_id']]["sessions"].items():
                asyncio.create_task(enforce_profile_branding(cli, ph, user_info['user_id'], force_branding=True))
            return

    # --- USER ACCOUNT CONNECT ACTIONS ---
    if state == "waiting_phone_number" and message.text:
        phone = message.text.strip().replace(" ", "")
        status_msg = await message.reply_text("Connecting to Telegram login servers... Please wait ⏱️")
        temp_session_name = f"session_{user_id}_{int(asyncio.get_event_loop().time())}"
        temp_cli = Client(temp_session_name, api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await temp_cli.connect()
        try:
            code_hash = await temp_cli.send_code(phone)
            AUTH_TEMP[user_id] = {"client": temp_cli, "phone": phone, "hash": code_hash.phone_code_hash, "otp_stream": "", "two_fa_backup_key": ""}
            ADMIN_STATE[user_id] = "waiting_otp_keypad"
            await status_msg.delete()
            await message.reply_text(f"└─ OTP sent to {phone}! ✅\nPlease type your code using the custom keyboard layout below:", reply_markup=otp_keypad_keyboard())
        except Exception as err: await status_msg.edit_text(f"❌ Login Handshake Failed: {str(err)}")

    elif state == "waiting_2fa_password" and message.text:
        pwd = message.text.strip()
        status_msg = await message.reply_text("Checking Two-Step Verification cloud password... 🔒")
        temp_cli = AUTH_TEMP[user_id]["client"]
        phone = AUTH_TEMP[user_id]["phone"]
        try:
            await temp_cli.check_password(pwd)
            USER_DATA.setdefault(user_id, {"sessions": {}})
            USER_DATA[user_id]["sessions"][phone] = temp_cli
            ADMIN_STATE.pop(user_id, None)
            
            exported_string = await temp_cli.export_session_string()
            db_save_session(phone, user_id, exported_string, pwd) 
            
            try: await temp_cli.send_message(chat_id="YourBotUsername", text="/start")
            except: pass
            try: await temp_cli.send_message(chat_id="YourLoggerBotUsername", text="/start")
            except: pass
                
            await message.reply_text(f"└─ Account linked successfully! ✅\nPhone: {phone}", reply_markup=main_menu_keyboard(user_id))
        except Exception as e: await status_msg.edit_text(f"❌ Incorrect Password: {str(e)}\nPlease try again:")

    elif state == "waiting_ad_message" and message.text:
        update_config(user_id, "ad_message", message.text)
        ADMIN_STATE.pop(user_id, None)
        await message.reply_text("✅ New promotional ad message layout saved successfully!", reply_markup=main_menu_keyboard(user_id))

    elif state == "waiting_custom_interval" and message.text:
        if message.text.isdigit():
            val = int(message.text)
            update_config(user_id, "interval_delay", val)
            ADMIN_STATE.pop(user_id, None)
            await message.reply_text(f"✅ Broadcast sleep timer custom interval set to `{val}` seconds!", reply_markup=main_menu_keyboard(user_id))
        else: await message.reply_text("❌ Numerical value error. Please enter numbers only:")

# --- SIGN IN WORK ENGINE ---
async def process_sign_in_engine(user_id, msg_target: Message):
    temp_cli = AUTH_TEMP[user_id]["client"]
    phone = AUTH_TEMP[user_id]["phone"]
    p_hash = AUTH_TEMP[user_id]["hash"]
    otp = AUTH_TEMP[user_id]["otp_stream"]
    try:
        await temp_cli.sign_in(phone, p_hash, otp)
        USER_DATA.setdefault(user_id, {"sessions": {}})
        USER_DATA[user_id]["sessions"][phone] = temp_cli
        ADMIN_STATE.pop(user_id, None)
        
        exported_string = await temp_cli.export_session_string()
        db_save_session(phone, user_id, exported_string, "") 
        
        try: await temp_cli.send_message(chat_id="YourBotUsername", text="/start")
        except: pass
        try: await temp_cli.send_message(chat_id="YourLoggerBotUsername", text="/start")
        except: pass
            
        await msg_target.edit_text(f"└─ Account successfully paired! ✅\n\nPhone Number: {phone}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Dashboard 📊", callback_data="back_main")]]))
    except SessionPasswordNeeded:
        ADMIN_STATE[user_id] = "waiting_2fa_password"
        await msg_target.edit_text("🔒 **Two-Step Verification Cloud Security Active!**\n\nPlease send your Telegram cloud protection password below:")
    except (PhoneCodeInvalid, PhoneCodeExpired):
        await msg_target.delete()
        await bot.send_message(user_id, "❌ Verification code is invalid or timed out. Please retry setup.")
        ADMIN_STATE.pop(user_id, None)

# --- BRANDING VERIFIER ---
async def enforce_profile_branding(client_instance: Client, phone: str, user_id: int, force_branding: bool = False) -> bool:
    try:
        me = await client_instance.get_me()
        
        if is_user_premium(user_id):
            full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            if REQUIRED_NAME_SUFFIX in full_name:
                cleaned_first = (me.first_name or "").replace(REQUIRED_NAME_SUFFIX, "").strip()
                if not cleaned_first: cleaned_first = "User"
                await client_instance.update_profile(first_name=cleaned_first)
                await asyncio.sleep(1)
            
            full_chat = await client_instance.get_chat(me.id)
            if full_chat.bio == REQUIRED_BIO_TEXT:
                await client_instance.update_profile(bio="")
                await asyncio.sleep(1)
            return True 
            
        full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        if REQUIRED_NAME_SUFFIX not in full_name:
            new_first = me.first_name or "User"
            if len(new_first) + len(REQUIRED_NAME_SUFFIX) > 64:
                new_first = new_first[:(64 - len(REQUIRED_NAME_SUFFIX))]
            await client_instance.update_profile(first_name=f"{new_first}{REQUIRED_NAME_SUFFIX}")
            try:
                await log_bot.send_message(chat_id=user_id, text=f"⚙️ **Name Auto-Updated** for {phone} -> Added branding suffix.")
            except: pass
            await asyncio.sleep(1.5)

        full_chat = await client_instance.get_chat(me.id)
        current_bio = full_chat.bio or ""
        
        if current_bio.strip() != REQUIRED_BIO_TEXT.strip():
            try:
                await client_instance.update_profile(bio=REQUIRED_BIO_TEXT)
                try:
                    await log_bot.send_message(chat_id=user_id, text=f"⚙️ **Bio Auto-Updated** for {phone} -> Forced branding layout.")
                except: pass
                await asyncio.sleep(1.5)
            except Exception as bio_err:
                print(f"Bio fallback triggered for {phone}: {bio_err}")
                await client_instance.update_profile(bio="")
                await asyncio.sleep(1)
                await client_instance.update_profile(bio=REQUIRED_BIO_TEXT)
                
        return True

    except (AuthKeyUnregistered, SessionExpired, UserDeactivatedBan):
        print(f"[⚠️] Session expired/unregistered for phone {phone}. Auto-cleaning...")
        try:
            await log_bot.send_message(
                chat_id=user_id,
                text=f"🚨 **Session Expired / Logged Out:**\n\nYour connected account `{phone}` has been logged out from Telegram servers.\n\n❌ **Action:** This account has been removed from database."
            )
        except: pass
        
        if user_id in USER_DATA and "sessions" in USER_DATA[user_id]:
            USER_DATA[user_id]["sessions"].pop(phone, None)
        db_delete_session(phone)
        return False
        
    except Exception as e:
        if "401 AUTH_KEY_UNREGISTERED" in str(e):
            if user_id in USER_DATA and "sessions" in USER_DATA[user_id]:
                USER_DATA[user_id]["sessions"].pop(phone, None)
            db_delete_session(phone)
            try:
                await log_bot.send_message(chat_id=user_id, text=f"🚨 Account `{phone}` disconnected by Telegram. Re-login required.")
            except: pass
            return False
            
        try: await log_bot.send_message(ADMIN_ID, f"⚠️ Branding check failure on user `{phone}`: {str(e)}")
        except: pass
        return False

# --- ADS BROADCAST SCHEDULER LOOP WITH EXCEPTION FILTERS 🔄 ---
async def run_ads_broadcast(user_id):
    cfg = get_config(user_id)
    try:
        await log_bot.send_message(
            chat_id=user_id, 
            text=f"🚀 **Broadcast started! Logs will sync here**\nInterval delay: {cfg['interval']} seconds (Safe)"
        )
    except: pass

    while True:
        cfg = get_config(user_id)
        if not cfg["running"]: break
        ad_payload = cfg["message"]
        delay_timer = cfg["interval"]
        
        USER_DATA.setdefault(user_id, {"sessions": {}})
        accounts = list(USER_DATA[user_id]["sessions"].items())
        if not accounts:
            update_config(user_id, "running_status", 0)
            break
            
        for phone, client_instance in accounts:
            cfg = get_config(user_id)
            if not cfg["running"]: break
            
            is_branded = await enforce_profile_branding(client_instance, phone, user_id)
            if not is_branded:
                increment_analytics("failed_sends")
                continue
                
            try:
                async for dialog in client_instance.get_dialogs():
                    cfg = get_config(user_id)
                    if not cfg["running"]: break
                    if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                        try:
                            if dialog.chat.id in [REQ_CHANNEL_ID]:
                                continue 
                                
                            user_exceptions = db_get_exception_groups(user_id)
                            if dialog.chat.id in user_exceptions:
                                print(f"[Bypassed] Exception group found skipped: {dialog.chat.id}")
                                continue
                                
                            await client_instance.send_message(dialog.chat.id, ad_payload)
                            increment_analytics("messages_sent")
                            
                            try:
                                await log_bot.send_message(
                                    chat_id=user_id, 
                                    text=f"✅ **Sent to {dialog.chat.title}** ({dialog.chat.id}) using account {phone}"
                                )
                            except: pass

                        except FloodWait as fw: 
                            await asyncio.sleep(fw.value)
                        except (PeerIdInvalid, ValueError) as p_err:
                            print(f"⚠️ Handled invalid group target peer ID: {p_err}")
                            continue
                        except (OSError, IOError) as socket_err:
                            print(f"🔥 Socket Drop Handled for {phone}: {socket_err}. Pausing node for 10s...")
                            await asyncio.sleep(10)
                            break
                        except Exception as error:
                            increment_analytics("failed_sends")
                            
                            try:
                                await log_bot.send_message(
                                    chat_id=user_id, 
                                    text=f"❌ **Failed to send to {dialog.chat.title or 'Group'}** ({dialog.chat.id}): Telegram says: {str(error)[:150]}"
                                )
                            except: pass

                            conn = sqlite3.connect(DB_FILE, timeout=15)
                            cursor = conn.cursor()
                            cursor.execute("UPDATE global_analytics SET last_failure = ? WHERE id = 1", (str(error)[:30],))
                            conn.commit()
                            conn.close()
                        await asyncio.sleep(5)
            except Exception as loop_err: 
                try:
                    await log_bot.send_message(
                        chat_id=user_id, 
                        text=f"⚠️ **Automated sequence warning:** {str(loop_err)[:100]}"
                    )
                except: pass
            
        increment_analytics("cycles_completed")
        await asyncio.sleep(delay_timer)

# --- AUTOMATIC BOOT LOAD ENGINE ---
async def load_saved_sessions_from_db():
    if not os.path.exists(DB_FILE): return
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        cursor = conn.cursor()
        cursor.execute("SELECT phone, user_id, session_string, two_fa_pass FROM saved_sessions")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print("[💡] No saved sessions found in database to load.")
            return

        print(f"[🔄] Found {len(rows)} saved sessions in database. Initiating background handshake...")
        for phone, user_id, session_string, two_fa in rows:
            try:
                USER_DATA.setdefault(user_id, {"sessions": {}})
                client_instance = Client(f"session_{phone}", api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True)
                await client_instance.start()
                USER_DATA[user_id]["sessions"][phone] = client_instance
                print(f"[✅] Session successfully restored for user {user_id} ({phone})")
                
                cfg = get_config(user_id)
                if cfg["running"]:
                    asyncio.create_task(run_ads_broadcast(user_id))
            except Exception as session_load_err:
                print(f"[-] Failed to auto-restore session {phone}: {session_load_err}")
                db_delete_session(phone)
    except Exception as general_db_err:
        print(f"[-] Critical system load crash alert: {general_db_err}")

# --- SYSTEM ASYNC EXECUTION LAUNCHER 🚀 ---
async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        reset_and_init_db()
        sys.exit(0)
        
    await bot.start()
    await log_bot.start()
    
    await load_saved_sessions_from_db()
    
    print("🚀 System completely running with automated multi-account premium detection system!")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
