import os
import re
import time
import html
import subprocess
import telebot

# Railway Environment Variable se Token lena
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN nahi mila! Railway variables me BOT_TOKEN add karein.")

bot = telebot.TeleBot(BOT_TOKEN)

def run_cmd(args, timeout=180):
    """Subprocess command runner bina kisi shell injection issue ke"""
    try:
        res = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except subprocess.TimeoutExpired:
        return "", "Command Timed Out", 1
    except Exception as e:
        return "", str(e), 1

# Background MEGAcmd engine start karna
print("🔄 Initializing MEGAcmd server daemon...")
run_cmd(["mega-version"])
time.sleep(2)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "📁 <b>MEGA Folder & File Importer Bot</b>\n\n"
        "<b>Available Commands:</b>\n"
        "🔹 <code>/login email password</code> — MEGA me login karein\n"
        "🔹 <code>/logout</code> — Active session logout karein\n"
        "🔹 <code>/status</code> — Check karein kaunsa account login hai\n\n"
        "<b>Kaise Use Karein:</b>\n"
        "1. Pehle <code>/login</code> command se account login karein.\n"
        "2. Koi bhi <b>MEGA Folder Link</b> ya File Link bhejein.\n"
        "3. Bot direct cloud drive me add karke <b>Naya Share Link</b> dedega."
    )
    bot.reply_to(message, welcome_text, parse_mode="HTML")

# ----------------- LOGIN -----------------
@bot.message_handler(commands=['login'])
def handle_login(message):
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) != 3:
            bot.reply_to(
                message, 
                "❌ <b>Format galat hai!</b>\nSahi format:\n<code>/login your_email@gmail.com your_password</code>", 
                parse_mode="HTML"
            )
            return
        
        email = parts[1].strip()
        password = parts[2].strip()
        
        msg = bot.reply_to(message, "🔄 MEGA Account login ho raha hai...")
        
        # Purana session logout karein
        run_cmd(["mega-logout"])
        
        # Naya login karein
        stdout, stderr, code = run_cmd(["mega-login", email, password], timeout=30)
        
        if code == 0:
            bot.edit_message_text(
                f"✅ <b>MEGA Login Safal Raha!</b>\n\n👤 <b>Logged in as:</b> <code>{html.escape(email)}</code>\n\nAb aap koi bhi <b>MEGA Folder Link</b> bhej sakte hain.",
                chat_id=message.chat.id,
                message_id=msg.message_id,
                parse_mode="HTML"
            )
        else:
            err = stderr if stderr else stdout
            bot.edit_message_text(
                f"❌ <b>Login Fail:</b>\n<code>{html.escape(err)}</code>\n\n<i>(Dhyan rahe Email/Password sahi ho aur MEGA par 2FA off ho)</i>",
                chat_id=message.chat.id,
                message_id=msg.message_id,
                parse_mode="HTML"
            )
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {html.escape(str(e))}", parse_mode="HTML")

# ----------------- LOGOUT -----------------
@bot.message_handler(commands=['logout'])
def handle_logout(message):
    msg = bot.reply_to(message, "🔄 Logout kiya ja raha hai...")
    stdout, stderr, code = run_cmd(["mega-logout"])
    
    if code == 0 or "Logged out" in stdout or "Not logged in" in stderr:
        bot.edit_message_text(
            "🚪 <b>Successfully Logged Out!</b>\nAapka MEGA session clear ho gaya hai.\n\nDobara use karne ke liye <code>/login email password</code> karein.",
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
    out, err, code = run_cmd(["mega-whoami"])
    if code == 0 and out:
        bot.reply_to(
            message, 
            f"🟢 <b>Account Status: LOGGED IN</b>\n\n<code>{html.escape(out)}</code>", 
            parse_mode="HTML"
        )
    else:
        bot.reply_to(
            message, 
            "🔴 <b>Account Status: NOT LOGGED IN</b>\n\nKripya login karein:\n<code>/login email password</code>", 
            parse_mode="HTML"
        )

# ----------------- LINK HANDLER -----------------
@bot.message_handler(func=lambda message: True)
def handle_mega_url(message):
    url = message.text.strip()
    
    if "mega.nz" not in url and "mega.co.nz" not in url:
        bot.reply_to(message, "⚠️ Kripya ek valid MEGA link bhejein ya <code>/help</code> check karein.", parse_mode="HTML")
        return

    # Check login
    who_out, _, who_code = run_cmd(["mega-whoami"])
    if who_code != 0 or not who_out:
        bot.reply_to(
            message, 
            "⚠️ <b>Aap logged in nahi hain!</b>\nPehle login karein:\n<code>/login email password</code>", 
            parse_mode="HTML"
        )
        return

    status_msg = bot.reply_to(message, "⏳ <b>Folder ko aapki Cloud Drive me add kiya ja raha hai...</b>")

    try:
        # Import se pehle drive snapshot
        ls_before, _, _ = run_cmd(["mega-ls", "/"])
        before_set = set([item.strip() for item in ls_before.splitlines() if item.strip()])
        
        # Server-side Folder Import
        imp_out, imp_err, imp_code = run_cmd(["mega-import", url, "/"], timeout=120)
        
        if imp_code != 0:
            bot.edit_message_text(
                f"❌ <b>Import Failed:</b>\n<code>{html.escape(imp_err if imp_err else imp_out)}</code>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            return

        # Import ke baad snapshot
        ls_after, _, _ = run_cmd(["mega-ls", "/"])
        after_set = set([item.strip() for item in ls_after.splitlines() if item.strip()])
        
        # Naya added folder detect karein
        new_items = list(after_set - before_set)
        
        target_name = None
        if new_items:
            target_name = new_items[0]
        else:
            all_items = [i.strip() for i in ls_after.splitlines() if i.strip()]
            if all_items:
                target_name = all_items[-1]

        if not target_name:
            bot.edit_message_text(
                "⚠️ Item add ho gaya, par folder name detect nahi hua.", 
                chat_id=message.chat.id, 
                message_id=status_msg.message_id
            )
            return

        # Share Link export karein
        exp_out, _, _ = run_cmd(["mega-export", "-a", f"/{target_name}"])
        match = re.search(r'(https://mega\.nz/[^\s]+)', exp_out)
        
        if match:
            share_link = match.group(1)
            bot.edit_message_text(
                f"✅ <b>Successfully Drive Mein Add Ho Gaya!</b>\n\n"
                f"📁 <b>Folder Name:</b> <code>{html.escape(target_name)}</code>\n"
                f"🔗 <b>Naya Share Link:</b>\n{share_link}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
        else:
            # Fallback list export search
            exp_list, _, _ = run_cmd(["mega-export"])
            match_fallback = re.search(rf'/{re.escape(target_name)}.*?(https://mega\.nz/[^\s]+)', exp_list)
            if match_fallback:
                bot.edit_message_text(
                    f"✅ <b>Drive Mein Add Ho Gaya!</b>\n\n"
                    f"📁 <b>Name:</b> <code>{html.escape(target_name)}</code>\n"
                    f"🔗 <b>Link:</b> {match_fallback.group(1)}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode="HTML"
                )
            else:
                bot.edit_message_text(
                    f"✅ Drive me add ho gaya: <code>{html.escape(target_name)}</code>\n(Export output: <code>{html.escape(exp_out)}</code>)",
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
