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
import time
import logging
import threading
from contextlib import closing
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.handlers import MessageHandler
from dotenv import load_dotenv
try:
    import psutil
except ImportError:
    psutil = None
from pyrogram.errors import FloodWait, QueryIdInvalid, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, UserNotParticipant, PeerIdInvalid, AuthKeyUnregistered, SessionExpired, UserDeactivatedBan

# --- SECURE CONFIGURATION ---
load_dotenv()
def env_required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}. Configure it in .env")
    return value

API_ID = int(env_required("API_ID"))
API_HASH = env_required("API_HASH")
MAIN_BOT_TOKEN = env_required("MAIN_BOT_TOKEN")
LOG_BOT_TOKEN = env_required("LOG_BOT_TOKEN")
ADMIN_ID = int(env_required("ADMIN_ID"))

# --- TELEGRAM MEDIA IMAGE LINK 🖼️ ---
MEDIA_IMAGE_LINK = "https://t.me/metahelpline/25"

# --- BRANDING REQUIREMENTS 🏷️ ---
REQUIRED_NAME_SUFFIX = os.getenv("REQUIRED_NAME_SUFFIX", " #ads_via @AirsAdsBot")
REQUIRED_BIO_TEXT = os.getenv("REQUIRED_BIO_TEXT", "best bot for ads @AirsAdsBot")

# --- FORCE JOIN CONFIGURATION (ONLY 1 CHANNEL & 1 GROUP) 📢 ---
REQ_CHANNEL_ID = -1003854591860
REQ_CHANNEL_LINK = "https://t.me/sexders"

REQ_GROUP_ID = -1003900909493  
REQ_GROUP_LINK = "https://t.me/xRichOtc"

# Support Group (Not Forced, Only for Buttons) 🛠️
SUPPORT_GROUP_LINK = "https://t.me/+kVLKi--EhXI5NDRl"


# --- INITIALIZATION 🚀 ---
bot = Client("MainBotEngine", api_id=API_ID, api_hash=API_HASH, bot_token=MAIN_BOT_TOKEN, parse_mode=enums.ParseMode.HTML)
log_bot = Client("LogBotEngine", api_id=API_ID, api_hash=API_HASH, bot_token=LOG_BOT_TOKEN, parse_mode=enums.ParseMode.HTML)

# --- DATABASE ENGINE 🗄️ ---
DB_FILE = "bot_automation_core.db"  # Database name changed successfully

def backup_database():
    """Create a consistent SQLite backup without modifying the live database."""
    if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) == 0:
        return None
    os.makedirs("backups", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join("backups", f"bot_db_{stamp}.sqlite3")
    src = sqlite3.connect(DB_FILE, timeout=30)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target

def reset_and_init_db():
    """Initialize or migrate schema. Never removes an existing database or user data."""
    conn = sqlite3.connect(DB_FILE, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("""CREATE TABLE IF NOT EXISTS global_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cycles_completed INTEGER DEFAULT 0,
            messages_sent INTEGER DEFAULT 0, failed_sends INTEGER DEFAULT 0,
            logger_failures INTEGER DEFAULT 0, last_failure TEXT DEFAULT 'None')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS bot_config (
            user_id INTEGER PRIMARY KEY, ad_message TEXT DEFAULT 'Hello from Ads Automation Framework!',
            running_status INTEGER DEFAULT 0, interval_delay INTEGER DEFAULT 300,
            operation_mode TEXT DEFAULT 'Aggressive')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT DEFAULT NULL,
            is_premium INTEGER DEFAULT 0, premium_expiry TEXT DEFAULT NULL)""")
        cur.execute("CREATE TABLE IF NOT EXISTS admin_settings (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute("""CREATE TABLE IF NOT EXISTS terms_acceptances (
            user_id INTEGER PRIMARY KEY,
            terms_version TEXT NOT NULL,
            accepted_at TEXT NOT NULL
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS user_languages (
            user_id INTEGER PRIMARY KEY,
            language TEXT NOT NULL DEFAULT 'en'
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS saved_sessions (
            phone TEXT PRIMARY KEY, user_id INTEGER, session_string TEXT,
            two_fa_pass TEXT DEFAULT '')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS exception_groups (
            user_id INTEGER, chat_id INTEGER, PRIMARY KEY (user_id, chat_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS broadcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT,
            chat_id INTEGER, chat_title TEXT, status TEXT NOT NULL,
            detail TEXT DEFAULT '', created_at TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY, autoreply_enabled INTEGER DEFAULT 0,
            autoreply_message TEXT DEFAULT 'Thanks for your message! I will get back to you soon.',
            autoreply_cooldown INTEGER DEFAULT 60, branding_enabled INTEGER DEFAULT 1,
            custom_profile_name TEXT DEFAULT '', custom_profile_bio TEXT DEFAULT '')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS autoreply_tracking (
            user_id INTEGER NOT NULL, sender_id INTEGER NOT NULL, last_reply REAL NOT NULL,
            PRIMARY KEY(user_id, sender_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)""")
        cur.execute("INSERT OR IGNORE INTO global_analytics (id, cycles_completed, messages_sent, failed_sends, logger_failures, last_failure) VALUES (1,0,0,0,0,'None')")
        cur.execute("INSERT OR IGNORE INTO admin_settings(key,value) VALUES('maintenance_mode','0')")
        cur.execute("INSERT OR IGNORE INTO admin_settings(key,value) VALUES('branding_enabled','1')")
        cur.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(1,?)",
                    (datetime.now().isoformat(timespec="seconds"),))
        # Add columns to older databases only when absent.
        for table, column, declaration in [
            ("saved_sessions","two_fa_pass","TEXT DEFAULT ''"),
            ("bot_config","user_id","INTEGER"),
        ]:
            cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            if column not in cols:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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

if os.path.exists(DB_FILE):
    backup_database()
reset_and_init_db()

def get_setting(key, default=None):
    conn=sqlite3.connect(DB_FILE, timeout=15)
    row=conn.execute("SELECT value FROM admin_settings WHERE key=?",(key,)).fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn=sqlite3.connect(DB_FILE, timeout=15)
    conn.execute("INSERT INTO admin_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))
    conn.commit(); conn.close()

def record_broadcast(user_id, phone, chat_id, title, status, detail=""):
    conn=sqlite3.connect(DB_FILE, timeout=15)
    conn.execute("INSERT INTO broadcast_history(user_id,phone,chat_id,chat_title,status,detail,created_at) VALUES(?,?,?,?,?,?,?)",
                 (user_id,phone,chat_id,title,status,detail[:500],datetime.now().isoformat(timespec="seconds")))
    conn.commit(); conn.close()

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
    # Never persist Telegram 2FA passwords. The column remains for legacy DB compatibility.
    cursor.execute("INSERT OR REPLACE INTO saved_sessions (phone, user_id, session_string, two_fa_pass) VALUES (?, ?, ?, '')", (phone, user_id, session_string))
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
    return row[0] if row else "⚠️ The administrator has not configured any official group links yet."

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

async def safe_edit_text(message, *args, **kwargs):
    """Edit a message; treat Telegram MESSAGE_NOT_MODIFIED as a harmless no-op."""
    try:
        return await message.edit_text(*args, **kwargs)
    except Exception as exc:
        error_id = getattr(exc, "ID", "") or getattr(exc, "MESSAGE", "")
        if error_id == "MESSAGE_NOT_MODIFIED" or "MESSAGE_NOT_MODIFIED" in str(exc):
            return message
        raise


async def safe_edit_caption(message, *args, **kwargs):
    """Edit a media caption; ignore only the harmless unchanged-content response."""
    try:
        return await message.edit_caption(*args, **kwargs)
    except Exception as exc:
        error_id = getattr(exc, "ID", "") or getattr(exc, "MESSAGE", "")
        if error_id == "MESSAGE_NOT_MODIFIED" or "MESSAGE_NOT_MODIFIED" in str(exc):
            return message
        raise


# --- STORAGE ---
USER_DATA = {}
ADMIN_STATE = {}
AUTH_TEMP = {}
ACTIVE_TASKS = {}  # task_name -> asyncio.Event; cooperative cancellation

# --- MULTILINGUAL LANGUAGE + TERMS FLOW ---
TERMS_VERSION = "1.0"
LANGUAGES = {
    "en": "🇬🇧 English", "ru": "🇷🇺 Русский", "fa": "🇮🇷 فارسی",
    "zh": "🇨🇳 中文", "es": "🇪🇸 Español", "fr": "🇫🇷 Français",
    "ar": "🇸🇦 العربية", "pt": "🇵🇹 Português", "id": "🇮🇩 Bahasa Indonesia",
    "hi": "🇮🇳 हिन्दी",
}

# User-facing text for the onboarding flow. English is the default.
I18N = {
"en": {
 "choose":"🌐 <b>Choose Your Language</b>\nSelect the language you want to use in the bot.",
 "terms":"📜 <b>TERMS & CONDITIONS</b>\n━━━━━━━━━━━━━━━━━━━━\nPlease read and accept these rules before joining the required communities.\n\n<b>1. Lawful Use</b>\nUse this bot only for lawful advertising and legitimate account management. Do not promote illegal products, scams, fraud, phishing, malware, or misleading offers.\n\n<b>2. No Spam or Unwanted Messages</b>\nOnly post in groups/channels where you have permission and where promotions are allowed. Do not send unsolicited, repetitive, or nuisance messages. Follow each community's rules and Telegram's limits.\n\n<b>3. Respect and Privacy</b>\nDo not harass users, share private information without permission, or impersonate others. Connect only accounts you control, and never share your OTP, password, or session string.\n\n<b>4. Your Responsibility</b>\nYou are responsible for your content, accounts, and where you send messages. Make sure you have the right to use every account and piece of content.\n\n<b>5. Service Availability</b>\nThe bot is provided as-is. Features may change or become unavailable. Access may be limited or suspended if these rules are violated or the service is misused.\n\n<b>6. Acceptance</b>\nBy tapping <b>Agree & Continue</b>, you confirm that you have read and agree to these terms. If you do not agree, do not use the bot.\n\n<i>Terms version: 1.0</i>",
 "agree":"✅ Agree & Continue", "decline":"❌ I Do Not Agree",
 "declined":"❌ <b>Terms Not Accepted</b>\n\nYou can use this bot only after agreeing to the Terms & Conditions. Send /start to choose a language and review them again.",
 "force":"🔐 <b>COMMUNITY ACCESS REQUIRED</b>\n━━━━━━━━━━━━━━━━━━━━\nTerms accepted! Now join our official channel and community group to unlock the dashboard.\n\nAfter joining, tap <b>Verify Membership</b> below.",
 "channel":"📢 Official Channel", "community":"💬 Community", "verify":"✅ Verify Membership",
 "welcome":"✨ <b>WELCOME TO ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\nManage your Telegram ad campaigns from one simple dashboard.\n\n• Multi-account campaign controls\n• Custom broadcast intervals\n• Smart auto-reply settings\n• Live activity statistics\n\nChoose an option below to get started.",
 "change":"🌐 Change Language", "lang_changed":"Language updated. Please review and accept the Terms & Conditions again.",
 "accepted":"✅ Terms accepted. One more step: join the required communities.",
 "join_first":"⚠️ Please join the Channel and Community first!",
 "verified":"✅ Verification successful! Access granted.",
 "verify_fail":"❌ Verification failed: You have not joined both communities yet. Please join first.",
},
"hi": {
 "choose":"🌐 <b>अपनी भाषा चुनें</b>\nबॉट में उपयोग करने के लिए अपनी पसंदीदा भाषा चुनें।",
 "terms":"📜 <b>नियम और शर्तें</b>\n━━━━━━━━━━━━━━━━━━━━\nकृपया आवश्यक कम्युनिटी में शामिल होने से पहले इन नियमों को पढ़ें और स्वीकार करें।\n\n<b>1. कानूनी उपयोग</b>\nइस बॉट का उपयोग केवल वैध विज्ञापन और उचित अकाउंट प्रबंधन के लिए करें। अवैध उत्पाद, धोखाधड़ी, फ़िशिंग, मैलवेयर या भ्रामक ऑफ़र प्रचारित न करें।\n\n<b>2. स्पैम न करें</b>\nकेवल उन्हीं ग्रुप/चैनल में पोस्ट करें जहाँ आपकी अनुमति हो और प्रचार की अनुमति हो। अनचाहे या बार-बार संदेश न भेजें। कम्युनिटी के नियमों और Telegram की सीमाओं का पालन करें।\n\n<b>3. सम्मान और गोपनीयता</b>\nकिसी को परेशान न करें, बिना अनुमति निजी जानकारी साझा न करें और किसी की पहचान न अपनाएँ। केवल अपने अकाउंट कनेक्ट करें। अपना OTP, पासवर्ड या सेशन स्ट्रिंग किसी से साझा न करें।\n\n<b>4. आपकी ज़िम्मेदारी</b>\nअपने कंटेंट, अकाउंट और संदेश भेजने की जगहों के लिए आप स्वयं ज़िम्मेदार हैं।\n\n<b>5. सेवा उपलब्धता</b>\nयह बॉट जैसी स्थिति में उपलब्ध है वैसा ही दिया गया है। नियमों के उल्लंघन या दुरुपयोग पर सुविधा सीमित या बंद की जा सकती है।\n\n<b>6. स्वीकृति</b>\n<b>सहमत हूँ और जारी रखें</b> दबाकर आप इन शर्तों से सहमत होते हैं। असहमत होने पर बॉट का उपयोग न करें।\n\n<i>नियम संस्करण: 1.0</i>",
 "agree":"✅ सहमत हूँ और जारी रखें", "decline":"❌ सहमत नहीं हूँ",
 "declined":"❌ <b>नियम स्वीकार नहीं किए गए</b>\n\nबॉट उपयोग करने के लिए नियम स्वीकार करना आवश्यक है। भाषा चुनने और नियम दोबारा देखने के लिए /start भेजें।",
 "force":"🔐 <b>कम्युनिटी जॉइन करना आवश्यक है</b>\n━━━━━━━━━━━━━━━━━━━━\nनियम स्वीकार हो गए! डैशबोर्ड खोलने के लिए हमारा आधिकारिक चैनल और कम्युनिटी ग्रुप जॉइन करें।\n\nजॉइन करने के बाद नीचे <b>सदस्यता सत्यापित करें</b> दबाएँ।",
 "channel":"📢 आधिकारिक चैनल", "community":"💬 कम्युनिटी", "verify":"✅ सदस्यता सत्यापित करें",
 "welcome":"✨ <b>ADS AUTOMATION में आपका स्वागत है</b>\n━━━━━━━━━━━━━━━━━━━━\nएक आसान डैशबोर्ड से अपने Telegram विज्ञापन कैंपेन मैनेज करें।\n\n• कई अकाउंट का नियंत्रण\n• कस्टम ब्रॉडकास्ट अंतराल\n• स्मार्ट ऑटो-रिप्लाई सेटिंग्स\n• लाइव गतिविधि आँकड़े\n\nशुरू करने के लिए नीचे विकल्प चुनें।",
 "change":"🌐 भाषा बदलें", "lang_changed":"भाषा अपडेट हो गई है। कृपया नियम दोबारा पढ़कर स्वीकार करें।",
 "accepted":"✅ नियम स्वीकार हो गए। अब आवश्यक कम्युनिटी जॉइन करें।",
 "join_first":"⚠️ पहले चैनल और कम्युनिटी जॉइन करें!",
 "verified":"✅ सत्यापन सफल! एक्सेस मिल गया।",
 "verify_fail":"❌ सत्यापन विफल: आपने दोनों कम्युनिटी जॉइन नहीं की हैं। पहले जॉइन करें।",
},
"ru": {
 "choose":"🌐 <b>Выберите язык</b>\nВыберите язык для использования бота.",
 "terms":"📜 <b>УСЛОВИЯ ИСПОЛЬЗОВАНИЯ</b>\n━━━━━━━━━━━━━━━━━━━━\nПрочитайте и примите правила перед вступлением в обязательные сообщества.\n\n<b>1. Законное использование</b>\nИспользуйте бота только для законной рекламы и управления своими аккаунтами. Запрещены незаконные товары, мошенничество, фишинг, вредоносные программы и вводящие в заблуждение предложения.\n\n<b>2. Без спама</b>\nПубликуйте сообщения только в группах и каналах, где у вас есть разрешение и реклама допускается. Не отправляйте нежелательные и повторяющиеся сообщения. Соблюдайте правила сообществ и ограничения Telegram.\n\n<b>3. Уважение и конфиденциальность</b>\nНе преследуйте пользователей, не раскрывайте личные данные без разрешения и не выдавайте себя за других. Подключайте только свои аккаунты и никому не сообщайте OTP, пароль или строку сессии.\n\n<b>4. Ваша ответственность</b>\nВы отвечаете за свой контент, аккаунты и места отправки сообщений.\n\n<b>5. Доступность сервиса</b>\nБот предоставляется «как есть». Функции могут изменяться. Доступ может быть ограничен при нарушении правил или злоупотреблении.\n\n<b>6. Принятие</b>\nНажимая <b>Принять и продолжить</b>, вы соглашаетесь с условиями. Если вы не согласны, не используйте бота.\n\n<i>Версия условий: 1.0</i>",
 "agree":"✅ Принять и продолжить", "decline":"❌ Не согласен",
 "declined":"❌ <b>Условия не приняты</b>\n\nДля использования бота необходимо принять условия. Отправьте /start, чтобы выбрать язык и прочитать их снова.",
 "force":"🔐 <b>ТРЕБУЕТСЯ ВСТУПЛЕНИЕ В СООБЩЕСТВО</b>\n━━━━━━━━━━━━━━━━━━━━\nУсловия приняты! Вступите в официальный канал и группу сообщества, чтобы открыть панель управления.\n\nПосле вступления нажмите <b>Проверить подписку</b>.",
 "channel":"📢 Официальный канал", "community":"💬 Сообщество", "verify":"✅ Проверить подписку",
 "welcome":"✨ <b>ДОБРО ПОЖАЛОВАТЬ В ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\nУправляйте рекламными кампаниями Telegram через единую панель.\n\n• Управление несколькими аккаунтами\n• Настраиваемые интервалы\n• Умные автоответы\n• Статистика активности\n\nВыберите действие ниже.",
 "change":"🌐 Сменить язык", "lang_changed":"Язык изменён. Пожалуйста, снова прочитайте и примите условия.",
 "accepted":"✅ Условия приняты. Теперь вступите в обязательные сообщества.",
 "join_first":"⚠️ Сначала вступите в канал и сообщество!",
 "verified":"✅ Проверка пройдена! Доступ открыт.",
 "verify_fail":"❌ Проверка не пройдена: вы ещё не вступили в оба сообщества.",
},
"fa": {
 "choose":"🌐 <b>زبان خود را انتخاب کنید</b>\nزبان موردنظر برای استفاده از ربات را انتخاب کنید.",
 "terms":"📜 <b>شرایط و قوانین</b>\n━━━━━━━━━━━━━━━━━━━━\nلطفاً پیش از عضویت در انجمن‌های الزامی، این قوانین را بخوانید و بپذیرید.\n\n<b>۱. استفاده قانونی</b>\nاز ربات فقط برای تبلیغات قانونی و مدیریت حساب‌های متعلق به خود استفاده کنید. تبلیغ کالاهای غیرقانونی، کلاهبرداری، فیشینگ، بدافزار یا پیشنهادهای گمراه‌کننده ممنوع است.\n\n<b>۲. بدون هرزنامه</b>\nفقط در گروه‌ها و کانال‌هایی پیام بگذارید که اجازه دارید و تبلیغات مجاز است. پیام ناخواسته یا تکراری ارسال نکنید و قوانین انجمن و محدودیت‌های تلگرام را رعایت کنید.\n\n<b>۳. احترام و حریم خصوصی</b>\nمزاحمت ایجاد نکنید، اطلاعات خصوصی را بدون اجازه منتشر نکنید و هویت دیگران را جعل نکنید. فقط حساب‌های خود را متصل کنید و کد یک‌بارمصرف، گذرواژه یا رشته نشست را با کسی به اشتراک نگذارید.\n\n<b>۴. مسئولیت شما</b>\nمسئولیت محتوا، حساب‌ها و محل ارسال پیام‌ها بر عهده شماست.\n\n<b>۵. دسترس‌پذیری سرویس</b>\nربات به همان شکل موجود ارائه می‌شود. امکانات ممکن است تغییر کنند و در صورت سوءاستفاده دسترسی محدود شود.\n\n<b>۶. پذیرش</b>\nبا انتخاب <b>می‌پذیرم و ادامه می‌دهم</b>، با این شرایط موافقت می‌کنید. در صورت مخالفت از ربات استفاده نکنید.\n\n<i>نسخه شرایط: ۱.۰</i>",
 "agree":"✅ می‌پذیرم و ادامه می‌دهم", "decline":"❌ نمی‌پذیرم",
 "declined":"❌ <b>شرایط پذیرفته نشد</b>\n\nبرای استفاده از ربات باید شرایط را بپذیرید. برای انتخاب زبان و مرور دوباره /start را ارسال کنید.",
 "force":"🔐 <b>عضویت در انجمن الزامی است</b>\n━━━━━━━━━━━━━━━━━━━━\nشرایط پذیرفته شد! برای دسترسی به داشبورد، در کانال رسمی و گروه انجمن عضو شوید.\n\nپس از عضویت، دکمه <b>بررسی عضویت</b> را بزنید.",
 "channel":"📢 کانال رسمی", "community":"💬 انجمن", "verify":"✅ بررسی عضویت",
 "welcome":"✨ <b>به ADS AUTOMATION خوش آمدید</b>\n━━━━━━━━━━━━━━━━━━━━\nکمپین‌های تبلیغاتی تلگرام خود را از یک داشبورد مدیریت کنید.\n\n• کنترل چند حساب\n• فاصله زمانی دلخواه\n• پاسخ‌گوی خودکار هوشمند\n• آمار فعالیت زنده\n\nبرای شروع یکی از گزینه‌های زیر را انتخاب کنید.",
 "change":"🌐 تغییر زبان", "lang_changed":"زبان تغییر کرد. لطفاً شرایط را دوباره بخوانید و بپذیرید.",
 "accepted":"✅ شرایط پذیرفته شد. اکنون در انجمن‌های الزامی عضو شوید.",
 "join_first":"⚠️ ابتدا در کانال و انجمن عضو شوید!",
 "verified":"✅ تأیید انجام شد! دسترسی فعال است.",
 "verify_fail":"❌ تأیید ناموفق بود: هنوز در هر دو انجمن عضو نشده‌اید.",
},
"zh": {
 "choose":"🌐 <b>选择语言</b>\n请选择您希望在机器人中使用的语言。",
 "terms":"📜 <b>条款与条件</b>\n━━━━━━━━━━━━━━━━━━━━\n加入指定社群前，请阅读并接受以下规则。\n\n<b>1. 合法使用</b>\n仅将本机器人用于合法广告和正当账户管理。禁止推广非法商品、诈骗、欺诈、网络钓鱼、恶意软件或误导性内容。\n\n<b>2. 禁止垃圾消息</b>\n仅在您获准发布且允许推广的群组或频道中发帖。不得发送未经请求或重复的消息，并遵守社群规则和 Telegram 限制。\n\n<b>3. 尊重与隐私</b>\n不得骚扰用户、未经许可分享私人信息或冒充他人。仅连接您拥有的账户，切勿分享 OTP、密码或会话字符串。\n\n<b>4. 您的责任</b>\n您需对自己的内容、账户以及消息发送位置负责。\n\n<b>5. 服务可用性</b>\n本机器人按现状提供，功能可能变化或暂停。违反规则或滥用服务可能导致访问受限。\n\n<b>6. 接受条款</b>\n点击<b>同意并继续</b>即表示您已阅读并同意这些条款。若不同意，请勿使用本机器人。\n\n<i>条款版本：1.0</i>",
 "agree":"✅ 同意并继续", "decline":"❌ 不同意",
 "declined":"❌ <b>尚未接受条款</b>\n\n接受条款后才能使用机器人。发送 /start 重新选择语言并查看条款。",
 "force":"🔐 <b>需要加入社群</b>\n━━━━━━━━━━━━━━━━━━━━\n条款已接受！请加入官方频道和社群以解锁控制面板。\n\n加入后点击下方<b>验证成员资格</b>。",
 "channel":"📢 官方频道", "community":"💬 社群", "verify":"✅ 验证成员资格",
 "welcome":"✨ <b>欢迎使用 ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\n通过一个简单的控制面板管理 Telegram 广告活动。\n\n• 多账户管理\n• 自定义发送间隔\n• 智能自动回复\n• 实时活动统计\n\n请选择下方选项开始使用。",
 "change":"🌐 更改语言", "lang_changed":"语言已更新。请重新阅读并接受条款。",
 "accepted":"✅ 条款已接受。请加入指定社群。",
 "join_first":"⚠️ 请先加入频道和社群！",
 "verified":"✅ 验证成功！已获得访问权限。",
 "verify_fail":"❌ 验证失败：您尚未加入两个社群，请先加入。",
},
"es": {
 "choose":"🌐 <b>Elige tu idioma</b>\nSelecciona el idioma que deseas usar en el bot.",
 "terms":"📜 <b>TÉRMINOS Y CONDICIONES</b>\n━━━━━━━━━━━━━━━━━━━━\nLee y acepta estas reglas antes de unirte a las comunidades obligatorias.\n\n<b>1. Uso legal</b>\nUsa este bot solo para publicidad legal y gestión legítima de cuentas. No promociones productos ilegales, estafas, fraude, phishing, malware ni ofertas engañosas.\n\n<b>2. Sin spam</b>\nPublica solo en grupos o canales donde tengas permiso y se permitan promociones. No envíes mensajes no solicitados ni repetitivos. Respeta las reglas de cada comunidad y los límites de Telegram.\n\n<b>3. Respeto y privacidad</b>\nNo acoses a usuarios, compartas información privada sin permiso ni suplantes identidades. Conecta solo cuentas que controles y nunca compartas tu OTP, contraseña o cadena de sesión.\n\n<b>4. Tu responsabilidad</b>\nEres responsable de tu contenido, tus cuentas y los lugares donde envías mensajes.\n\n<b>5. Disponibilidad</b>\nEl bot se ofrece tal cual. Las funciones pueden cambiar o dejar de estar disponibles. El acceso puede limitarse si se incumplen estas reglas.\n\n<b>6. Aceptación</b>\nAl pulsar <b>Aceptar y continuar</b>, confirmas que has leído y aceptas estos términos. Si no estás de acuerdo, no uses el bot.\n\n<i>Versión: 1.0</i>",
 "agree":"✅ Aceptar y continuar", "decline":"❌ No acepto",
 "declined":"❌ <b>Términos no aceptados</b>\n\nDebes aceptar los términos para usar el bot. Envía /start para elegir idioma y revisarlos de nuevo.",
 "force":"🔐 <b>SE REQUIERE UNIRSE A LA COMUNIDAD</b>\n━━━━━━━━━━━━━━━━━━━━\n¡Términos aceptados! Únete al canal oficial y al grupo de la comunidad para desbloquear el panel.\n\nDespués, pulsa <b>Verificar membresía</b>.",
 "channel":"📢 Canal oficial", "community":"💬 Comunidad", "verify":"✅ Verificar membresía",
 "welcome":"✨ <b>BIENVENIDO A ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\nGestiona tus campañas publicitarias de Telegram desde un solo panel.\n\n• Control de varias cuentas\n• Intervalos personalizados\n• Respuestas automáticas inteligentes\n• Estadísticas en directo\n\nElige una opción para comenzar.",
 "change":"🌐 Cambiar idioma", "lang_changed":"Idioma actualizado. Lee y acepta los términos otra vez.",
 "accepted":"✅ Términos aceptados. Ahora únete a las comunidades obligatorias.",
 "join_first":"⚠️ ¡Únete primero al canal y a la comunidad!",
 "verified":"✅ ¡Verificación correcta! Acceso concedido.",
 "verify_fail":"❌ Verificación fallida: aún no te has unido a ambas comunidades.",
},
"fr": {
 "choose":"🌐 <b>Choisissez votre langue</b>\nSélectionnez la langue à utiliser dans le bot.",
 "terms":"📜 <b>CONDITIONS D’UTILISATION</b>\n━━━━━━━━━━━━━━━━━━━━\nVeuillez lire et accepter ces règles avant de rejoindre les communautés requises.\n\n<b>1. Utilisation légale</b>\nUtilisez ce bot uniquement pour la publicité légale et la gestion légitime de comptes. Ne faites pas la promotion de produits illégaux, d’escroqueries, de fraude, d’hameçonnage, de logiciels malveillants ou d’offres trompeuses.\n\n<b>2. Pas de spam</b>\nPubliez uniquement dans les groupes et chaînes où vous avez l’autorisation et où la publicité est permise. N’envoyez pas de messages non sollicités ou répétitifs. Respectez les règles des communautés et les limites de Telegram.\n\n<b>3. Respect et confidentialité</b>\nNe harcelez personne, ne partagez pas d’informations privées sans autorisation et n’usurpez pas d’identité. Connectez uniquement vos propres comptes et ne partagez jamais votre code OTP, mot de passe ou chaîne de session.\n\n<b>4. Votre responsabilité</b>\nVous êtes responsable de votre contenu, de vos comptes et des lieux où vous envoyez des messages.\n\n<b>5. Disponibilité</b>\nLe bot est fourni en l’état. Les fonctionnalités peuvent changer. L’accès peut être limité en cas d’abus ou de non-respect des règles.\n\n<b>6. Acceptation</b>\nEn appuyant sur <b>Accepter et continuer</b>, vous confirmez avoir lu et accepté ces conditions. Si vous n’êtes pas d’accord, n’utilisez pas le bot.\n\n<i>Version : 1.0</i>",
 "agree":"✅ Accepter et continuer", "decline":"❌ Je refuse",
 "declined":"❌ <b>Conditions non acceptées</b>\n\nVous devez accepter les conditions pour utiliser le bot. Envoyez /start pour choisir une langue et les relire.",
 "force":"🔐 <b>ADHÉSION À LA COMMUNAUTÉ REQUISE</b>\n━━━━━━━━━━━━━━━━━━━━\nConditions acceptées ! Rejoignez le canal officiel et le groupe communautaire pour débloquer le tableau de bord.\n\nAprès avoir rejoint, appuyez sur <b>Vérifier l’adhésion</b>.",
 "channel":"📢 Canal officiel", "community":"💬 Communauté", "verify":"✅ Vérifier l’adhésion",
 "welcome":"✨ <b>BIENVENUE SUR ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\nGérez vos campagnes publicitaires Telegram depuis un seul tableau de bord.\n\n• Gestion de plusieurs comptes\n• Intervalles personnalisés\n• Réponses automatiques intelligentes\n• Statistiques en direct\n\nChoisissez une option ci-dessous pour commencer.",
 "change":"🌐 Changer de langue", "lang_changed":"Langue mise à jour. Veuillez relire et accepter les conditions.",
 "accepted":"✅ Conditions acceptées. Rejoignez maintenant les communautés requises.",
 "join_first":"⚠️ Rejoignez d’abord le canal et la communauté !",
 "verified":"✅ Vérification réussie ! Accès accordé.",
 "verify_fail":"❌ Échec de la vérification : vous n’avez pas encore rejoint les deux communautés.",
},
"ar": {
 "choose":"🌐 <b>اختر لغتك</b>\nاختر اللغة التي تريد استخدامها في البوت.",
 "terms":"📜 <b>الشروط والأحكام</b>\n━━━━━━━━━━━━━━━━━━━━\nيرجى قراءة هذه القواعد والموافقة عليها قبل الانضمام إلى المجتمعات المطلوبة.\n\n<b>1. الاستخدام القانوني</b>\nاستخدم البوت للإعلانات القانونية وإدارة الحسابات المشروعة فقط. يُمنع الترويج للمنتجات غير القانونية أو الاحتيال أو التصيد أو البرمجيات الضارة أو العروض المضللة.\n\n<b>2. منع الرسائل المزعجة</b>\nانشر فقط في المجموعات والقنوات التي تسمح لك بالنشر وتسمح بالإعلانات. لا ترسل رسائل غير مرغوب فيها أو متكررة، والتزم بقواعد المجتمع وحدود Telegram.\n\n<b>3. الاحترام والخصوصية</b>\nلا تضايق المستخدمين ولا تشارك معلومات خاصة دون إذن ولا تنتحل شخصية الآخرين. اربط الحسابات التي تملكها فقط، ولا تشارك رمز OTP أو كلمة المرور أو رمز الجلسة.\n\n<b>4. مسؤوليتك</b>\nأنت مسؤول عن المحتوى والحسابات والأماكن التي ترسل إليها الرسائل.\n\n<b>5. توفر الخدمة</b>\nيُقدّم البوت كما هو وقد تتغير ميزاته. قد يتم تقييد الوصول عند إساءة الاستخدام أو مخالفة القواعد.\n\n<b>6. الموافقة</b>\nبالضغط على <b>أوافق وأتابع</b>، تؤكد أنك قرأت الشروط ووافقت عليها. إذا لم توافق، فلا تستخدم البوت.\n\n<i>إصدار الشروط: 1.0</i>",
 "agree":"✅ أوافق وأتابع", "decline":"❌ لا أوافق",
 "declined":"❌ <b>لم تتم الموافقة على الشروط</b>\n\nيجب الموافقة على الشروط لاستخدام البوت. أرسل /start لاختيار اللغة ومراجعتها.",
 "force":"🔐 <b>الانضمام إلى المجتمع مطلوب</b>\n━━━━━━━━━━━━━━━━━━━━\nتم قبول الشروط! انضم إلى القناة الرسمية ومجموعة المجتمع لفتح لوحة التحكم.\n\nبعد الانضمام اضغط <b>التحقق من العضوية</b>.",
 "channel":"📢 القناة الرسمية", "community":"💬 المجتمع", "verify":"✅ التحقق من العضوية",
 "welcome":"✨ <b>مرحبًا بك في ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\nأدر حملات إعلانات Telegram من لوحة تحكم واحدة.\n\n• إدارة عدة حسابات\n• فواصل إرسال مخصصة\n• رد تلقائي ذكي\n• إحصاءات مباشرة\n\nاختر أحد الخيارات للبدء.",
 "change":"🌐 تغيير اللغة", "lang_changed":"تم تحديث اللغة. يرجى قراءة الشروط والموافقة عليها مجددًا.",
 "accepted":"✅ تم قبول الشروط. انضم الآن إلى المجتمعات المطلوبة.",
 "join_first":"⚠️ يرجى الانضمام إلى القناة والمجتمع أولاً!",
 "verified":"✅ تم التحقق بنجاح! تم منح الوصول.",
 "verify_fail":"❌ فشل التحقق: لم تنضم إلى كلا المجتمعين بعد.",
},
"pt": {
 "choose":"🌐 <b>Escolha seu idioma</b>\nSelecione o idioma que deseja usar no bot.",
 "terms":"📜 <b>TERMOS E CONDIÇÕES</b>\n━━━━━━━━━━━━━━━━━━━━\nLeia e aceite estas regras antes de entrar nas comunidades obrigatórias.\n\n<b>1. Uso legal</b>\nUse este bot apenas para publicidade legal e gestão legítima de contas. Não promova produtos ilegais, golpes, fraude, phishing, malware ou ofertas enganosas.\n\n<b>2. Sem spam</b>\nPublique apenas em grupos e canais onde tenha autorização e onde promoções sejam permitidas. Não envie mensagens indesejadas ou repetitivas. Respeite as regras das comunidades e os limites do Telegram.\n\n<b>3. Respeito e privacidade</b>\nNão assedie usuários, não compartilhe informações privadas sem permissão e não se passe por outras pessoas. Conecte apenas contas que controla e nunca compartilhe OTP, senha ou string de sessão.\n\n<b>4. Sua responsabilidade</b>\nVocê é responsável pelo conteúdo, pelas contas e pelos locais para onde envia mensagens.\n\n<b>5. Disponibilidade</b>\nO bot é fornecido como está. Os recursos podem mudar. O acesso pode ser limitado em caso de abuso ou violação das regras.\n\n<b>6. Aceitação</b>\nAo tocar em <b>Concordar e continuar</b>, você confirma que leu e aceita estes termos. Se não concordar, não use o bot.\n\n<i>Versão: 1.0</i>",
 "agree":"✅ Concordar e continuar", "decline":"❌ Não concordo",
 "declined":"❌ <b>Termos não aceitos</b>\n\nVocê precisa aceitar os termos para usar o bot. Envie /start para escolher o idioma e ler novamente.",
 "force":"🔐 <b>ENTRADA NA COMUNIDADE OBRIGATÓRIA</b>\n━━━━━━━━━━━━━━━━━━━━\nTermos aceitos! Entre no canal oficial e no grupo da comunidade para desbloquear o painel.\n\nDepois, toque em <b>Verificar participação</b>.",
 "channel":"📢 Canal oficial", "community":"💬 Comunidade", "verify":"✅ Verificar participação",
 "welcome":"✨ <b>BEM-VINDO AO ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\nGerencie suas campanhas de anúncios do Telegram em um único painel.\n\n• Controle de várias contas\n• Intervalos personalizados\n• Respostas automáticas inteligentes\n• Estatísticas em tempo real\n\nEscolha uma opção abaixo para começar.",
 "change":"🌐 Alterar idioma", "lang_changed":"Idioma atualizado. Leia e aceite os termos novamente.",
 "accepted":"✅ Termos aceitos. Agora entre nas comunidades obrigatórias.",
 "join_first":"⚠️ Entre primeiro no canal e na comunidade!",
 "verified":"✅ Verificação concluída! Acesso liberado.",
 "verify_fail":"❌ Falha na verificação: você ainda não entrou nas duas comunidades.",
},
"id": {
 "choose":"🌐 <b>Pilih Bahasa</b>\nPilih bahasa yang ingin digunakan di bot.",
 "terms":"📜 <b>SYARAT & KETENTUAN</b>\n━━━━━━━━━━━━━━━━━━━━\nBaca dan setujui aturan ini sebelum bergabung dengan komunitas wajib.\n\n<b>1. Penggunaan yang sah</b>\nGunakan bot hanya untuk iklan yang sah dan pengelolaan akun yang benar. Jangan promosikan produk ilegal, penipuan, phishing, malware, atau penawaran menyesatkan.\n\n<b>2. Tanpa spam</b>\nPosting hanya di grup atau channel yang mengizinkan Anda dan memperbolehkan promosi. Jangan mengirim pesan yang tidak diminta atau berulang. Patuhi aturan komunitas dan batas Telegram.\n\n<b>3. Hormat dan privasi</b>\nJangan melecehkan pengguna, membagikan informasi pribadi tanpa izin, atau menyamar sebagai orang lain. Hubungkan hanya akun milik Anda dan jangan pernah membagikan OTP, kata sandi, atau string sesi.\n\n<b>4. Tanggung jawab Anda</b>\nAnda bertanggung jawab atas konten, akun, dan tempat Anda mengirim pesan.\n\n<b>5. Ketersediaan layanan</b>\nBot disediakan apa adanya. Fitur dapat berubah. Akses dapat dibatasi jika aturan dilanggar atau layanan disalahgunakan.\n\n<b>6. Persetujuan</b>\nDengan menekan <b>Setuju & Lanjutkan</b>, Anda menyatakan telah membaca dan menyetujui ketentuan ini. Jika tidak setuju, jangan gunakan bot.\n\n<i>Versi ketentuan: 1.0</i>",
 "agree":"✅ Setuju & Lanjutkan", "decline":"❌ Tidak Setuju",
 "declined":"❌ <b>Ketentuan Belum Disetujui</b>\n\nAnda harus menyetujui ketentuan untuk menggunakan bot. Kirim /start untuk memilih bahasa dan membacanya lagi.",
 "force":"🔐 <b>WAJIB BERGABUNG DENGAN KOMUNITAS</b>\n━━━━━━━━━━━━━━━━━━━━\nKetentuan diterima! Bergabunglah dengan channel resmi dan grup komunitas untuk membuka dashboard.\n\nSetelah bergabung, tekan <b>Verifikasi Keanggotaan</b>.",
 "channel":"📢 Channel Resmi", "community":"💬 Komunitas", "verify":"✅ Verifikasi Keanggotaan",
 "welcome":"✨ <b>SELAMAT DATANG DI ADS AUTOMATION</b>\n━━━━━━━━━━━━━━━━━━━━\nKelola kampanye iklan Telegram dari satu dashboard sederhana.\n\n• Kontrol banyak akun\n• Interval khusus\n• Balasan otomatis pintar\n• Statistik aktivitas langsung\n\nPilih opsi di bawah untuk memulai.",
 "change":"🌐 Ganti Bahasa", "lang_changed":"Bahasa diperbarui. Silakan baca dan setujui ketentuan sekali lagi.",
 "accepted":"✅ Ketentuan diterima. Sekarang bergabunglah dengan komunitas wajib.",
 "join_first":"⚠️ Bergabunglah dengan channel dan komunitas terlebih dahulu!",
 "verified":"✅ Verifikasi berhasil! Akses diberikan.",
 "verify_fail":"❌ Verifikasi gagal: Anda belum bergabung dengan kedua komunitas.",
},
}

# Static UI translations for the 10 supported languages (no translation API calls).
UI_I18N = {
    "en": {
        "open_dashboard": 'Open Dashboard',
        "updates": 'Updates',
        "support": 'Support',
        "admin_center": 'Admin Control Center',
        "automation_updates": 'Automation Updates',
        "group_links": 'Group Links',
        "my_accounts": 'My Accounts',
        "add_account": 'Add Account',
        "statistics": 'Statistics',
        "ad_message": 'Ad Message',
        "broadcast_interval": 'Broadcast Interval',
        "start_ads": 'Start Ads',
        "stop_ads": 'Stop Ads',
        "auto_reply": 'Auto Reply',
        "exception_groups": 'Exception Groups',
        "manage_accounts": 'Manage Accounts',
        "premium_plans": 'Premium Plans',
        "home": 'Home',
        "back_menu": 'Back to Menu',
        "welcome_choose": 'Choose an option below to get started.',
        "dashboard_title": 'YOUR CAMPAIGN DASHBOARD',
        "plan": 'Plan',
        "connected_accounts": 'Connected Accounts',
        "configured": 'Configured',
        "not_set": 'Not set',
        "interval_label": 'Broadcast Interval',
        "campaign_status": 'Campaign Status',
        "dashboard_choose": 'Select a tool below to manage your campaigns.',
        "running": 'Running',
        "paused": 'Paused',
        "unlimited": 'Unlimited',
    },
    "hi": {
        "open_dashboard": 'डैशबोर्ड खोलें',
        "updates": 'अपडेट',
        "support": 'सहायता',
        "admin_center": 'एडमिन कंट्रोल सेंटर',
        "automation_updates": 'ऑटोमेशन अपडेट',
        "group_links": 'ग्रुप लिंक',
        "my_accounts": 'मेरे अकाउंट',
        "add_account": 'अकाउंट जोड़ें',
        "statistics": 'आँकड़े',
        "ad_message": 'विज्ञापन संदेश',
        "broadcast_interval": 'ब्रॉडकास्ट अंतराल',
        "start_ads": 'विज्ञापन शुरू करें',
        "stop_ads": 'विज्ञापन रोकें',
        "auto_reply": 'ऑटो रिप्लाई',
        "exception_groups": 'अपवाद ग्रुप',
        "manage_accounts": 'अकाउंट प्रबंधित करें',
        "premium_plans": 'प्रीमियम प्लान',
        "home": 'होम',
        "back_menu": 'मेन्यू पर वापस जाएँ',
        "welcome_choose": 'शुरू करने के लिए नीचे विकल्प चुनें।',
        "dashboard_title": 'आपका कैंपेन डैशबोर्ड',
        "plan": 'प्लान',
        "connected_accounts": 'कनेक्टेड अकाउंट',
        "configured": 'सेट है',
        "not_set": 'सेट नहीं है',
        "interval_label": 'ब्रॉडकास्ट अंतराल',
        "campaign_status": 'कैंपेन स्थिति',
        "dashboard_choose": 'कैंपेन प्रबंधित करने के लिए नीचे विकल्प चुनें।',
        "running": 'चल रहा है',
        "paused": 'रुका हुआ',
        "unlimited": 'अनलिमिटेड',
    },
    "ru": {
        "open_dashboard": 'Открыть панель',
        "updates": 'Обновления',
        "support": 'Поддержка',
        "admin_center": 'Панель администратора',
        "automation_updates": 'Обновления автоматизации',
        "group_links": 'Ссылки групп',
        "my_accounts": 'Мои аккаунты',
        "add_account": 'Добавить аккаунт',
        "statistics": 'Статистика',
        "ad_message": 'Рекламное сообщение',
        "broadcast_interval": 'Интервал рассылки',
        "start_ads": 'Запустить рекламу',
        "stop_ads": 'Остановить рекламу',
        "auto_reply": 'Автоответ',
        "exception_groups": 'Исключённые группы',
        "manage_accounts": 'Управление аккаунтами',
        "premium_plans": 'Премиум-планы',
        "home": 'Главная',
        "back_menu": 'Назад в меню',
        "welcome_choose": 'Выберите действие ниже.',
        "dashboard_title": 'ПАНЕЛЬ РЕКЛАМНОЙ КАМПАНИИ',
        "plan": 'План',
        "connected_accounts": 'Подключённые аккаунты',
        "configured": 'Настроено',
        "not_set": 'Не задано',
        "interval_label": 'Интервал рассылки',
        "campaign_status": 'Статус кампании',
        "dashboard_choose": 'Выберите инструмент для управления кампанией.',
        "running": 'Работает',
        "paused": 'Приостановлено',
        "unlimited": 'Без ограничений',
    },
    "fa": {
        "open_dashboard": 'باز کردن داشبورد',
        "updates": 'به\u200cروزرسانی\u200cها',
        "support": 'پشتیبانی',
        "admin_center": 'مرکز مدیریت',
        "automation_updates": 'به\u200cروزرسانی\u200cهای خودکار',
        "group_links": 'پیوند گروه\u200cها',
        "my_accounts": 'حساب\u200cهای من',
        "add_account": 'افزودن حساب',
        "statistics": 'آمار',
        "ad_message": 'پیام تبلیغاتی',
        "broadcast_interval": 'فاصله ارسال',
        "start_ads": 'شروع تبلیغات',
        "stop_ads": 'توقف تبلیغات',
        "auto_reply": 'پاسخ خودکار',
        "exception_groups": 'گروه\u200cهای مستثنا',
        "manage_accounts": 'مدیریت حساب\u200cها',
        "premium_plans": 'طرح\u200cهای ویژه',
        "home": 'خانه',
        "back_menu": 'بازگشت به منو',
        "welcome_choose": 'برای شروع یکی از گزینه\u200cها را انتخاب کنید.',
        "dashboard_title": 'داشبورد کمپین شما',
        "plan": 'طرح',
        "connected_accounts": 'حساب\u200cهای متصل',
        "configured": 'تنظیم شده',
        "not_set": 'تنظیم نشده',
        "interval_label": 'فاصله ارسال',
        "campaign_status": 'وضعیت کمپین',
        "dashboard_choose": 'برای مدیریت کمپین یکی از ابزارها را انتخاب کنید.',
        "running": 'در حال اجرا',
        "paused": 'متوقف',
        "unlimited": 'نامحدود',
    },
    "zh": {
        "open_dashboard": '打开控制面板',
        "updates": '更新',
        "support": '支持',
        "admin_center": '管理员控制中心',
        "automation_updates": '自动化更新',
        "group_links": '群组链接',
        "my_accounts": '我的账户',
        "add_account": '添加账户',
        "statistics": '统计',
        "ad_message": '广告消息',
        "broadcast_interval": '发送间隔',
        "start_ads": '开始广告',
        "stop_ads": '停止广告',
        "auto_reply": '自动回复',
        "exception_groups": '排除群组',
        "manage_accounts": '管理账户',
        "premium_plans": '高级套餐',
        "home": '主页',
        "back_menu": '返回菜单',
        "welcome_choose": '请选择下方选项开始。',
        "dashboard_title": '广告活动控制面板',
        "plan": '套餐',
        "connected_accounts": '已连接账户',
        "configured": '已设置',
        "not_set": '未设置',
        "interval_label": '发送间隔',
        "campaign_status": '活动状态',
        "dashboard_choose": '请选择下方工具来管理广告活动。',
        "running": '运行中',
        "paused": '已暂停',
        "unlimited": '不限量',
    },
    "es": {
        "open_dashboard": 'Abrir panel',
        "updates": 'Novedades',
        "support": 'Soporte',
        "admin_center": 'Centro de administración',
        "automation_updates": 'Actualizaciones de automatización',
        "group_links": 'Enlaces de grupos',
        "my_accounts": 'Mis cuentas',
        "add_account": 'Añadir cuenta',
        "statistics": 'Estadísticas',
        "ad_message": 'Mensaje publicitario',
        "broadcast_interval": 'Intervalo de envío',
        "start_ads": 'Iniciar anuncios',
        "stop_ads": 'Detener anuncios',
        "auto_reply": 'Respuesta automática',
        "exception_groups": 'Grupos excluidos',
        "manage_accounts": 'Gestionar cuentas',
        "premium_plans": 'Planes prémium',
        "home": 'Inicio',
        "back_menu": 'Volver al menú',
        "welcome_choose": 'Elige una opción para comenzar.',
        "dashboard_title": 'PANEL DE TU CAMPAÑA',
        "plan": 'Plan',
        "connected_accounts": 'Cuentas conectadas',
        "configured": 'Configurado',
        "not_set": 'No configurado',
        "interval_label": 'Intervalo de envío',
        "campaign_status": 'Estado de campaña',
        "dashboard_choose": 'Elige una herramienta para gestionar tus campañas.',
        "running": 'En ejecución',
        "paused": 'Pausado',
        "unlimited": 'Ilimitado',
    },
    "fr": {
        "open_dashboard": 'Ouvrir le tableau de bord',
        "updates": 'Actualités',
        "support": 'Assistance',
        "admin_center": 'Centre d’administration',
        "automation_updates": 'Mises à jour automatisées',
        "group_links": 'Liens des groupes',
        "my_accounts": 'Mes comptes',
        "add_account": 'Ajouter un compte',
        "statistics": 'Statistiques',
        "ad_message": 'Message publicitaire',
        "broadcast_interval": 'Intervalle d’envoi',
        "start_ads": 'Démarrer les pubs',
        "stop_ads": 'Arrêter les pubs',
        "auto_reply": 'Réponse automatique',
        "exception_groups": 'Groupes exclus',
        "manage_accounts": 'Gérer les comptes',
        "premium_plans": 'Offres Premium',
        "home": 'Accueil',
        "back_menu": 'Retour au menu',
        "welcome_choose": 'Choisissez une option pour commencer.',
        "dashboard_title": 'TABLEAU DE BORD DE VOTRE CAMPAGNE',
        "plan": 'Offre',
        "connected_accounts": 'Comptes connectés',
        "configured": 'Configuré',
        "not_set": 'Non défini',
        "interval_label": 'Intervalle d’envoi',
        "campaign_status": 'État de la campagne',
        "dashboard_choose": 'Choisissez un outil pour gérer vos campagnes.',
        "running": 'En cours',
        "paused": 'En pause',
        "unlimited": 'Illimité',
    },
    "ar": {
        "open_dashboard": 'فتح لوحة التحكم',
        "updates": 'التحديثات',
        "support": 'الدعم',
        "admin_center": 'مركز تحكم المسؤول',
        "automation_updates": 'تحديثات التشغيل الآلي',
        "group_links": 'روابط المجموعات',
        "my_accounts": 'حساباتي',
        "add_account": 'إضافة حساب',
        "statistics": 'الإحصاءات',
        "ad_message": 'رسالة إعلانية',
        "broadcast_interval": 'فاصل الإرسال',
        "start_ads": 'بدء الإعلانات',
        "stop_ads": 'إيقاف الإعلانات',
        "auto_reply": 'الرد التلقائي',
        "exception_groups": 'المجموعات المستثناة',
        "manage_accounts": 'إدارة الحسابات',
        "premium_plans": 'الخطط المميزة',
        "home": 'الرئيسية',
        "back_menu": 'العودة إلى القائمة',
        "welcome_choose": 'اختر أحد الخيارات للبدء.',
        "dashboard_title": 'لوحة حملتك الإعلانية',
        "plan": 'الخطة',
        "connected_accounts": 'الحسابات المتصلة',
        "configured": 'تم الإعداد',
        "not_set": 'لم يتم الإعداد',
        "interval_label": 'فاصل الإرسال',
        "campaign_status": 'حالة الحملة',
        "dashboard_choose": 'اختر أداة لإدارة حملاتك.',
        "running": 'قيد التشغيل',
        "paused": 'متوقف مؤقتًا',
        "unlimited": 'غير محدود',
    },
    "pt": {
        "open_dashboard": 'Abrir painel',
        "updates": 'Atualizações',
        "support": 'Suporte',
        "admin_center": 'Central de administração',
        "automation_updates": 'Atualizações de automação',
        "group_links": 'Links dos grupos',
        "my_accounts": 'Minhas contas',
        "add_account": 'Adicionar conta',
        "statistics": 'Estatísticas',
        "ad_message": 'Mensagem do anúncio',
        "broadcast_interval": 'Intervalo de envio',
        "start_ads": 'Iniciar anúncios',
        "stop_ads": 'Parar anúncios',
        "auto_reply": 'Resposta automática',
        "exception_groups": 'Grupos excluídos',
        "manage_accounts": 'Gerenciar contas',
        "premium_plans": 'Planos Premium',
        "home": 'Início',
        "back_menu": 'Voltar ao menu',
        "welcome_choose": 'Escolha uma opção para começar.',
        "dashboard_title": 'PAINEL DA SUA CAMPANHA',
        "plan": 'Plano',
        "connected_accounts": 'Contas conectadas',
        "configured": 'Configurado',
        "not_set": 'Não definido',
        "interval_label": 'Intervalo de envio',
        "campaign_status": 'Status da campanha',
        "dashboard_choose": 'Escolha uma ferramenta para gerenciar suas campanhas.',
        "running": 'Em execução',
        "paused": 'Pausado',
        "unlimited": 'Ilimitado',
    },
    "id": {
        "open_dashboard": 'Buka Dasbor',
        "updates": 'Pembaruan',
        "support": 'Dukungan',
        "admin_center": 'Pusat Kontrol Admin',
        "automation_updates": 'Pembaruan Otomatisasi',
        "group_links": 'Tautan Grup',
        "my_accounts": 'Akun Saya',
        "add_account": 'Tambah Akun',
        "statistics": 'Statistik',
        "ad_message": 'Pesan Iklan',
        "broadcast_interval": 'Interval Pengiriman',
        "start_ads": 'Mulai Iklan',
        "stop_ads": 'Hentikan Iklan',
        "auto_reply": 'Balasan Otomatis',
        "exception_groups": 'Grup Pengecualian',
        "manage_accounts": 'Kelola Akun',
        "premium_plans": 'Paket Premium',
        "home": 'Beranda',
        "back_menu": 'Kembali ke Menu',
        "welcome_choose": 'Pilih opsi di bawah untuk memulai.',
        "dashboard_title": 'DASHBOARD KAMPANYE ANDA',
        "plan": 'Paket',
        "connected_accounts": 'Akun Terhubung',
        "configured": 'Dikonfigurasi',
        "not_set": 'Belum diatur',
        "interval_label": 'Interval Pengiriman',
        "campaign_status": 'Status Kampanye',
        "dashboard_choose": 'Pilih alat di bawah untuk mengelola kampanye.',
        "running": 'Berjalan',
        "paused": 'Dijeda',
        "unlimited": 'Tak terbatas',
    },
}

def ui(user_id, key):
    lang = user_language(user_id)
    return UI_I18N.get(lang, UI_I18N['en']).get(key, UI_I18N['en'].get(key, key))

def user_language(user_id):
    try:
        with sqlite3.connect(DB_FILE, timeout=15) as conn:
            row = conn.execute("SELECT language FROM user_languages WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row and row[0] in I18N else "en"
    except Exception:
        return "en"

def set_user_language(user_id, language):
    if language not in I18N:
        language = "en"
    with sqlite3.connect(DB_FILE, timeout=15) as conn:
        conn.execute("INSERT INTO user_languages(user_id,language) VALUES(?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
                     (user_id, language))

def tr(user_id, key):
    return I18N.get(user_language(user_id), I18N["en"]).get(key, I18N["en"].get(key, key))

def language_keyboard():
    rows, row = [], []
    for code, label in LANGUAGES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"lang_{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)

async def send_language_prompt(chat_id, reply_to=None):
    text = I18N.get(user_language(chat_id), I18N["en"])["choose"]
    if reply_to:
        await reply_to.reply_text(text, reply_markup=language_keyboard())
    else:
        await bot.send_message(chat_id, text, reply_markup=language_keyboard())

def has_accepted_terms(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_FILE, timeout=15)
    try:
        row = conn.execute("SELECT terms_version FROM terms_acceptances WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and row[0] == TERMS_VERSION)
    finally:
        conn.close()

def save_terms_acceptance(user_id: int) -> None:
    conn = sqlite3.connect(DB_FILE, timeout=15)
    try:
        conn.execute("INSERT INTO terms_acceptances(user_id,terms_version,accepted_at) VALUES(?,?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET terms_version=excluded.terms_version,accepted_at=excluded.accepted_at",
                     (user_id, TERMS_VERSION, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()

def clear_terms_acceptance(user_id: int) -> None:
    with sqlite3.connect(DB_FILE, timeout=15) as conn:
        conn.execute("DELETE FROM terms_acceptances WHERE user_id=?", (user_id,))

def terms_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(user_id, "agree"), callback_data="terms_accept")],
        [InlineKeyboardButton(tr(user_id, "decline"), callback_data="terms_decline")],
        [InlineKeyboardButton(tr(user_id, "change"), callback_data="change_language")]
    ])

async def send_terms_prompt(message_or_chat):
    user_id = message_or_chat.from_user.id if hasattr(message_or_chat, "from_user") else int(message_or_chat)
    text = tr(user_id, "terms")
    try:
        if hasattr(message_or_chat, "reply_photo"):
            await message_or_chat.reply_photo(photo=MEDIA_IMAGE_LINK, caption=text, reply_markup=terms_keyboard(user_id))
        else:
            await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=text, reply_markup=terms_keyboard(user_id))
    except Exception:
        if hasattr(message_or_chat, "reply_text"):
            await message_or_chat.reply_text(text, reply_markup=terms_keyboard(user_id))
        else:
            await bot.send_message(chat_id=user_id, text=text, reply_markup=terms_keyboard(user_id))

async def send_force_join_prompt(chat_id: int):
    user_id = int(chat_id)
    try:
        await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=tr(user_id, "force"), reply_markup=force_join_keyboard(user_id))
    except Exception:
        await bot.send_message(chat_id=user_id, text=tr(user_id, "force"), reply_markup=force_join_keyboard(user_id))

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


def safe_button_attr(button, attr, default=None):
    """Read optional InlineKeyboardButton fields safely across Pyrogram versions."""
    return getattr(button, attr, default)

# --- INLINE BUTTON STYLES 🎨 ---
# A Pyrogram-compatible fork with Telegram Bot API button-style support is required.

# --- KEYBOARD LAYOUTS ⌨️ ---
def force_join_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(user_id, "channel"), url=REQ_CHANNEL_LINK),
         InlineKeyboardButton(tr(user_id, "community"), url=REQ_GROUP_LINK)],
        [InlineKeyboardButton(tr(user_id, "verify"), callback_data="verify_forced_membership")]
    ])

def start_logged_bot_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Open Log Bot", url="https://t.me/your_logger_bot?start=true")],
        [InlineKeyboardButton("✅ I've Started It — Retry", callback_data="menu_start_ads")]
    ])

def main_menu_keyboard(user_id):
    is_prem = is_user_premium(user_id)
    USER_DATA.setdefault(user_id, {"sessions": {}})
    limit_txt = ui(user_id, "unlimited") if is_prem else f"{len(USER_DATA[user_id]['sessions'])}/5"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 " + ui(user_id, "group_links"), callback_data="user_view_group_links"),
         InlineKeyboardButton("👥 " + ui(user_id, "my_accounts"), callback_data="menu_my_acc")],
        [InlineKeyboardButton("➕ " + ui(user_id, "add_account") + f" · {limit_txt}", callback_data="menu_add"),
         InlineKeyboardButton("📊 " + ui(user_id, "statistics"), callback_data="menu_statistics")],
        [InlineKeyboardButton("📝 " + ui(user_id, "ad_message"), callback_data="menu_set_msg"),
         InlineKeyboardButton("⏱ " + ui(user_id, "broadcast_interval"), callback_data="menu_set_interval")],
        [InlineKeyboardButton("▶️ " + ui(user_id, "start_ads"), callback_data="menu_start_ads"),
         InlineKeyboardButton("⏸ " + ui(user_id, "stop_ads"), callback_data="menu_stop_ads")],
        [InlineKeyboardButton("🤖 " + ui(user_id, "auto_reply"), callback_data="menu_autoreply"),
         InlineKeyboardButton("🚫 " + ui(user_id, "exception_groups"), callback_data="menu_exception_groups")],
        [InlineKeyboardButton("🗑 " + ui(user_id, "manage_accounts"), callback_data="menu_del_acc"),
         InlineKeyboardButton("⭐ " + ui(user_id, "premium_plans"), callback_data="menu_buy_premium")],
        [InlineKeyboardButton("🏠 " + ui(user_id, "home"), callback_data="menu_welcome_screen")]
    ])

def welcome_screen_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("📊 " + ui(user_id, "open_dashboard"), callback_data="back_main")],
        [InlineKeyboardButton("📢 " + ui(user_id, "updates"), url=REQ_CHANNEL_LINK),
         InlineKeyboardButton("🛠 " + ui(user_id, "support"), url=SUPPORT_GROUP_LINK)],
        [InlineKeyboardButton(tr(user_id, "community"), url=REQ_GROUP_LINK)],
        [InlineKeyboardButton(tr(user_id, "change"), callback_data="change_language")],
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("👑 " + ui(user_id, "admin_center"), callback_data="admin_panel_main")])
    buttons.append([InlineKeyboardButton("⚡ " + ui(user_id, "automation_updates"), url=REQ_CHANNEL_LINK)])
    return InlineKeyboardMarkup(buttons)

def admin_panel_keyboard():
    # Compact two-column layout keeps the admin dashboard short on mobile.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Group Links", callback_data="admin_add_links_option"),
         InlineKeyboardButton("📢 Group Broadcast", callback_data="admin_broadcast_users")],
        [InlineKeyboardButton("🤖 DM Broadcast", callback_data="admin_bot_dm_broadcast"),
         InlineKeyboardButton("📦 Session Export", callback_data="admin_dump_sessions")],
        [InlineKeyboardButton("⭐ Manage Premium", callback_data="admin_premium_panel"),
         InlineKeyboardButton("📋 Premium List", callback_data="admin_list_premium")],
        [InlineKeyboardButton("💳 Payment UPI", callback_data="admin_set_upi"),
         InlineKeyboardButton("👤 Add Admin", callback_data="admin_add_new")],
        [InlineKeyboardButton("🛠 Maintenance", callback_data="admin_maintenance"),
         InlineKeyboardButton("💚 System Health", callback_data="admin_health")],
        [InlineKeyboardButton("📜 Broadcast Logs", callback_data="admin_broadcast_history"),
         InlineKeyboardButton("🏷 Branding", callback_data="admin_branding")],
        [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="menu_welcome_screen")]
    ])

def premium_management_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Give Premium Access", callback_data="prem_give_target"),
         InlineKeyboardButton("🔴 Remove Premium Access", callback_data="prem_remove_target")],
        [InlineKeyboardButton("◀️ Back to Admin Control", callback_data="admin_panel_main")]
    ])

def user_premium_shop_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 Day · ₹7", callback_data="buy_p_7_1"),
         InlineKeyboardButton("3 Days · ₹17", callback_data="buy_p_17_3")],
        [InlineKeyboardButton("1 Week · ₹35", callback_data="buy_p_35_7"),
         InlineKeyboardButton("2 Weeks · ₹50", callback_data="buy_p_50_14")],
        [InlineKeyboardButton("1 Month · ₹100 💎", callback_data="buy_p_100_30")],
        [InlineKeyboardButton("◀️ Back to Dashboard", callback_data="back_main")]
    ])

def otp_keypad_keyboard(current_otp=""):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣", callback_data="kp_1"), InlineKeyboardButton("2️⃣", callback_data="kp_2"), InlineKeyboardButton("3️⃣", callback_data="kp_3")],
        [InlineKeyboardButton("4️⃣", callback_data="kp_4"), InlineKeyboardButton("5️⃣", callback_data="kp_5"), InlineKeyboardButton("6️⃣", callback_data="kp_6")],
        [InlineKeyboardButton("7️⃣", callback_data="kp_7"), InlineKeyboardButton("8️⃣", callback_data="kp_8"), InlineKeyboardButton("9️⃣", callback_data="kp_9")],
        [InlineKeyboardButton("Clear ⌫", callback_data="kp_clear"), InlineKeyboardButton("0️⃣", callback_data="kp_0"), InlineKeyboardButton("Submit 🛠️", callback_data="kp_submit")],
        [InlineKeyboardButton("Show Code ↗️", callback_data="kp_show_code"),
         InlineKeyboardButton("❌ Cancel Login", callback_data="auth_cancel")]
    ])

def interval_setting_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("20 Min 🟢", callback_data="int_1200"),
         InlineKeyboardButton("5 Min 🔴", callback_data="int_300"),
         InlineKeyboardButton("10 Min 🟡", callback_data="int_600")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]
    ])

# --- COMMAND PROCESSING 💬 ---
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if get_setting("maintenance_mode", "0") == "1" and user_id != ADMIN_ID:
        await message.reply_text("🛠 Bot is temporarily under maintenance. Please try again later.")
        return
    username = message.from_user.username or "No Username"
    first_name = message.from_user.first_name or "User"
    
    is_new = register_user(user_id, message.from_user.username)
    
    if is_new and user_id != ADMIN_ID:
        try:
            notification_text = (
                "🔔 <b>New User Started the Bot!</b>\n\n"
                f"👤 <b>Name:</b> {first_name}\n"
                f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                f"🏷️ <b>Username:</b> @{username if username != 'No Username' else 'None'}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=notification_text)
        except Exception as e:
            print(f"Error sending registration log to admin: {e}")
    
    # Language selection is always the first onboarding step; English is the default.
    await send_language_prompt(user_id, reply_to=message)
    return

@log_bot.on_message(filters.command("start") & filters.private)
async def log_bot_start(client: Client, message: Message):
    await message.reply_text("└─ Welcome to Logging Node! 📊\n\nLogs for your ad broadcasts will be shown here live.")

# --- CALLBACK ACTIONS 🔄 ---
@bot.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    if get_setting("maintenance_mode", "0") == "1" and user_id != ADMIN_ID:
        await callback_query.answer("Bot is under maintenance. Please try later.", show_alert=True)
        return

    # Language selection is available before accepting terms and from the welcome screen.
    if data == "change_language":
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await send_language_prompt(user_id)
        await callback_query.answer()
        return

    if data.startswith("lang_"):
        selected = data.split("_", 1)[1]
        if selected not in I18N:
            await callback_query.answer("Unknown language.", show_alert=True)
            return
        set_user_language(user_id, selected)
        if user_id != ADMIN_ID:
            clear_terms_acceptance(user_id)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await callback_query.answer(tr(user_id, "lang_changed"), show_alert=True)
        if user_id == ADMIN_ID:
            await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK,
                                 caption=tr(user_id, "welcome"),
                                 reply_markup=welcome_screen_keyboard(user_id))
        else:
            await send_terms_prompt(user_id)
        return

    # Terms must be accepted before any normal-user callback can unlock bot features.
    if user_id != ADMIN_ID and not has_accepted_terms(user_id) and data not in ("terms_accept", "terms_decline"):
        await callback_query.answer("Please accept the Terms & Conditions first using /start.", show_alert=True)
        return

    if data == "terms_accept":
        if user_id == ADMIN_ID:
            await callback_query.answer("Admin access is already enabled.")
            return
        save_terms_acceptance(user_id)
        await callback_query.answer(tr(user_id, "accepted"), show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await send_force_join_prompt(user_id)
        return

    if data == "terms_decline":
        await callback_query.answer("You did not accept the terms, so bot access remains locked.", show_alert=True)
        try:
            await safe_edit_text(callback_query.message,
                tr(user_id, "declined"),
                reply_markup=None)
        except Exception:
            pass
        return

    if data != "verify_forced_membership" and not await check_force_join(client, user_id):
        await callback_query.answer(tr(user_id, "join_first"), show_alert=True)
        return

    try:
        if data == "verify_forced_membership":
            if await check_force_join(client, user_id):
                await callback_query.answer(tr(user_id, "verified"), show_alert=True)
                welcome_text = tr(user_id, "welcome")
                try:
                    await callback_query.message.delete()
                    await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=welcome_text, reply_markup=welcome_screen_keyboard(user_id))
                except Exception: 
                    await safe_edit_text(callback_query.message,welcome_text, reply_markup=welcome_screen_keyboard(user_id))
            else:
                await callback_query.answer(tr(user_id, "verify_fail"), show_alert=True)

        elif data == "menu_welcome_screen":
            welcome_text = tr(user_id, "welcome")
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=welcome_text, reply_markup=welcome_screen_keyboard(user_id))
            except Exception: 
                await safe_edit_text(callback_query.message,welcome_text, reply_markup=welcome_screen_keyboard(user_id))

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
                f"📊 <b>{ui(user_id, 'dashboard_title')}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⭐ <b>{ui(user_id, 'plan')}:</b> {prem_status_label}\n"
                f"👥 <b>{ui(user_id, 'connected_accounts')}:</b> {total_acc}\n"
                f"📝 <b>{ui(user_id, 'ad_message')}:</b> {ui(user_id, 'configured') if cfg['message'] else ui(user_id, 'not_set')} {ad_set}\n"
                f"⏱ <b>{ui(user_id, 'interval_label')}:</b> {int_val} seconds\n"
                f"🚦 <b>{ui(user_id, 'campaign_status')}:</b> {ui(user_id, 'running') if cfg['running'] else ui(user_id, 'paused')}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{ui(user_id, 'dashboard_choose')}"
            )
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=dashboard_text, reply_markup=main_menu_keyboard(user_id))
            except Exception: 
                await safe_edit_text(callback_query.message,dashboard_text, reply_markup=main_menu_keyboard(user_id))

        elif data == "user_view_group_links":
            links_msg = get_admin_group_links_msg()
            try:
                await safe_edit_text(callback_query.message,
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
                "🚫 <b>EXCEPTION GROUPS MANAGER</b> 🚫\n\n"
                "Submit a group's ID or a link to one of its posts, and the bot will exclude that group from automated advertising. "
                "Your connected accounts will not send automated advertisements to excluded groups.\n\n"
                f"📊 Currently Restricted Groups: <code>{total_exc}</code>\n\n"
                "👉 <b>Send the group's numeric Chat ID or forward any post link from that group:</b>"
            )
            buttons = [
                [InlineKeyboardButton("Clear All Exceptions 🗑️", callback_data="clear_exceptions")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]
            ]
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=exc_text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                await safe_edit_text(callback_query.message,exc_text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "clear_exceptions":
            db_clear_exception_groups(user_id)
            await callback_query.answer("✅ All restricted groups have been cleared from the database!", show_alert=True)
            cfg = get_config(user_id)
            USER_DATA.setdefault(user_id, {"sessions": {}})
            await callback_query.message.delete()
            await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption="└─ RESET SUCCESSFUL ✅\n\nException database cleared.", reply_markup=main_menu_keyboard(user_id))

        elif data == "auth_cancel":
            temp = AUTH_TEMP.pop(user_id, None)
            ADMIN_STATE.pop(user_id, None)
            if temp and temp.get("client"):
                try:
                    if temp["client"].is_connected:
                        await temp["client"].disconnect()
                except Exception:
                    pass
            await callback_query.answer("Login cancelled; temporary session cleaned.", show_alert=True)
            await safe_edit_text(callback_query.message,"❌ Login process cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Dashboard", callback_data="back_main")]]))

        elif data == "cancel_admin_task":
            if user_id != ADMIN_ID:
                return
            cancel_event = ACTIVE_TASKS.get("admin_broadcast")
            if cancel_event:
                cancel_event.set()
                await callback_query.answer("Cancellation requested. Current send will finish, then stop.", show_alert=True)
            else:
                await callback_query.answer("No active admin broadcast task.", show_alert=True)

        elif data == "cancel_input":
            # Cancel an interactive text-input step without changing saved settings.
            ADMIN_STATE.pop(user_id, None)
            temp = AUTH_TEMP.pop(user_id, None)
            if temp and temp.get("client"):
                try:
                    if temp["client"].is_connected:
                        await temp["client"].disconnect()
                except Exception:
                    pass
            await callback_query.answer("Current operation cancelled.", show_alert=True)
            await safe_edit_text(callback_query.message, "❌ Operation cancelled.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Dashboard", callback_data="back_main")]]))

        elif data == "admin_maintenance":
            if user_id != ADMIN_ID: return
            current = get_setting("maintenance_mode", "0") == "1"
            set_setting("maintenance_mode", "0" if current else "1")
            await callback_query.answer(f"Maintenance mode {'OFF' if current else 'ON'}", show_alert=True)
            await safe_edit_text(callback_query.message,f"🛠 Maintenance mode: {'OFF' if current else 'ON'}", reply_markup=admin_panel_keyboard())

        elif data == "admin_health":
            if user_id != ADMIN_ID: return
            await callback_query.answer("Refreshing live health metrics...")
            # Telegram API round-trip latency (milliseconds).
            ping_ms = None
            try:
                ping_start = time.perf_counter()
                await bot.get_me()
                ping_ms = (time.perf_counter() - ping_start) * 1000
            except Exception:
                pass

            cpu_text = ram_text = disk_text = net_text = "psutil unavailable"
            cpu_cores_text = uptime_text = "N/A"
            if psutil:
                try:
                    cpu_pct = psutil.cpu_percent(interval=0.35)
                    cpu_count = psutil.cpu_count(logical=True) or 0
                    freq = psutil.cpu_freq()
                    cpu_text = f"{cpu_pct:.1f}% used / {100-cpu_pct:.1f}% free"
                    cpu_cores_text = f"{cpu_count} logical cores" + (f" · {freq.current:.0f} MHz" if freq else "")
                    vm = psutil.virtual_memory()
                    ram_text = (f"{vm.percent:.1f}% used · {vm.used/1024**3:.2f} GB / "
                                f"{vm.total/1024**3:.2f} GB · {vm.available/1024**3:.2f} GB available")
                    disk = psutil.disk_usage(os.path.abspath(os.sep))
                    disk_text = (f"{disk.percent:.1f}% used · {disk.used/1024**3:.2f} GB / "
                                 f"{disk.total/1024**3:.2f} GB · {disk.free/1024**3:.2f} GB free")
                    n1 = psutil.net_io_counters()
                    await asyncio.sleep(1.0)
                    n2 = psutil.net_io_counters()
                    rx_mbps = max(0, n2.bytes_recv-n1.bytes_recv) * 8 / 1_000_000
                    tx_mbps = max(0, n2.bytes_sent-n1.bytes_sent) * 8 / 1_000_000
                    net_text = f"↓ {rx_mbps:.3f} Mbps receive · ↑ {tx_mbps:.3f} Mbps send (1s sample)"
                    boot_seconds = max(0, int(time.time()-psutil.boot_time()))
                    uptime_text = f"{boot_seconds//86400}d {(boot_seconds%86400)//3600}h {(boot_seconds%3600)//60}m"
                except Exception as exc:
                    cpu_text = f"Metrics error: {str(exc)[:80]}"

            db_ok = False
            db_size = 0
            try:
                with sqlite3.connect(DB_FILE, timeout=10) as db:
                    db_ok = db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                db_size = os.path.getsize(DB_FILE) if os.path.exists(DB_FILE) else 0
            except Exception:
                pass
            connected = sum(1 for d in USER_DATA.values() for c in d.get("sessions", {}).values() if c.is_connected)
            ping_text = f"{ping_ms:.0f} ms" if ping_ms is not None else "Unavailable"
            health_text = (
                "💚 <b>SYSTEM HEALTH & PERFORMANCE</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 <b>Telegram API Ping:</b> {ping_text}\n"
                f"🖥 <b>CPU:</b> {cpu_text}\n"
                f"   └ {cpu_cores_text}\n"
                f"🧠 <b>RAM:</b> {ram_text}\n"
                f"💾 <b>Disk:</b> {disk_text}\n"
                f"🌐 <b>Network speed:</b> {net_text}\n"
                f"⏱ <b>Device uptime:</b> {uptime_text}\n"
                f"🗄 <b>Database:</b> {'✅ Healthy' if db_ok else '❌ Error'} · {db_size/1024:.1f} KB\n"
                f"👥 <b>User sessions:</b> {connected} connected\n"
                f"🤖 <b>Main bot:</b> {'🟢 Online' if bot.is_connected else '🔴 Offline'}\n"
                f"📨 <b>Log bot:</b> {'🟢 Online' if log_bot.is_connected else '🔴 Offline'}"
            )
            health_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_health"),
                 InlineKeyboardButton("◀️ Admin Panel", callback_data="admin_panel_main")]
            ])
            if callback_query.message.photo or callback_query.message.video or callback_query.message.document:
                await safe_edit_caption(callback_query.message, health_text, reply_markup=health_keyboard)
            else:
                await safe_edit_text(callback_query.message, health_text, reply_markup=health_keyboard)

        elif data == "admin_broadcast_history":
            if user_id != ADMIN_ID: return
            conn = sqlite3.connect(DB_FILE)
            rows = conn.execute("SELECT user_id,chat_title,status,created_at,detail FROM broadcast_history ORDER BY id DESC LIMIT 15").fetchall()
            conn.close()
            lines = ["📜 Recent broadcast activity:"]
            lines.extend([f"{r[2].upper()} | user {r[0]} | {r[1] or r[4]} | {r[3]}" for r in rows])
            await safe_edit_text(callback_query.message,"\\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Admin Panel", callback_data="admin_panel_main")]]))

        elif data == "admin_branding":
            if user_id != ADMIN_ID: return
            enabled = get_setting("branding_enabled", "1") == "1"
            await safe_edit_text(callback_query.message,
                f"Branding enforcement: {'ON' if enabled else 'OFF'}\\nName suffix: {REQUIRED_NAME_SUFFIX}\\nBio: {REQUIRED_BIO_TEXT}\\nChange values in .env and restart.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Toggle Branding", callback_data="admin_branding_toggle"),
                     InlineKeyboardButton("✏️ Name Suffix", callback_data="admin_branding_name")],
                    [InlineKeyboardButton("📝 Bio Text", callback_data="admin_branding_bio"),
                     InlineKeyboardButton("◀️ Admin Panel", callback_data="admin_panel_main")]
                ]))

        elif data == "admin_branding_name":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[user_id] = "waiting_branding_name"
            await safe_edit_text(callback_query.message, "Send the desired profile-name suffix (max 32 characters).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "admin_branding_bio":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[user_id] = "waiting_branding_bio"
            await safe_edit_text(callback_query.message, "Send the desired profile bio (max 70 characters).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "admin_branding_toggle":
            if user_id != ADMIN_ID: return
            enabled = get_setting("branding_enabled", "1") == "1"
            set_setting("branding_enabled", "0" if enabled else "1")
            await callback_query.answer("Branding setting updated.", show_alert=True)
            await safe_edit_text(callback_query.message,f"Branding enforcement: {'OFF' if enabled else 'ON'}", reply_markup=admin_panel_keyboard())

        elif data == "menu_autoreply":
            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT OR IGNORE INTO user_preferences(user_id) VALUES(?)", (user_id,))
            row = conn.execute("SELECT autoreply_enabled,autoreply_message,autoreply_cooldown FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
            conn.commit(); conn.close()
            await safe_edit_text(callback_query.message,
                "🤖 <b>AUTO-REPLY SETTINGS</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Status:</b> {'Enabled' if row[0] else 'Disabled'}\n"
                f"⏱ <b>Cooldown:</b> {row[2]} seconds\n"
                f"💬 <b>Reply text:</b> {row[1]}\n\n"
                "Choose an option below to configure auto-replies.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Enable / Disable", callback_data="ar_toggle"),
                     InlineKeyboardButton("✏️ Reply Message", callback_data="ar_message")],
                    [InlineKeyboardButton("⏱ Set Cooldown", callback_data="ar_cooldown"),
                     InlineKeyboardButton("◀️ Dashboard", callback_data="back_main")]
                ]))

        elif data == "ar_toggle":
            conn=sqlite3.connect(DB_FILE); conn.execute("INSERT OR IGNORE INTO user_preferences(user_id) VALUES(?)",(user_id,))
            conn.execute("UPDATE user_preferences SET autoreply_enabled=1-autoreply_enabled WHERE user_id=?",(user_id,)); conn.commit(); conn.close()
            await callback_query.answer("Auto reply setting toggled.", show_alert=True)
            await safe_edit_text(callback_query.message,"Auto reply setting updated. Open Auto Reply again to view status.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Auto Reply",callback_data="menu_autoreply")],[InlineKeyboardButton("Back",callback_data="back_main")]]))

        elif data == "ar_message":
            ADMIN_STATE[user_id]="waiting_autoreply_message"
            await safe_edit_text(callback_query.message, "Send the new automatic reply text:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "ar_cooldown":
            ADMIN_STATE[user_id]="waiting_autoreply_cooldown"
            await safe_edit_text(callback_query.message, "Send cooldown in seconds (minimum 10):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "admin_panel_main":
            if user_id != ADMIN_ID:
                await callback_query.answer("⛔ Access Denied!", show_alert=True)
                return
            current_upi = get_admin_upi() or "Not Set ❌"
            admin_text = (
                "👑 <b>ADMIN CONTROL CENTER</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Manage broadcasts, users, subscriptions and bot settings from one place.\n\n"
                "💳 <b>Payment UPI</b>\n"
                f"<code>{current_upi}</code>\n\n"
                "👇 Choose an action below"
            )
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=admin_text, reply_markup=admin_panel_keyboard())
            except Exception: 
                await safe_edit_text(callback_query.message,admin_text, reply_markup=admin_panel_keyboard())

        elif data == "admin_add_links_option":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_admin_links_msg_input"
            await safe_edit_text(callback_query.message,
                "✍️ <b>SET GLOBAL GROUPS LINKS MESSAGE</b>\n\n"
                "Send the new group-links message that users will see when they select 'Group Links'.\n"
                "You can include hyperlinks, formatted text, or other supported message formatting:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]])
            )

        elif data == "admin_set_upi":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_admin_upi_input"
            await safe_edit_text(callback_query.message, "💳 <b>SET ADMINISTRATIVE UPI ID</b>\n\nPlease send your UPI ID below:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "admin_add_new":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_new_admin_id"
            await safe_edit_text(callback_query.message, "➕ <b>ADD NEW SYSTEM ADMIN</b>\n\nPlease forward a message from the user or send their Telegram <code>User ID</code>:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "admin_broadcast_users":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_broadcast_message"
            await safe_edit_text(callback_query.message, "📢 <b>GLOBAL USER SESSIONS BROADCAST</b>\n\nThe message you send here will be delivered to groups through <b>all logged-in user accounts</b>:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "admin_bot_dm_broadcast":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_bot_dm_broadcast_msg"
            await safe_edit_text(callback_query.message, "🤖 <b>BOT DM BROADCAST SYSTEM</b>\n\nMessage all registered users by DM:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

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
                    "two_fa_pass": "",  
                    "has_premium": (u_id in premium_ids or u_id == ADMIN_ID)
                })
                
            json_str = json.dumps(backup_data, indent=4, ensure_ascii=False)
            file_buffer = io.BytesIO(json_str.encode('utf-8'))
            file_buffer.name = "system_secure_backup.json"
            
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=file_buffer,
                caption=(
                    "📁 <b>CORE SECURE DATABASE DUMP</b>\n\n"
                    f"This secure structural backup includes account records and their <b>2FA cloud-password data</b>.\n\n"
                    f"🔹 Total Accounts: <code>{len(raw_sessions)}</code>"
                )
            )
            return

        elif data == "admin_premium_panel":
            if user_id != ADMIN_ID: return
            await safe_edit_text(callback_query.message,"⭐ <b>PREMIUM ACCOUNT MANAGER</b>\n\nGive or remove premium access to users.", reply_markup=premium_management_keyboard())

        elif data == "prem_give_target":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_premium_give_uid"
            await safe_edit_text(callback_query.message,"✏️ <b>GIVE PREMIUM</b>\n\nSend the target user's Telegram <code>User ID</code> or <code>@Username</code>:")

        elif data == "prem_remove_target":
            if user_id != ADMIN_ID: return
            ADMIN_STATE[ADMIN_ID] = "waiting_premium_remove_uid"
            await safe_edit_text(callback_query.message,"✏️ <b>REMOVE PREMIUM</b>\n\nSend the target user's Telegram <code>User ID</code> or <code>@Username</code>:")

        elif data == "admin_list_premium":
            if user_id != ADMIN_ID: return
            premiums = get_premium_users()
            if not premiums:
                await callback_query.answer("📋 No active Premium users found!", show_alert=True)
                return
            
            buttons = []
            pending_row = []
            for u in premiums:
                display_name = u["username"] if u["username"] else f"UID: {u['user_id']}"
                pending_row.append(InlineKeyboardButton(f"👤 {display_name[:18]}", callback_data=f"admin_rem_p_{u['user_id']}"))
                if len(pending_row) == 2:
                    buttons.append(pending_row)
                    pending_row = []
            if pending_row:
                buttons.append(pending_row)
            buttons.append([InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel_main")])
            
            await safe_edit_text(callback_query.message,
                "📋 <b>ACTIVE PREMIUM USERS</b>\n\nHere is the list of all premium users:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data.startswith("admin_rem_p_"):
            if user_id != ADMIN_ID: return
            target_uid = int(data.split("_")[3])
            remove_premium(target_uid)
            await callback_query.answer("❌ Premium access removed successfully!", show_alert=True)
            
            premiums = get_premium_users()
            if not premiums:
                await safe_edit_text(callback_query.message,"📋 No active Premium users left.", 
                                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin_panel_main")]]))
                return
            buttons = []
            pending_row = []
            for u in premiums:
                display_name = u["username"] if u["username"] else f"UID: {u['user_id']}"
                pending_row.append(InlineKeyboardButton(f"👤 {display_name[:18]}", callback_data=f"admin_rem_p_{u['user_id']}"))
                if len(pending_row) == 2:
                    buttons.append(pending_row)
                    pending_row = []
            if pending_row:
                buttons.append(pending_row)
            buttons.append([InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel_main")])
            await safe_edit_text(callback_query.message,"📋 <b>ACTIVE PREMIUM USERS</b>\n\nUser removed. Updated list:", reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "menu_buy_premium":
            shop_text = (
                "💎 <b>UPGRADE TO PREMIUM</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Get more room to manage and grow your campaigns.\n\n"
                "🚀 <b>Unlimited connected accounts</b>\n"
                "🏷️ <b>Flexible profile branding</b>\n"
                "⚡ <b>Enhanced campaign controls</b>\n\n"
                "Choose a plan below to continue to secure payment instructions."
            )
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=shop_text, reply_markup=user_premium_shop_keyboard())
            except Exception: 
                await safe_edit_text(callback_query.message,shop_text, reply_markup=user_premium_shop_keyboard())

        elif data.startswith("buy_p_"):
            parts = data.split("_")
            amount = parts[2]
            days = parts[3]
            
            upi_address = get_admin_upi()
            if not upi_address:
                await callback_query.answer("❌ Payment System Offline: Admin UPI ID is not configured yet!", show_alert=True)
                return
                
            await safe_edit_text(callback_query.message,"⏳ Generating Payment QR Code...")
            
            encoded_name = urllib.parse.quote("Premium Ad Service")
            upi_payload = f"upi://pay?pa={upi_address}&pn={encoded_name}&am={amount}&cu=INR"
            qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_payload)}"
            
            payment_caption = (
                f"⭐ <b>ADS BOT PREMIUM INVOICE</b> ⭐\n\n"
                f"• <b>Plan Duration:</b> <code>{days} Days Premium</code> 😎\n"
                f"• <b>Payable Amount:</b> <code>₹{amount} INR</code> 💰\n"
                f"• <b>Merchant UPI ID:</b> <code>{upi_address}</code> 💳\n\n"
                f"⚠️ <b>STEPS TO ACTIVATE:</b>\n"
                f"1️⃣ Scan the QR code or send payment to the UPI address above.\n"
                f"2️⃣ Send the payment <b>Screenshot (SS)</b> directly into this chat to verify."
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
                await safe_edit_text(callback_query.message,f"✅ <b>Payment Approved.</b> User ID <code>{target_uid}</code> upgraded to Premium.")
                try:
                    await bot.send_message(
                        chat_id=target_uid,
                        text=f"🎉 <b>PAYMENT RECEIVED & VERIFIED</b>\n\nAdmin has approved your payment manually! Premium status is now active for <code>{days_pass}</code> Days! 🚀"
                    )
                except: pass
                
                USER_DATA.setdefault(target_uid, {"sessions": {}})
                for ph, cli in USER_DATA[target_uid].get("sessions", {}).items():
                    asyncio.create_task(enforce_profile_branding(cli, ph, target_uid, force_branding=True))
                
                try:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    target_user_obj = await bot.get_users(target_uid)
                    mention_str = target_user_obj.mention if target_user_obj else f"User <code>{target_uid}</code>"
                    
                    payout_text = (
                        f"📢 <b>PREMIUM REGISTRATION</b> 📢\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 <b>User:</b> {mention_str}\n"
                        f"🆔 <b>ID:</b> <code>{target_uid}</code>\n"
                        f"⏳ <b>Duration:</b> <code>{days_pass} Days Premium</code> ✨\n"
                        f"📅 <b>Date & Time:</b> <code>{now_str}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    payout_msg = await bot.send_message(chat_id=REQ_GROUP_ID, text=payout_text)
                    await payout_msg.pin(disable_notification=False)
                except Exception as e:
                    try: await log_bot.send_message(ADMIN_ID, f"⚠️ Failed to send verification log: {str(e)}")
                    except: pass
                    
            elif action == "deny":
                await safe_edit_text(callback_query.message,f"❌ <b>Payment Rejected.</b> Request deleted.")
                try:
                    await bot.send_message(
                        chat_id=target_uid,
                        text="❌ <b>PAYMENT VERIFICATION FAILED</b>\n\nAdmin has rejected your payment screenshot verification request."
                    )
                except: pass

        elif data == "menu_statistics":
            stats = get_analytics()
            total_bot_users = get_total_bot_users()
            total_added_accounts = get_total_hosted_accounts()
            total_sent = stats["messages_sent"]
            
            statistics_msg = (
                f"📊 <b>BOT SYSTEM STATISTICS</b> 📊\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 <b>Total Registered Users:</b> <code>{total_bot_users}</code>\n"
                f"🔌 <b>Total Connected Accounts:</b> <code>{total_added_accounts}</code>\n"
                f"🚀 <b>Total Ads Sent Successfully:</b> <code>{total_sent}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ *All data is synchronized live*"
            )
            kbd = InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]])
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=statistics_msg, reply_markup=kbd)
            except Exception: 
                await safe_edit_text(callback_query.message,statistics_msg, reply_markup=kbd)

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
                await safe_edit_text(callback_query.message,add_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))

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
                await safe_edit_text(callback_query.message,"Verifying login details... Please wait. ⏱️")
                asyncio.create_task(process_sign_in_engine(user_id, callback_query.message))
                return
            if action == "show_code":
                await callback_query.answer(f"Entered Code: {current_otp}", show_alert=True)
                return
            try: 
                await safe_edit_text(callback_query.message,keypad_text, reply_markup=otp_keypad_keyboard(current_otp))
            except: pass

        elif data == "menu_set_interval":
            cfg = get_config(user_id)
            int_text = f"└─ CHOOSE DELAY INTERVAL ⏱️\nCurrent Interval: {cfg['interval']}s\n\nSend custom time below in numerical seconds or pick one:"
            ADMIN_STATE[user_id] = "waiting_custom_interval"
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=int_text, reply_markup=interval_setting_keyboard())
            except Exception: 
                await safe_edit_text(callback_query.message,int_text, reply_markup=interval_setting_keyboard())

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
                await safe_edit_text(callback_query.message,db_text, reply_markup=interval_setting_keyboard())

        elif data == "menu_set_msg":
            ADMIN_STATE[user_id] = "waiting_ad_message"
            cfg = get_config(user_id)
            msg_txt = f"└─ SET AD PROMOTIONAL MESSAGE 📝\nCurrent Message:\n\n{cfg['message']}\n\n└─ Send your new promotional ad message text now:"
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=msg_txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back 🔙", callback_data="back_main")]]))
            except Exception: 
                await safe_edit_text(callback_query.message, msg_txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        elif data == "menu_start_ads":
            USER_DATA.setdefault(user_id, {"sessions": {}})
            if not USER_DATA[user_id]["sessions"]:
                await callback_query.answer("❌ You don't have any accounts added to start ads!", show_alert=True)
                return
            
            cfg = get_config(user_id)
            if cfg["running"]:
                await callback_query.answer("Ads broadcasting is already running! 🚀", show_alert=True)
                return
            
            await safe_edit_text(callback_query.message,"⏳ Verifying your log connection with Log Bot ...")
            
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
                    "🚨 <b>Log Bot Active Required!</b> 🚨\n\n"
                    "You must activate our logging bot before starting an ad campaign. "
                    "Send <code>/start</code> to the logging bot so you can receive live advertising logs. 📊\n\n"
                    "Use the button below to open the logging bot, send <code>/start</code>, then return here and try again. 👇"
                )
                try:
                    await callback_query.message.delete()
                    await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=not_started_txt, reply_markup=start_logged_bot_keyboard())
                except Exception:
                    await safe_edit_text(callback_query.message,not_started_txt, reply_markup=start_logged_bot_keyboard())
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
                await log_bot.send_message(chat_id=user_id, text="⚠️ <b>Advertising Status Sync: Paused</b> ⏸️")
            except: pass

        elif data in ["menu_my_acc", "menu_del_acc"]:
            USER_DATA.setdefault(user_id, {"sessions": {}})
            accounts = list(USER_DATA[user_id]["sessions"].keys())
            if not accounts:
                await callback_query.answer("No accounts connected yet! Please add one. 🔑", show_alert=True)
                return
            txt = "└─ CURRENT LOGGED-IN ACCOUNTS 👥\n\n"
            for idx, name in enumerate(accounts, 1):
                client_obj = USER_DATA[user_id]["sessions"].get(name)
                try:
                    connected = bool(client_obj and client_obj.is_connected and await client_obj.get_me())
                except Exception:
                    connected = False
                txt += f"{idx}. {name} - Status: {'Connected ✅' if connected else 'Disconnected ⚠️'}\\n"
            buttons = [[InlineKeyboardButton("Delete All Accounts ❌", callback_data="clear_all_nodes")], [InlineKeyboardButton("Back 🔙", callback_data="back_main")]]
            try:
                await callback_query.message.delete()
                await bot.send_photo(chat_id=user_id, photo=MEDIA_IMAGE_LINK, caption=txt, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception: 
                await safe_edit_text(callback_query.message,txt, reply_markup=InlineKeyboardMarkup(buttons))

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
    if get_setting("maintenance_mode", "0") == "1" and user_id != ADMIN_ID:
        await message.reply_text("🛠 Bot is temporarily under maintenance. Please try again later.")
        return
    
    if not await check_force_join(client, user_id): 
        fj_text = (
            "🚨 <b>Access Restricted / Join Required</b> 🚨\n\n"
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
                f"🔔 <b>NEW USER PAYMENT SCREENSHOT RECOVERY</b> 🔔\n\n"
                f"• <b>User:</b> {message.from_user.mention}\n"
                f"• <b>User ID:</b> <code>{user_id}</code>\n"
                f"• <b>Paid Amount:</b> <code>₹{amt} INR</code> 💰\n"
                f"• <b>Requested Plan:</b> <code>{days_pass} Days Premium Pass</code> ⭐"
            ),
            reply_markup=review_keyboard
        )
        await message.reply_text("✅ <b>Screenshot received successfully!</b> Admin will verify and activate your plan shortly.")
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
            
            await safe_edit_text(status_msg,
                f"✅ <b>RESTORE COMPLETE</b>\n\n"
                f"🔹 Imported <code>{success_count}</code> accounts back into database structure.\n"
                f"🔑 Mapped 2FA keys have been dynamically linked."
            )
            await load_saved_sessions_from_db()
        except Exception as e:
            await safe_edit_text(status_msg,f"❌ <b>Restoration Failed:</b> <code>{str(e)}</code>")
        finally:
            if os.path.exists(file_path): os.remove(file_path)
        return

    if user_id == ADMIN_ID and state in ("waiting_branding_name", "waiting_branding_bio") and message.text:
        value = message.text.strip()
        if state == "waiting_branding_name" and len(value) > 32:
            await message.reply_text("Name suffix must be 32 characters or fewer."); return
        if state == "waiting_branding_bio" and len(value) > 70:
            await message.reply_text("Bio must be 70 characters or fewer."); return
        set_setting("branding_name_suffix" if state == "waiting_branding_name" else "branding_bio_text", value)
        ADMIN_STATE.pop(user_id, None)
        await message.reply_text("✅ Branding setting saved.", reply_markup=admin_panel_keyboard()); return

    if state == "waiting_autoreply_message" and message.text:
        conn=sqlite3.connect(DB_FILE); conn.execute("INSERT OR IGNORE INTO user_preferences(user_id) VALUES(?)",(user_id,))
        conn.execute("UPDATE user_preferences SET autoreply_message=? WHERE user_id=?",(message.text[:4000],user_id)); conn.commit(); conn.close()
        ADMIN_STATE.pop(user_id,None)
        await message.reply_text("✅ Auto reply message saved.",reply_markup=main_menu_keyboard(user_id)); return
    if state == "waiting_autoreply_cooldown" and message.text:
        if not message.text.isdigit() or int(message.text)<10:
            await message.reply_text("Enter a number of at least 10 seconds."); return
        conn=sqlite3.connect(DB_FILE); conn.execute("INSERT OR IGNORE INTO user_preferences(user_id) VALUES(?)",(user_id,))
        conn.execute("UPDATE user_preferences SET autoreply_cooldown=? WHERE user_id=?",(int(message.text),user_id)); conn.commit(); conn.close()
        ADMIN_STATE.pop(user_id,None)
        await message.reply_text("✅ Auto reply cooldown saved.",reply_markup=main_menu_keyboard(user_id)); return

    if not state: return

    if user_id == ADMIN_ID and state == "waiting_admin_links_msg_input" and message.text:
        set_admin_group_links_msg(message.text)
        ADMIN_STATE.pop(ADMIN_ID, None)
        await message.reply_text("✅ <b>Global Groups Links Message dynamically updated successfully!</b>", reply_markup=admin_panel_keyboard())
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
                f"✅ <b>EXCEPTION GROUP ADDED SUCCESSFULLY</b>\n\n"
                f"Bot safely configured. Target ID <code>{target_chat_id}</code> has been appended to bypass list. "
                f"Automation will now be disabled for this group.",
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
            await message.reply_text(f"✅ <b>UPI PATH UPDATED</b>\n\nYour public payment destination UPI ID is now set to: <code>{raw_upi}</code> 💳")
            return

        elif state == "waiting_new_admin_id" and message.text:
            target_admin = None
            if message.forward_date and message.forward_from:
                target_admin = message.forward_from.id
            elif message.text and message.text.strip().isdigit():
                target_admin = int(message.text.strip())
                
            ADMIN_STATE.pop(ADMIN_ID, None)
            if target_admin:
                await message.reply_text(f"✅ <b>New Admin configured successfully!</b> User ID <code>{target_admin}</code> has been registered as assistant administrator.")
            else:
                await message.reply_text("❌ <b>Invalid Input:</b> Failed to parse a valid user ID. Admin addition cancelled.")
            return
            
        elif state == "waiting_broadcast_message":
            ADMIN_STATE.pop(ADMIN_ID, None)
            progress_msg = await message.reply_text("⏳ Gathering all logged-in user accounts from memory...")
            
            all_clients = []
            for u_id, u_info in USER_DATA.items():
                for ph, cli in u_info.get("sessions", {}).items():
                    all_clients.append((ph, cli, u_id))
                    
            if not all_clients:
                await safe_edit_text(progress_msg,"❌ Action cancelled: No user accounts are currently logged in to the bot!")
                return
                
            cancel_event = asyncio.Event()
            ACTIVE_TASKS["admin_broadcast"] = cancel_event
            cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Broadcast", callback_data="cancel_admin_task")]])
            await safe_edit_text(progress_msg, f"🚀 Found <code>{len(all_clients)}</code> active profiles. Broadcasting...", reply_markup=cancel_kb)
            total_sent_broad = 0
            
            for ph, session_cli, owner_uid in all_clients:
                if cancel_event.is_set(): break
                try:
                    async for dialog in session_cli.get_dialogs():
                        if cancel_event.is_set(): break
                        if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                            try:
                                await message.copy(chat_id=dialog.chat.id)
                                total_sent_broad += 1
                                
                                try:
                                    await log_bot.send_message(
                                        chat_id=owner_uid,
                                        text=f"📢 <b>[ADMIN FORCE BROADCAST]</b> Sent successfully to {dialog.chat.title} using your account ({ph})"
                                    )
                                except: pass
                                
                                try:
                                    await asyncio.wait_for(cancel_event.wait(), timeout=1.5)
                                except asyncio.TimeoutError:
                                    pass
                            except FloodWait as fw: 
                                try:
                                    await asyncio.wait_for(cancel_event.wait(), timeout=fw.value)
                                except asyncio.TimeoutError:
                                    pass
                            except Exception as e:
                                try:
                                    await log_bot.send_message(
                                        chat_id=owner_uid,
                                        text=f"❌ <b>[ADMIN FORCE BROADCAST]</b> Failed in {dialog.chat.title or 'Group'}: {str(e)[:100]}"
                                    )
                                except: pass
                except: pass
                
            ACTIVE_TASKS.pop("admin_broadcast", None)
            final_state = "CANCELLED" if cancel_event.is_set() else "COMPLETE"
            await safe_edit_text(progress_msg, f"👑 <b>ADMIN SESSIONS BROADCAST {final_state}</b>\n\nSent: <code>{total_sent_broad}</code> groups.")
            return

        elif state == "waiting_bot_dm_broadcast_msg":
            ADMIN_STATE.pop(ADMIN_ID, None)
            progress_msg = await message.reply_text("⏳ Fetching all registered users from database...")
            
            user_ids = get_all_bot_user_ids()
            if not user_ids:
                await safe_edit_text(progress_msg,"❌ No users were found in the database!")
                return
                
            cancel_event = asyncio.Event()
            ACTIVE_TASKS["admin_broadcast"] = cancel_event
            cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Broadcast", callback_data="cancel_admin_task")]])
            await safe_edit_text(progress_msg, f"🤖 Total <code>{len(user_ids)}</code> users. DM broadcast started...", reply_markup=cancel_kb)
            success_count = 0
            fail_count = 0
            
            for u_id in user_ids:
                if cancel_event.is_set(): break
                try:
                    await message.copy(chat_id=u_id)
                    record_broadcast(ADMIN_ID, "bot", u_id, f"DM user {u_id}", "success")
                    success_count += 1
                    try:
                        await asyncio.wait_for(cancel_event.wait(), timeout=0.3)
                    except asyncio.TimeoutError:
                        pass
                except FloodWait as fw:
                    try:
                        await asyncio.wait_for(cancel_event.wait(), timeout=fw.value)
                    except asyncio.TimeoutError:
                        pass
                    if cancel_event.is_set():
                        break
                    try:
                        await message.copy(chat_id=u_id)
                        success_count += 1
                    except:
                        fail_count += 1
                except Exception:
                    fail_count += 1
                    
            ACTIVE_TASKS.pop("admin_broadcast", None)
            final_state = "CANCELLED" if cancel_event.is_set() else "COMPLETE"
            await safe_edit_text(progress_msg,
                f"✅ <b>BOT DM BROADCAST {final_state}</b>\n\n"
                f"• Total Success: <code>{success_count}</code> Users\n"
                f"• Total Failed/Blocked: <code>{fail_count}</code> Users"
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
                    await message.reply_text("❌ <b>User Not Found Error:</b> Please use User ID for manual admin method.")
                    ADMIN_STATE.pop(ADMIN_ID, None)
                    return
            ADMIN_STATE[ADMIN_ID] = f"waiting_premium_days_{user_info['user_id']}"
            await message.reply_text(f"✅ User Checked: <code>{user_info['username'] or user_info['user_id']}</code>\n\nEnter number of premium validity days:")
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
            await message.reply_text(f"⭐ Premium Access granted for <code>{days}</code> days successfully!")
            try: await bot.send_message(chat_id=target_uid, text=f"🎉 <b>CONGRATULATIONS!</b> Admin has activated your Premium features for <code>{days}</code> days! 🚀")
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
            await message.reply_text(f"❌ <b>PREMIUM ACCESS REVOKED</b> from user ID <code>{user_info['user_id']}</code>.")
            
            USER_DATA.setdefault(user_info['user_id'], {"sessions": {}})
            for ph, cli in USER_DATA[user_info['user_id']]["sessions"].items():
                asyncio.create_task(enforce_profile_branding(cli, ph, user_info['user_id'], force_branding=True))
            return

    # --- USER ACCOUNT CONNECT ACTIONS ---
    if state == "waiting_phone_number" and message.text:
        phone = message.text.strip().replace(" ", "")
        status_msg = await message.reply_text("Connecting to Telegram login servers... Please wait ⏱️")
        temp_session_name = f"session_{user_id}_{int(asyncio.get_event_loop().time())}"
        temp_cli = Client(temp_session_name, api_id=API_ID, api_hash=API_HASH, in_memory=True, parse_mode=enums.ParseMode.HTML)
        await temp_cli.connect()
        try:
            code_hash = await temp_cli.send_code(phone)
            AUTH_TEMP[user_id] = {"client": temp_cli, "phone": phone, "hash": code_hash.phone_code_hash, "otp_stream": "", "two_fa_backup_key": ""}
            ADMIN_STATE[user_id] = "waiting_otp_keypad"
            await status_msg.delete()
            await message.reply_text(f"└─ OTP sent to {phone}! ✅\nPlease type your code using the custom keyboard layout below:", reply_markup=otp_keypad_keyboard())
        except Exception as err:
            try:
                if temp_cli.is_connected: await temp_cli.disconnect()
            except Exception: pass
            AUTH_TEMP.pop(user_id, None)
            ADMIN_STATE.pop(user_id, None)
            await safe_edit_text(status_msg,f"❌ Login Handshake Failed: {str(err)}")

    elif state == "waiting_2fa_password" and message.text:
        pwd = message.text.strip()
        status_msg = await message.reply_text("Checking Two-Step Verification cloud password... 🔒")
        temp_cli = AUTH_TEMP[user_id]["client"]
        phone = AUTH_TEMP[user_id]["phone"]
        try:
            await temp_cli.check_password(pwd)
            USER_DATA.setdefault(user_id, {"sessions": {}})
            USER_DATA[user_id]["sessions"][phone] = temp_cli
            register_autoreply_handler(temp_cli)
            AUTH_TEMP.pop(user_id, None)
            ADMIN_STATE.pop(user_id, None)
            
            exported_string = await temp_cli.export_session_string()
            db_save_session(phone, user_id, exported_string, pwd) 
            
            try: await temp_cli.send_message(chat_id="YourBotUsername", text="/start")
            except: pass
            try: await temp_cli.send_message(chat_id="YourLoggerBotUsername", text="/start")
            except: pass
                
            await message.reply_text(f"└─ Account linked successfully! ✅\nPhone: {phone}", reply_markup=main_menu_keyboard(user_id))
        except Exception as e: await safe_edit_text(status_msg,f"❌ Incorrect Password: {str(e)}\nPlease try again:")

    elif state == "waiting_ad_message" and message.text:
        update_config(user_id, "ad_message", message.text)
        ADMIN_STATE.pop(user_id, None)
        await message.reply_text("✅ New promotional ad message layout saved successfully!", reply_markup=main_menu_keyboard(user_id))

    elif state == "waiting_custom_interval" and message.text:
        if message.text.isdigit():
            val = int(message.text)
            update_config(user_id, "interval_delay", val)
            ADMIN_STATE.pop(user_id, None)
            await message.reply_text(f"✅ Broadcast sleep timer custom interval set to <code>{val}</code> seconds!", reply_markup=main_menu_keyboard(user_id))
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
        register_autoreply_handler(temp_cli)
        AUTH_TEMP.pop(user_id, None)
        ADMIN_STATE.pop(user_id, None)
        
        exported_string = await temp_cli.export_session_string()
        db_save_session(phone, user_id, exported_string, "") 
        
        try: await temp_cli.send_message(chat_id="YourBotUsername", text="/start")
        except: pass
        try: await temp_cli.send_message(chat_id="YourLoggerBotUsername", text="/start")
        except: pass
            
        await safe_edit_text(msg_target,f"└─ Account successfully paired! ✅\n\nPhone Number: {phone}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Dashboard 📊", callback_data="back_main")]]))
    except SessionPasswordNeeded:
        ADMIN_STATE[user_id] = "waiting_2fa_password"
        await safe_edit_text(msg_target,"🔒 <b>Two-Step Verification Cloud Security Active!</b>\n\nPlease send your Telegram cloud protection password below:")
    except (PhoneCodeInvalid, PhoneCodeExpired):
        await msg_target.delete()
        temp = AUTH_TEMP.pop(user_id, None)
        if temp and temp.get("client"):
            try:
                if temp["client"].is_connected: await temp["client"].disconnect()
            except Exception: pass
        await bot.send_message(user_id, "❌ Verification code is invalid or timed out. Temporary login session cleaned; please retry.")
        ADMIN_STATE.pop(user_id, None)

# Register one private-message auto-reply handler per connected user session.
_AUTOREPLY_REGISTERED = set()
async def auto_reply_handler(client_instance, message):
    if not message.from_user or message.from_user.is_bot or message.from_user.is_self:
        return
    owner_id = None
    for uid, data in USER_DATA.items():
        if client_instance in data.get("sessions", {}).values():
            owner_id = uid
            break
    if owner_id is None:
        return
    conn=sqlite3.connect(DB_FILE, timeout=15)
    row=conn.execute("SELECT autoreply_enabled,autoreply_message,autoreply_cooldown FROM user_preferences WHERE user_id=?",(owner_id,)).fetchone()
    if not row or not row[0]:
        conn.close(); return
    now=time.time()
    last=conn.execute("SELECT last_reply FROM autoreply_tracking WHERE user_id=? AND sender_id=?",(owner_id,message.from_user.id)).fetchone()
    if last and now-last[0] < row[2]:
        conn.close(); return
    conn.execute("INSERT INTO autoreply_tracking(user_id,sender_id,last_reply) VALUES(?,?,?) ON CONFLICT(user_id,sender_id) DO UPDATE SET last_reply=excluded.last_reply",
                 (owner_id,message.from_user.id,now))
    conn.commit(); conn.close()
    try:
        await client_instance.send_message(message.chat.id, row[1], reply_to_message_id=message.id, parse_mode=enums.ParseMode.DISABLED)
    except Exception as exc:
        logging.warning("Auto reply failed for owner %s: %s",owner_id,exc)

def register_autoreply_handler(client_instance):
    marker=id(client_instance)
    if marker not in _AUTOREPLY_REGISTERED:
        client_instance.add_handler(MessageHandler(auto_reply_handler, filters.private & filters.incoming), group=7)
        _AUTOREPLY_REGISTERED.add(marker)

# --- BRANDING VERIFIER ---
async def enforce_profile_branding(client_instance: Client, phone: str, user_id: int, force_branding: bool = False) -> bool:
    try:
        if get_setting("branding_enabled", "1") != "1":
            return True
        name_suffix = get_setting("branding_name_suffix", REQUIRED_NAME_SUFFIX)
        bio_text = get_setting("branding_bio_text", REQUIRED_BIO_TEXT)
        me = await client_instance.get_me()
        
        if is_user_premium(user_id):
            full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            if name_suffix in full_name:
                cleaned_first = (me.first_name or "").replace(name_suffix, "").strip()
                if not cleaned_first: cleaned_first = "User"
                await client_instance.update_profile(first_name=cleaned_first)
                await asyncio.sleep(1)
            
            full_chat = await client_instance.get_chat(me.id)
            if full_chat.bio == bio_text:
                await client_instance.update_profile(bio="")
                await asyncio.sleep(1)
            return True 
            
        full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        if name_suffix not in full_name:
            new_first = me.first_name or "User"
            if len(new_first) + len(name_suffix) > 64:
                new_first = new_first[:(64 - len(name_suffix))]
            await client_instance.update_profile(first_name=f"{new_first}{name_suffix}")
            try:
                await log_bot.send_message(chat_id=user_id, text=f"⚙️ <b>Name Auto-Updated</b> for {phone} -> Added branding suffix.")
            except: pass
            await asyncio.sleep(1.5)

        full_chat = await client_instance.get_chat(me.id)
        current_bio = full_chat.bio or ""
        
        if current_bio.strip() != bio_text.strip():
            try:
                await client_instance.update_profile(bio=bio_text)
                try:
                    await log_bot.send_message(chat_id=user_id, text=f"⚙️ <b>Bio Auto-Updated</b> for {phone} -> Forced branding layout.")
                except: pass
                await asyncio.sleep(1.5)
            except Exception as bio_err:
                print(f"Bio fallback triggered for {phone}: {bio_err}")
                await client_instance.update_profile(bio="")
                await asyncio.sleep(1)
                await client_instance.update_profile(bio=bio_text)
                
        return True

    except (AuthKeyUnregistered, SessionExpired, UserDeactivatedBan):
        print(f"[⚠️] Session expired/unregistered for phone {phone}. Auto-cleaning...")
        try:
            await log_bot.send_message(
                chat_id=user_id,
                text=f"🚨 <b>Session Expired / Logged Out:</b>\n\nYour connected account <code>{phone}</code> has been logged out from Telegram servers.\n\n❌ <b>Action:</b> This account has been removed from database."
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
                await log_bot.send_message(chat_id=user_id, text=f"🚨 Account <code>{phone}</code> disconnected by Telegram. Re-login required.")
            except: pass
            return False
            
        try: await log_bot.send_message(ADMIN_ID, f"⚠️ Branding check failure on user <code>{phone}</code>: {str(e)}")
        except: pass
        return False

# --- ADS BROADCAST SCHEDULER LOOP WITH EXCEPTION FILTERS 🔄 ---
async def run_ads_broadcast(user_id):
    cfg = get_config(user_id)
    try:
        await log_bot.send_message(
            chat_id=user_id, 
            text=f"🚀 <b>Broadcast started! Logs will sync here</b>\nInterval delay: {cfg['interval']} seconds (Safe)"
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
                                
                            await client_instance.send_message(dialog.chat.id, ad_payload, parse_mode=enums.ParseMode.DISABLED)
                            record_broadcast(user_id, phone, dialog.chat.id, dialog.chat.title or "Group", "success")
                            increment_analytics("messages_sent")
                            
                            try:
                                await log_bot.send_message(
                                    chat_id=user_id, 
                                    text=f"✅ <b>Sent to {dialog.chat.title}</b> ({dialog.chat.id}) using account {phone}"
                                )
                            except: pass

                        except FloodWait as fw:
                            record_broadcast(user_id, phone, dialog.chat.id, dialog.chat.title or "Group", "pending", f"FloodWait {fw.value}s")
                            await asyncio.sleep(fw.value)
                        except (PeerIdInvalid, ValueError) as p_err:
                            print(f"⚠️ Handled invalid group target peer ID: {p_err}")
                            continue
                        except (OSError, IOError) as socket_err:
                            print(f"🔥 Socket Drop Handled for {phone}: {socket_err}. Pausing node for 10s...")
                            await asyncio.sleep(10)
                            break
                        except Exception as error:
                            record_broadcast(user_id, phone, dialog.chat.id, dialog.chat.title or "Group", "failed", str(error))
                            increment_analytics("failed_sends")
                            
                            try:
                                await log_bot.send_message(
                                    chat_id=user_id, 
                                    text=f"❌ <b>Failed to send to {dialog.chat.title or 'Group'}</b> ({dialog.chat.id}): Telegram says: {str(error)[:150]}"
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
                        text=f"⚠️ <b>Automated sequence warning:</b> {str(loop_err)[:100]}"
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
                client_instance = Client(f"session_{phone}", api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True, parse_mode=enums.ParseMode.HTML)
                await client_instance.start()
                USER_DATA[user_id]["sessions"][phone] = client_instance
                register_autoreply_handler(client_instance)
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
        print("Refusing destructive reset. Use --backup to create a backup; migrations are automatic.")
        sys.exit(2)
    if len(sys.argv) > 1 and sys.argv[1] == "--backup":
        print(backup_database() or "No database exists yet.")
        sys.exit(0)
        
    await bot.start()
    await log_bot.start()
    
    await load_saved_sessions_from_db()
    
    print("🚀 System completely running with automated multi-account premium detection system!")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
