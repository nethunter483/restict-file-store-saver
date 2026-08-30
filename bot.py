import os
import re
import time
import html
import random
import string
import logging
import asyncio
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.request import HTTPXRequest

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN environment variable is missing!")
    exit(1)

MEGA_REGISTER_URL = "https://mega.nz/register"
MAIL_TM_API = "https://api.mail.tm"

# Multi-Thread Executor for Account Generation & Cloning
_genac_executor = ThreadPoolExecutor(max_workers=3)
CLONE_LOCK = asyncio.Lock()

FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Andrew",
    "Paul", "Joshua", "Kevin", "Brian", "George", "Timothy", "Jason", "Ryan",
    "Jacob", "Nicholas", "Eric", "Jonathan", "Stephen", "Justin", "Scott", "Brandon",
    "Benjamin", "Samuel", "Alexander", "Emma", "Olivia", "Ava", "Isabella", "Sophia"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson"
]

# ----------------- MEGACMD LINK EXPORT ENGINE (PRESERVED 100%) -----------------

def strip_ansi(text):
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def run_cmd(args, timeout=240, input_data="yes\nyes\nyes\n"):
    try:
        res = subprocess.run(
            args,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return strip_ansi(res.stdout.strip()), strip_ansi(res.stderr.strip()), res.returncode
    except subprocess.TimeoutExpired:
        return "", "Command Timed Out", 1
    except Exception as e:
        return "", str(e), 1

def extract_mega_link(text):
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

def import_and_export_to_account(email, password, mega_url):
    """MEGAcmd me login karke folder create, import aur guaranteed export karta hai"""
    run_cmd(["mega-logout"])
    
    out_log, err_log, code_log = run_cmd(["mega-login", email, password], timeout=40)
    if code_log != 0:
        return None, f"Login Error: {err_log or out_log}"

    folder_name = f"Import_{time.strftime('%Y%m%d_%H%M%S')}_{random.randint(100, 999)}"
    target_path = f"/{folder_name}"
    
    run_cmd(["mega-mkdir", target_path])
    
    imp_out, imp_err, imp_code = run_cmd(["mega-import", mega_url, target_path], timeout=240)
    if imp_code != 0:
        return None, f"Import Error: {imp_err or imp_out}"

    time.sleep(2)
    exp_out, exp_err, _ = run_cmd(["mega-export", "-a", target_path])
    share_link = extract_mega_link(exp_out + " " + exp_err)

    if not share_link:
        time.sleep(1)
        q_out, q_err, _ = run_cmd(["mega-export", target_path])
        share_link = extract_mega_link(q_out + " " + q_err)

    if not share_link:
        list_out, _, _ = run_cmd(["mega-export"])
        for line in list_out.splitlines():
            if folder_name.lower() in line.lower():
                share_link = extract_mega_link(line)
                if share_link:
                    break

    if share_link:
        return share_link, folder_name
    return None, f"Export Output: {exp_out}"

# ----------------- PLAYWRIGHT ACCOUNT CREATOR -----------------

def generate_complex_password():
    length = random.randint(12, 15)
    chars = string.ascii_letters + string.digits + "@#$!%&*"
    pwd = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice("@#$!%&*")
    ]
    pwd += [random.choice(chars) for _ in range(length - 4)]
    random.shuffle(pwd)
    return "".join(pwd)

def get_temp_email(session: requests.Session):
    for _ in range(3):
        try:
            resp = session.get(f"{MAIL_TM_API}/domains", timeout=8)
            if resp.status_code == 429:
                time.sleep(2)
                continue
            resp.raise_for_status()
            domains = resp.json().get("hydra:member", [])
            domain = domains[0]["domain"] if domains else "web-library.net"
            
            username = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
            temp_password = generate_complex_password()
            email = f"{username}@{domain}"

            acc_resp = session.post(
                f"{MAIL_TM_API}/accounts",
                json={"address": email, "password": temp_password},
                timeout=8,
            )
            if acc_resp.status_code == 429:
                time.sleep(2)
                continue
            acc_resp.raise_for_status()

            token_resp = session.post(
                f"{MAIL_TM_API}/token",
                json={"address": email, "password": temp_password},
                timeout=8,
            )
            token = token_resp.json().get("token", "")

            if token:
                return email, token
        except Exception as e:
            logger.error(f"mail.tm error: {e}")
            time.sleep(1)
    return None, None

def wait_and_get_verification_link(session: requests.Session, token: str, timeout: int = 50):
    start_time = time.time()
    headers = {"Authorization": f"Bearer {token}"}
    while time.time() - start_time < timeout:
        try:
            resp = session.get(f"{MAIL_TM_API}/messages", headers=headers, timeout=8)
            if resp.status_code == 200:
                messages = resp.json().get("hydra:member", [])
                if messages:
                    msg_id = messages[0].get("id")
                    msg_resp = session.get(f"{MAIL_TM_API}/messages/{msg_id}", headers=headers, timeout=8)
                    if msg_resp.status_code == 200:
                        msg_data = msg_resp.json()
                        body_text = (
                            msg_data.get("body", "") 
                            or msg_data.get("text", "") 
                            or msg_data.get("html", "") 
                            or ""
                        )
                        links = re.findall(r'https?://[^\s<>"\']+', body_text)
                        for link in links:
                            if any(k in link.lower() for k in ["verify", "confirm", "activate", "mega.nz", "mega.io"]):
                                return link
        except Exception:
            pass
        time.sleep(1.5)
    return None

def run_signup_automation():
    session = requests.Session()
    email, token = get_temp_email(session)
    if not email or not token:
        return {"status": "error", "message": "Temp email create nahi ho paya."}

    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    generated_password = generate_complex_password()

    browser = None
    p = None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,webm}", lambda r: r.abort())

        page.goto(MEGA_REGISTER_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector('input[type="email"], input[name*="email"], #register-email-registerpage2', timeout=15000)
        page.wait_for_timeout(1000)

        fill_script = """
        ({ email, password, firstName, lastName }) => {
            const fn = document.querySelector('#register-firstname-registerpage2, input[name*="first"], input[name="firstname"]');
            const ln = document.querySelector('#register-lastname-registerpage2, input[name*="last"], input[name="lastname"]');
            if (fn) { fn.value = firstName; fn.dispatchEvent(new Event('input', { bubbles: true })); }
            if (ln) { ln.value = lastName; ln.dispatchEvent(new Event('input', { bubbles: true })); }

            const em = document.querySelector('#register-email-registerpage2, input[type="email"], input[name*="email"]');
            if (em) { em.value = email; em.dispatchEvent(new Event('input', { bubbles: true })); }

            document.querySelectorAll('input[type="password"]').forEach(input => {
                input.value = password;
                input.dispatchEvent(new Event('input', { bubbles: true }));
            });

            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                cb.checked = true;
                cb.dispatchEvent(new Event('change', { bubbles: true }));
            });

            document.querySelectorAll('.mega-checkbox, .checkbox, .check-box, label.checkbox').forEach(el => el.click());
        }
        """
        page.evaluate(fill_script, {
            "email": email,
            "password": generated_password,
            "firstName": first_name,
            "lastName": last_name
        })

        page.wait_for_timeout(800)

        submit_selectors = [
            "button.register-button", "button[type='submit']", 
            "button:has-text('Create account')", "button:has-text('Sign up')"
        ]
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click(force=True)
                    break
            except Exception:
                continue

        verification_link = wait_and_get_verification_link(session, token, timeout=50)
        if not verification_link:
            browser.close()
            p.stop()
            return {"status": "timeout", "email": email, "password": generated_password}

        page.goto(verification_link, wait_until="domcontentloaded", timeout=30000)
        verify_pwd = page.locator("input[type='password']").first
        verify_pwd.wait_for(state="visible", timeout=12000)
        verify_pwd.fill(generated_password)

        confirm_btn = page.locator("button.confirm-account-btn, button:has-text('Confirm'), button:has-text('Verify')").first
        if confirm_btn.is_visible(timeout=2000):
            confirm_btn.click(force=True)
        else:
            page.keyboard.press("Enter")

        try:
            page.wait_for_function("() => window.location.href.includes('#fm') || window.location.href.includes('plans')", timeout=12000)
        except Exception:
            pass

        page.wait_for_timeout(2000)
        browser.close()
        p.stop()
        return {"status": "success", "email": email, "password": generated_password, "name": f"{first_name} {last_name}"}

    except Exception as e:
        logger.error(f"Playwright error: {e}")
        if browser:
            try: browser.close()
            except Exception: pass
        if p:
            try: p.stop()
            except Exception: pass
        return {"status": "error", "message": str(e)}

# ----------------- TELEGRAM BOT LOGIC -----------------

async def handle_dual_mega_clone(update: Update, context: ContextTypes.DEFAULT_TYPE, mega_url: str):
    chat_id = update.effective_chat.id
    
    async with CLONE_LOCK:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ <b>[1/4] Creating MEGA Account #1...</b>\n<i>(Temp mail + Playwright auto-verify)</i>",
            parse_mode="HTML"
        )

        loop = asyncio.get_running_loop()

        # --- ACCOUNT 1 ---
        acc1 = await loop.run_in_executor(_genac_executor, run_signup_automation)
        if acc1.get("status") != "success":
            await status_msg.edit_text(f"❌ <b>Account #1 create karne me error aaya:</b>\n<code>{acc1.get('message', 'Timeout')}</code>", parse_mode="HTML")
            return

        await status_msg.edit_text(
            f"✅ <b>Account #1 Created!</b> (<code>{acc1['email']}</code>)\n\n"
            f"⏳ <b>[2/4] Link ko Account #1 me clone & export kiya ja raha hai...</b>",
            parse_mode="HTML"
        )

        link1, details1 = await loop.run_in_executor(
            _genac_executor, 
            import_and_export_to_account, 
            acc1["email"], 
            acc1["password"], 
            mega_url
        )

        if not link1:
            await status_msg.edit_text(f"❌ <b>Account #1 par Link Export fail ho gaya:</b>\n<code>{details1}</code>", parse_mode="HTML")
            return

        # --- ACCOUNT 2 ---
        await status_msg.edit_text(
            f"✅ <b>Account #1 Ready!</b>\n\n"
            f"⏳ <b>[3/4] Creating MEGA Account #2...</b>",
            parse_mode="HTML"
        )

        acc2 = await loop.run_in_executor(_genac_executor, run_signup_automation)
        if acc2.get("status") != "success":
            await status_msg.edit_text(f"❌ <b>Account #2 create karne me error aaya:</b>\n<code>{acc2.get('message', 'Timeout')}</code>", parse_mode="HTML")
            return

        await status_msg.edit_text(
            f"✅ <b>Account #2 Created!</b> (<code>{acc2['email']}</code>)\n\n"
            f"⏳ <b>[4/4] Link ko Account #2 me clone & export kiya ja raha hai...</b>",
            parse_mode="HTML"
        )

        link2, details2 = await loop.run_in_executor(
            _genac_executor, 
            import_and_export_to_account, 
            acc2["email"], 
            acc2["password"], 
            mega_url
        )

        if not link2:
            await status_msg.edit_text(f"❌ <b>Account #2 par Link Export fail ho gaya:</b>\n<code>{details2}</code>", parse_mode="HTML")
            return

        # --- FINAL RESPONSE ---
        final_text = (
            "╭──────────────────────────────╮\n"
            "│  🎉 <b>DUAL MEGA CLONE SUCCESS!</b>  │\n"
            "╰──────────────────────────────╯\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>ACCOUNT #1:</b>\n"
            f"📧 <code>{acc1['email']}</code>\n"
            f"🔑 <code>{acc1['password']}</code>\n"
            f"🔗 <b>Share Link:</b>\n{link1}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>ACCOUNT #2:</b>\n"
            f"📧 <code>{acc2['email']}</code>\n"
            f"🔑 <code>{acc2['password']}</code>\n"
            f"🔗 <b>Share Link:</b>\n{link2}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ <i>Dono accounts fresh & verified hain, aur files successfully clone ho chuki hain!</i>"
        )

        await status_msg.edit_text(final_text, parse_mode="HTML")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "mega.nz" in text or "mega.co.nz" in text:
        await handle_dual_mega_clone(update, context, text)
    else:
        await update.message.reply_text("⚠️ Kripya ek valid **MEGA Folder/File Link** bhejein ya `/genac` se account banayein.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "╭──────────────────────────────╮\n"
        "│  🤖  <b>MEGA AUTO-CLONE BOT</b>      │\n"
        "╰──────────────────────────────╯\n\n"
        "👋 <b>Namaste!</b>\n\n"
        "👉 <b>Bas koi bhi MEGA Folder/File Link bhejein:</b>\n"
        "Bot khud <b>2 fresh accounts</b> banayega aur dono me folder clone karke <b>2 naye public share links</b> de dega!\n\n"
        "🔹 <code>/genac</code> — Sirf 1 naya MEGA account banane ke liye.",
        parse_mode="HTML"
    )


async def genac_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ <i>Creating your verified account...</i>", parse_mode="HTML")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_genac_executor, run_signup_automation)
    
    if result["status"] == "success":
        await status_msg.edit_text(
            f"🎉 <b>ACCOUNT CREATED!</b>\n\n"
            f"👤 <b>Name:</b> <code>{result.get('name', 'Mega User')}</code>\n"
            f"📧 <b>Email:</b> <code>{result['email']}</code>\n"
            f"🔑 <b>Password:</b> <code>{result['password']}</code>",
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(f"❌ <b>Error:</b> {result.get('message', 'Failed')}", parse_mode="HTML")


async def post_init(application):
    commands = [
        BotCommand("start", "🚀 Welcome menu"),
        BotCommand("genac", "🧬 Single account generator"),
    ]
    await application.bot.set_my_commands(commands)


def main():
    print("🔄 Initializing MEGAcmd server daemon...")
    run_cmd(["mega-version"])

    custom_request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(BOT_TOKEN).request(custom_request).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("genac", genac_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🤖 Dual MEGA Auto-Clone Bot is Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
