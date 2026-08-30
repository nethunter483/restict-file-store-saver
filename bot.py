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

_genac_executor = ThreadPoolExecutor(max_workers=5)
CLONE_LOCK = asyncio.Lock()

# 100% Unique Realistic Random Names (Exact from your working code)
FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Andrew",
    "Paul", "Joshua", "Kevin", "Brian", "George", "Timothy", "Jason", "Ryan",
    "Jacob", "Nicholas", "Eric", "Jonathan", "Stephen", "Justin", "Scott", "Brandon",
    "Benjamin", "Samuel", "Alexander", "Emma", "Olivia", "Ava", "Isabella", "Sophia",
    "Charlotte", "Mia", "Amelia", "Harper", "Evelyn", "Abigail", "Emily", "Ella",
    "Elizabeth", "Camila", "Luna", "Aria", "Chloe", "Penelope", "Layla", "Mila"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Hill", "Flores", "Green"
]

# ----------------- MEGACMD EXPORT ENGINE (100% WORKING) -----------------

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

def import_and_export_to_account(email, password, mega_url, status_cb=None):
    """MEGAcmd me login, import aur link export karta hai"""
    if status_cb:
        status_cb("⏳ <b>Step 5/6</b> — Logging into MEGA Cloud Drive...")

    run_cmd(["mega-logout"])
    out_log, err_log, code_log = run_cmd(["mega-login", email, password], timeout=40)
    if code_log != 0:
        return None, f"Login Error: {err_log or out_log}"

    folder_name = f"Import_{time.strftime('%Y%m%d_%H%M%S')}_{random.randint(100, 999)}"
    target_path = f"/{folder_name}"
    
    run_cmd(["mega-mkdir", target_path])
    
    if status_cb:
        status_cb(f"⏳ <b>Step 6/6</b> — Cloning remote folder into Drive...")

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

# ----------------- PLAYWRIGHT SIGNUP (EXACT 100% CODE) -----------------

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
            logger.error(f"mail.tm session error: {e}")
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
        except Exception as e:
            logger.error(f"Error checking email messages: {e}")
        time.sleep(1.5)
    return None

def run_signup_automation(status_callback=None):
    def status(text):
        if status_callback:
            try:
                status_callback(text)
            except Exception:
                pass

    session = requests.Session()
    status("⏳ <b>Step 1/4</b> — Creating temporary inbox...")
    email, token = get_temp_email(session)
    if not email or not token:
        return {"status": "error", "message": "Failed to create temporary inbox. Please try again."}

    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    generated_password = generate_complex_password()

    status(f"⏳ <b>Step 2/4</b> — Registering as <code>{first_name} {last_name}</code>...")

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
                "--no-first-run",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,mp4,webm}",
            lambda route: route.abort()
        )

        page.goto(MEGA_REGISTER_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector('input[type="email"], input[name*="email"], #register-email-registerpage2', timeout=15000)
        page.wait_for_timeout(1000)

        fill_script = """
        ({ email, password, firstName, lastName }) => {
            const fn = document.querySelector('#register-firstname-registerpage2, input[name*="first"], input[name="firstname"]');
            const ln = document.querySelector('#register-lastname-registerpage2, input[name*="last"], input[name="lastname"]');
            const allText = Array.from(document.querySelectorAll('input[type="text"], input:not([type])')).filter(el => el.offsetParent !== null);
            
            if (fn) {
                fn.value = firstName;
                fn.dispatchEvent(new Event('input', { bubbles: true }));
                fn.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (allText.length >= 1) {
                allText[0].value = firstName;
                allText[0].dispatchEvent(new Event('input', { bubbles: true }));
                allText[0].dispatchEvent(new Event('change', { bubbles: true }));
            }

            if (ln) {
                ln.value = lastName;
                ln.dispatchEvent(new Event('input', { bubbles: true }));
                ln.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (allText.length >= 2) {
                allText[1].value = lastName;
                allText[1].dispatchEvent(new Event('input', { bubbles: true }));
                allText[1].dispatchEvent(new Event('change', { bubbles: true }));
            }

            const em = document.querySelector('#register-email-registerpage2, input[type="email"], input[name*="email"]');
            if (em) {
                em.value = email;
                em.dispatchEvent(new Event('input', { bubbles: true }));
                em.dispatchEvent(new Event('change', { bubbles: true }));
            }

            const pwInputs = Array.from(document.querySelectorAll('input[type="password"]')).filter(el => el.offsetParent !== null);
            pwInputs.forEach(input => {
                input.value = password;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });

            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                cb.checked = true;
                cb.dispatchEvent(new Event('input', { bubbles: true }));
                cb.dispatchEvent(new Event('change', { bubbles: true }));
            });

            document.querySelectorAll('.mega-checkbox, .checkbox, .check-box, .understand-check, .terms-check, label.checkbox, label[for*="register"]').forEach(el => {
                el.click();
            });
        }
        """
        page.evaluate(fill_script, {
            "email": email,
            "password": generated_password,
            "firstName": first_name,
            "lastName": last_name
        })

        page.wait_for_timeout(800)

        for chk in page.locator(".mega-checkbox, .checkbox, .check-box, label.checkbox, input[type='checkbox']").all():
            try:
                chk.click(force=True)
            except Exception:
                pass

        page.wait_for_timeout(500)

        submit_selectors = [
            "button.register-button",
            "button[type='submit']",
            "button:has-text('Create account')",
            "button:has-text('Sign up')",
            "button:has-text('Register')",
            ".top-dialog-btn",
        ]
        clicked = False
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click(force=True)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            page.keyboard.press("Enter")

        page.wait_for_timeout(2000)
        status("⏳ <b>Step 3/4</b> — Waiting for verification email...")

        verification_link = wait_and_get_verification_link(session, token, timeout=50)
        if not verification_link:
            browser.close()
            p.stop()
            return {"status": "timeout", "email": email, "password": generated_password}

        status("⏳ <b>Step 4/4</b> — Initializing Root Keys & Link Sharing engine...")

        page.goto(verification_link, wait_until="domcontentloaded", timeout=30000)

        verify_pwd = page.locator("input[type='password']").first
        verify_pwd.wait_for(state="visible", timeout=12000)
        verify_pwd.fill(generated_password)

        confirm_btn = page.locator(
            "button.confirm-account-btn, button:has-text('Confirm'), button:has-text('Verify'), button:has-text('Start'), button[type='submit'], .top-dialog-btn"
        ).first
        if confirm_btn.is_visible(timeout=2000):
            confirm_btn.click(force=True)
        else:
            page.keyboard.press("Enter")

        try:
            page.wait_for_function(
                """() => {
                    const u = window.location.href;
                    return u.includes('#fm') || u.includes('start') || u.includes('plans') || !document.querySelector('input[type="password"]');
                }""",
                timeout=12000
            )
        except Exception:
            pass

        try:
            free_btn = page.locator("button:has-text('Free'), button:has-text('Get started'), button:has-text('Skip'), .account-type-free").first
            if free_btn.is_visible(timeout=2000):
                free_btn.click(force=True)
        except Exception:
            pass

        page.wait_for_timeout(2500)

        browser.close()
        p.stop()
        return {"status": "success", "email": email, "password": generated_password, "name": f"{first_name} {last_name}"}

    except Exception as e:
        logger.error(f"Automation error: {e}")
        if browser:
            try: browser.close()
            except Exception: pass
        if p:
            try: p.stop()
            except Exception: pass
        return {"status": "error", "message": str(e)}

# ----------------- LIVE PROGRESS CONTROLLER -----------------

def create_live_status_cb(chat_id, message_id, title_prefix=""):
    def callback(text):
        try:
            full_msg = (
                "╭──────────────────────────────╮\n"
                f"│  ⚡ <b>{title_prefix}</b>\n"
                "╰──────────────────────────────╯\n\n"
                f"{text}"
            )
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": full_msg,
                    "parse_mode": "HTML",
                },
                timeout=5,
            )
        except Exception:
            pass
    return callback

async def handle_dual_mega_clone(update: Update, context: ContextTypes.DEFAULT_TYPE, mega_url: str):
    chat_id = update.effective_chat.id
    
    async with CLONE_LOCK:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "╭──────────────────────────────╮\n"
                "│  ⏳  <b>STARTING DUAL CLONE...</b>   │\n"
                "╰──────────────────────────────╯\n\n"
                "⏳ <i>Initializing account creation engine...</i>"
            ),
            parse_mode="HTML"
        )
        msg_id = msg.message_id
        loop = asyncio.get_running_loop()

        # ==================== ACCOUNT 1 ====================
        cb1 = create_live_status_cb(chat_id, msg_id, "ACCOUNT 1/2 IN PROGRESS")
        acc1 = await loop.run_in_executor(_genac_executor, run_signup_automation, cb1)
        
        if acc1.get("status") != "success":
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"❌ <b>Account #1 create karne me error aaya:</b>\n<code>{acc1.get('message', 'Timeout / Failed')}</code>",
                parse_mode="HTML"
            )
            return

        cb1_imp = create_live_status_cb(chat_id, msg_id, "ACCOUNT 1/2 IMPORTING")
        link1, details1 = await loop.run_in_executor(
            _genac_executor, 
            import_and_export_to_account, 
            acc1["email"], 
            acc1["password"], 
            mega_url,
            cb1_imp
        )

        if not link1:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"❌ <b>Account #1 Link Export fail ho gaya:</b>\n<code>{details1}</code>",
                parse_mode="HTML"
            )
            return

        # ==================== ACCOUNT 2 ====================
        cb2 = create_live_status_cb(chat_id, msg_id, "ACCOUNT 2/2 IN PROGRESS")
        acc2 = await loop.run_in_executor(_genac_executor, run_signup_automation, cb2)
        
        if acc2.get("status") != "success":
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"❌ <b>Account #2 create karne me error aaya:</b>\n<code>{acc2.get('message', 'Timeout / Failed')}</code>",
                parse_mode="HTML"
            )
            return

        cb2_imp = create_live_status_cb(chat_id, msg_id, "ACCOUNT 2/2 IMPORTING")
        link2, details2 = await loop.run_in_executor(
            _genac_executor, 
            import_and_export_to_account, 
            acc2["email"], 
            acc2["password"], 
            mega_url,
            cb2_imp
        )

        if not link2:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"❌ <b>Account #2 Link Export fail ho gaya:</b>\n<code>{details2}</code>",
                parse_mode="HTML"
            )
            return

        # ==================== FINAL SUCCESS REPORT ====================
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
            "⚡ <i>Dono accounts fresh & verified hain, aur folder dono accounts me permanently export ho chuka hai!</i>"
        )

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=final_text,
            parse_mode="HTML"
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "mega.nz" in text or "mega.co.nz" in text:
        await handle_dual_mega_clone(update, context, text)
    else:
        await update.message.reply_text("⚠️ Kripya valid **MEGA Folder/File Link** bhejein ya `/genac` se single account banayein.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🧬 CREATE SINGLE ACCOUNT", callback_data="genac")]]
    await update.message.reply_text(
        "╭──────────────────────────────╮\n"
        "│  🤖  <b>MEGA AUTO-CLONE BOT</b>      │\n"
        "╰──────────────────────────────╯\n\n"
        "👋 <b>Namaste!</b>\n\n"
        "👉 <b>Bas koi bhi MEGA Link bhejein:</b>\n"
        "Bot live <b>2 fresh accounts</b> banayega aur dono me folder clone karke <b>2 naye public share links</b> de dega!\n\n"
        "🔹 <code>/genac</code> — Single MEGA account banane ke liye.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_genac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    init_text = (
        "╭──────────────────────────────╮\n"
        "│  ⏳  <b>STARTING PROCESS...</b>      │\n"
        "╰──────────────────────────────╯\n\n"
        "⏳ <i>Creating your verified account...</i>"
    )
    if update.callback_query:
        msg = await update.callback_query.edit_message_text(init_text, parse_mode="HTML")
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=init_text, parse_mode="HTML")

    cb = create_live_status_cb(chat_id, msg.message_id, "GENERATE SINGLE ACCOUNT")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_genac_executor, run_signup_automation, cb)

    if result["status"] == "success":
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=(
                "╭──────────────────────────────╮\n"
                "│  🎉  <b>ACCOUNT CREATED!</b>        │\n"
                "╰──────────────────────────────╯\n\n"
                f"👤 <b>Name:</b> <code>{result.get('name', 'Mega User')}</code>\n"
                f"📧 <b>Email:</b> <code>{result['email']}</code>\n"
                f"🔑 <b>Password:</b> <code>{result['password']}</code>\n\n"
                "✅ <i>Status: Master Keys & Link Sharing Ready!</i>"
            ),
            parse_mode="HTML"
        )
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=f"❌ <b>Error:</b> <code>{result.get('message', 'Failed')}</code>",
            parse_mode="HTML"
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "genac":
        await handle_genac(update, context)

async def genac_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_genac(update, context)

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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🤖 Dual MEGA Auto-Clone Bot is Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
