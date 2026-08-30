import os
import re
import time
import html
import subprocess
import telebot
from telebot import types

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN nahi mila! Railway variables me BOT_TOKEN set karein.")

bot = telebot.TeleBot(BOT_TOKEN)
user_login_data = {}

def strip_ansi(text):
    """Terminal ke hidden color codes ko hatane ke liye"""
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def run_cmd(args, timeout=180, input_data="yes\nyes\nyes\n"):
    """Subprocess runner jo Terms/Prompts ko automatically 'yes' bhejta hai"""
    try:
        res = subprocess.run(
            args,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        clean_stdout = strip_ansi(res.stdout.strip())
        clean_stderr = strip_ansi(res.stderr.strip())
        return clean_stdout, clean_stderr, res.returncode
    except subprocess.TimeoutExpired:
        return "", "Command Timed Out", 1
    except Exception as e:
        return "", str(e), 1

def extract_mega_link(text):
    """Output me se clean MEGA share link nikalne ke liye regex"""
    cleaned = strip_ansi(text)
    patterns = [
        r'(https?://mega\.nz/folder/[a-zA-Z0-9_-]+#[a-zA-Z0-9_-]+)',
        r'(https?://mega\.nz/file/[a-zA-Z0-9_-]+#[a-zA-Z0-9_-]+)',
        r'(https?://mega\.nz/#F\![a-zA-Z0-9_-]+\![a-zA-Z0-9_-]+)',
        r'(https?://mega\.nz/\#[a-zA-Z0-9_-]+\![a-zA-Z0-9_-]+)',
        r'(https?://mega\.(?:nz|co\.nz)/(?:folder/|file/|#F!|#!)[a-zA-Z0-9_#-]+)',
        r'(https?://mega\.(?:nz|co\.nz)/[^\s"\'<>\)\],]+)'
    ]
    for pat in patterns:
        m = re.search(pat, cleaned)
        if m:
            return m.group(1).rstrip('.:;,\'")]}>')
    return None

def export_and_get_link(target_name):
    """Guaranteed Share Link Fetch Engine"""
    clean_name = target_name.strip().strip("'\"").strip("/")
    target_path = f"/{clean_name}"

    time.sleep(2)

    # 1. Direct Export command with Auto-Yes
    out1, err1, _ = run_cmd(["mega-export", "-a", target_path])
    link = extract_mega_link(out1 + " " + err1)
    if link:
        return link, clean_name

    # 2. Query target export path
    time.sleep(1)
    out2, err2, _ = run_cmd(["mega-export", target_path])
    link = extract_mega_link(out2 + " " + err2)
    if link:
        return link, clean_name

    # 3. List all exports and search
    out3, _, _ = run_cmd(["mega-export"])
    for line in out3.splitlines():
        if clean_name.lower() in line.lower():
            link = extract_mega_link(line)
            if link:
                return link, clean_name

    # 4. Re-export (Delete and create fresh)
    run_cmd(["mega-export", "-d", target_path])
    time.sleep(1)
    out4, err4, _ = run_cmd(["mega-export", "-a", target_path])
    link = extract_mega_link(out4 + " " + err4)
    if link:
        return link, clean_name

    # 5. Last active export fallback
    lines = [l.strip() for l in out3.splitlines() if l.strip()]
    if lines:
        for l in reversed(lines):
            link = extract_mega_link(l)
            if link:
                return link, clean_name

    return None, clean_name

# Telegram Menu setup
try:
    bot.set_my_commands([
        types.BotCommand("login", "MEGA account login karein (Step-by-step)"),
        types.BotCommand("logout", "Account logout karein"),
        types.BotCommand("status", "Check login status & user email"),
        types.BotCommand("cancel", "Chal rahe process ko cancel karein"),
        types.BotCommand("help", "Bot use karne ki guide")
    ])
except Exception as e:
    print(f"Menu setup notice: {e}")

# Daemon startup
print("🔄 Initializing MEGAcmd server...")
run_cmd(["mega-version"])
time.sleep(2)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "📁 <b>MEGA Auto-Importer & Share Bot</b>\n\n"
        "Ye bot direct <b>Folder Links</b> ko cloud drive me add karke uska naya share link generate karta hai.\n\n"
        "<b>📌 Menu Commands:</b>\n"
        "🔹 <code>/login</code> — MEGA account login karein\n"
        "🔹 <code>/logout</code> — Active account logout karein\n"
        "🔹 <code>/status</code> — Active email check karein\n"
        "🔹 <code>/cancel</code> — Process cancel karein\n\n"
        "<b>Kaise use karein:</b>\n"
        "1️⃣ <code>/login</code> par click karein aur apna Email/Password dein.\n"
        "2️⃣ Login hone ke baad koi bhi <b>MEGA Folder Link</b> bhej dein."
    )
    bot.reply_to(message, welcome_text, parse_mode="HTML")

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    user_login_data.pop(message.chat.id, None)
    bot.reply_to(message, "🚫 Current process cancel ho gaya hai.")

# ----------------- STEP-BY-STEP LOGIN -----------------
@bot.message_handler(commands=['login'])
def start_login(message):
    chat_id = message.chat.id
    user_login_data[chat_id] = {'step': 'EMAIL'}
    
    msg = bot.reply_to(
        message,
        "📧 <b>Step 1/2:</b> Kripya apna <b>MEGA Email Address</b> bhejein:\n\n<i>(Cancel karne ke liye /cancel bhejein)</i>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_email_step)

def process_email_step(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if text.startswith('/cancel'):
        user_login_data.pop(chat_id, None)
        bot.reply_to(message, "🚫 Login process cancel ho gaya.")
        return

    if text.startswith('/'):
        bot.reply_to(message, "⚠️ Pehle <code>/login</code> dobara karein ya <code>/cancel</code> karein.", parse_mode="HTML")
        return

    if "@" not in text or "." not in text:
        msg = bot.reply_to(message, "❌ <b>Galat Email!</b> Sahi email bhejein:\n\n<i>(Cancel ke liye /cancel)</i>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_email_step)
        return

    user_login_data[chat_id] = {'email': text, 'step': 'PASSWORD'}

    msg = bot.reply_to(
        message,
        f"🔑 <b>Step 2/2:</b> Email <code>{html.escape(text)}</code> ke liye <b>MEGA Password</b> bhejein:\n\n<i>(Suraksha ke liye password chat se delete ho jayega)</i>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_password_step)

def process_password_step(message):
    chat_id = message.chat.id
    password = message.text.strip()

    if password.startswith('/cancel'):
        user_login_data.pop(chat_id, None)
        bot.reply_to(message, "🚫 Login process cancel ho gaya.")
        return

    try:
        bot.delete_message(chat_id, message.message_id)
    except Exception:
        pass

    state = user_login_data.get(chat_id, {})
    email = state.get('email')

    if not email:
        bot.reply_to(message, "⚠️ Session expire ho gaya. Kripya <code>/login</code> phirse karein.", parse_mode="HTML")
        return

    status_msg = bot.send_message(chat_id, "🔄 <b>MEGA Account verify kiya ja raha hai...</b>", parse_mode="HTML")

    run_cmd(["mega-logout"])
    stdout, stderr, code = run_cmd(["mega-login", email, password], timeout=40)
    user_login_data.pop(chat_id, None)

    if code == 0:
        bot.edit_message_text(
            f"✅ <b>MEGA Login Safal Raha!</b>\n\n👤 <b>Logged in as:</b> <code>{html.escape(email)}</code>\n\nAb aap koi bhi <b>MEGA Folder Link</b> bhej sakte hain!",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )
    else:
        err = stderr if stderr else stdout
        bot.edit_message_text(
            f"❌ <b>Login Fail:</b>\n<code>{html.escape(err)}</code>\n\n👉 <i>Dhyan rahe Email/Password sahi ho aur MEGA par 2FA off ho.</i>\nDobara try karne ke liye <code>/login</code> bhejein.",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

# ----------------- LOGOUT -----------------
@bot.message_handler(commands=['logout'])
def handle_logout(message):
    msg = bot.reply_to(message, "🔄 Logout ho raha hai...")
    stdout, stderr, code = run_cmd(["mega-logout"])
    
    if code == 0 or "Logged out" in stdout or "Not logged in" in stderr:
        bot.edit_message_text(
            "🚪 <b>Successfully Logged Out!</b>\nAapka MEGA session clear ho gaya hai.",
            chat_id=message.chat.id,
            message_id=msg.message_id,
            parse_mode="HTML"
        )
    else:
        bot.edit_message_text(
            f"❌ Logout Error: <code>{html.escape(stderr if stderr else stdout)}</code>",
            chat_id=message.chat.id,
            message_id=msg.message_id,
            parse_mode="HTML"
        )

# ----------------- STATUS -----------------
@bot.message_handler(commands=['status', 'whoami'])
def handle_status(message):
    out, _, code = run_cmd(["mega-whoami"])
    if code == 0 and out:
        bot.reply_to(
            message, 
            f"🟢 <b>Account Status: LOGGED IN</b>\n\n<code>{html.escape(out)}</code>", 
            parse_mode="HTML"
        )
    else:
        bot.reply_to(
            message, 
            "🔴 <b>Account Status: NOT LOGGED IN</b>\n\nKripya <code>/login</code> command se login karein.", 
            parse_mode="HTML"
        )

# ----------------- LINK PROCESSOR -----------------
@bot.message_handler(func=lambda message: True)
def handle_mega_url(message):
    url = message.text.strip()
    
    if message.chat.id in user_login_data:
        bot.reply_to(message, "⚠️ Pehle apna login process poora karein ya <code>/cancel</code> karein.", parse_mode="HTML")
        return

    if "mega.nz" not in url and "mega.co.nz" not in url:
        bot.reply_to(message, "⚠️ Kripya ek valid MEGA link bhejein ya <code>/help</code> check karein.", parse_mode="HTML")
        return

    # Check login
    who_out, _, who_code = run_cmd(["mega-whoami"])
    if who_code != 0 or not who_out:
        bot.reply_to(
            message, 
            "⚠️ <b>Aap logged in nahi hain!</b>\nPehle <code>/login</code> par click karke login karein.", 
            parse_mode="HTML"
        )
        return

    status_msg = bot.reply_to(message, "⏳ <b>Folder ko Cloud Drive me import kiya ja raha hai...</b>")

    try:
        # Pre-import snapshot
        ls_before, _, _ = run_cmd(["mega-ls", "/"])
        before_set = set([x.strip().strip("'\"").strip("/") for x in ls_before.splitlines() if x.strip()])
        
        # Import folder
        imp_out, imp_err, imp_code = run_cmd(["mega-import", url, "/"], timeout=180)
        
        if imp_code != 0:
            bot.edit_message_text(
                f"❌ <b>Import Failed:</b>\n<code>{html.escape(imp_err if imp_err else imp_out)}</code>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            return

        bot.edit_message_text(
            "⏳ <b>Drive me save ho gaya!</b> Ab Share Link generate kiya ja raha hai...",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

        target_name = None

        # 1. Exact match from import stdout
        m_name = re.search(r'Imported.*?:?\s*/([^\r\n/]+)', imp_out + " " + imp_err, re.IGNORECASE)
        if m_name:
            target_name = m_name.group(1).strip().strip("'\"").strip("/")

        # 2. Match from directory diff
        if not target_name:
            for _ in range(4):
                time.sleep(2)
                ls_after, _, _ = run_cmd(["mega-ls", "/"])
                after_set = set([x.strip().strip("'\"").strip("/") for x in ls_after.splitlines() if x.strip()])
                new_items = list(after_set - before_set)
                if new_items:
                    target_name = new_items[0]
                    break

        # 3. Fallback to latest item
        if not target_name:
            ls_all, _, _ = run_cmd(["mega-ls", "/"])
            all_items = [x.strip().strip("'\"").strip("/") for x in ls_all.splitlines() if x.strip()]
            if all_items:
                target_name = all_items[-1]

        if not target_name:
            bot.edit_message_text(
                "⚠️ Item add ho gaya, par folder identify nahi ho saka.",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
            return

        # Export & fetch share link
        share_link, final_name = export_and_get_link(target_name)

        if share_link:
            bot.edit_message_text(
                f"✅ <b>Successfully Drive Mein Add Ho Gaya!</b>\n\n"
                f"📁 <b>Folder Name:</b> <code>{html.escape(final_name)}</code>\n\n"
                f"🔗 <b>Aapka Naya Share Link:</b>\n{share_link}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
        else:
            bot.edit_message_text(
                f"⚠️ Folder <code>{html.escape(final_name)}</code> Drive me add ho gaya hai, par link fetch nahi ho saka.",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )

    except Exception as e:
        bot.edit_message_text(
            f"❌ <b>Error:</b> {html.escape(str(e))}", 
            chat_id=message.chat.id, 
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

print("🤖 MEGA Folder Bot 100% Ready and Polling...")
bot.infinity_polling()
