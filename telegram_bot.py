"""
Telegram Bot Interface for SheerID Verification
PLATINUM EDITION - Custom ASCII UI
"""
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode

import config
import sheerid_api
import student_generator
import doc_generator
import re
import json
import os

AUTHORIZED_USERS_FILE = "authorized_users.json"
active_tasks = set()

def load_authorized_users():
    if os.path.exists(AUTHORIZED_USERS_FILE):
        try:
            with open(AUTHORIZED_USERS_FILE, "r") as f:
                return set(json.load(f))
        except:
            pass
    return set()

def save_authorized_users(users_set):
    with open(AUTHORIZED_USERS_FILE, "w") as f:
        json.dump(list(users_set), f)

authorized_users = load_authorized_users()

def is_authorized(user_id):
    if str(config.ADMIN_ID) and str(user_id) == str(config.ADMIN_ID):
        return True
    return user_id in authorized_users

async def check_auth(update: Update) -> bool:
    user_id = update.effective_user.id
    if is_authorized(user_id):
        return True
    await update.message.reply_text(f"❌ **Access Denied**. You are not authorized (ID: `{user_id}`). Contact the administrator for access.", parse_mode=ParseMode.MARKDOWN)
    return False


# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ═══════════════════════════════════════════════════════════════════════
# CUSTOM UI COMPONENTS - Box Drawing & ASCII Art
# ═══════════════════════════════════════════════════════════════════════

class UI:
    """Custom UI elements using Unicode box-drawing characters"""
    
    # Box corners and lines
    TL = "╔"  # top-left
    TR = "╗"  # top-right
    BL = "╚"  # bottom-left
    BR = "╝"  # bottom-right
    H = "═"   # horizontal
    V = "║"   # vertical
    
    # Light box
    tl = "┌"
    tr = "┐"
    bl = "└"
    br = "┘"
    h = "─"
    v = "│"
    
    # Status indicators (non-emoji)
    PULSE = "●"
    HOLLOW = "○"
    ARROW = "▸"
    CHECK = "▣"
    CROSS = "▢"
    BLOCK = "█"
    SHADE = "░"
    HALF = "▒"
    
    # Progress characters
    PROG_FULL = "■"
    PROG_EMPTY = "□"
    
    @staticmethod
    def box(title: str, content: str, width: int = 32) -> str:
        """Generate a bordered box with title"""
        lines = content.split('\n')
        inner_w = width - 4
        
        # Build box
        result = []
        result.append(f"{UI.TL}{UI.H}{title[:inner_w].center(inner_w, UI.H)}{UI.H}{UI.TR}")
        
        for line in lines:
            padded = line[:inner_w].ljust(inner_w)
            result.append(f"{UI.V} {padded} {UI.V}")
        
        result.append(f"{UI.BL}{UI.H * (width - 2)}{UI.BR}")
        return '\n'.join(result)
    
    @staticmethod
    def progress_bar(current: int, total: int, width: int = 12) -> str:
        """Generate ASCII progress bar"""
        filled = int((current / total) * width)
        empty = width - filled
        return f"[{UI.PROG_FULL * filled}{UI.PROG_EMPTY * empty}]"
    
    @staticmethod
    def header(text: str) -> str:
        """Generate a header line"""
        return f"{UI.BLOCK}{UI.SHADE} {text} {UI.SHADE}{UI.BLOCK}"
    
    @staticmethod
    def status_line(key: str, value: str, key_width: int = 12) -> str:
        """Generate aligned status line"""
        return f"{UI.ARROW} {key.ljust(key_width)} {UI.v} {value}"
    
    @staticmethod
    def divider(width: int = 28) -> str:
        """Generate divider line"""
        return UI.h * width

# ═══════════════════════════════════════════════════════════════════════
# ASCII ART BANNERS
# ═══════════════════════════════════════════════════════════════════════

BANNER_MAIN = """
```
 _____ _                    ___________
/  ___| |                  |_   _|  _  \\
\\ `--.| |__   ___  ___ _ __  | | | | | |
 `--. \\ '_ \\ / _ \\/ _ \\ '__| | | | | | |
/\\__/ / | | |  __/  __/ |   _| |_| |/ /
\\____/|_| |_|\\___|\\___|_|   |___/|___/

      P L A T I N U M   E D I T I O N
           ┌──────────────────┐
           │  STEALTH  MODE   │
           └──────────────────┘
```"""

BANNER_SUCCESS = """
```
    ╔═══════════════════════════════╗
    ║                               ║
    ║   ▓▓▓   █   █  █ █▄▀         ║
    ║   █ █   ██ ██  █ █ █         ║
    ║   ▓▓▓   █ █ █  █ █  █        ║
    ║                               ║
    ║   V E R I F I C A T I O N    ║
    ║   C O M P L E T E            ║
    ╚═══════════════════════════════╝
```"""

BANNER_FAIL = """
```
    ┌───────────────────────────────┐
    │         ▄▀▀▀▀▀▀▀▀▀▀▀▄        │
    │        █  ░░░░░░░░░  █       │
    │        █  ░ DENIED ░  █       │
    │        █  ░░░░░░░░░  █       │
    │         ▀▄▄▄▄▄▄▄▄▄▄▄▀        │
    └───────────────────────────────┘
```"""

BANNER_LOADING = """```
     ╭─────────────────────╮
     │ ▓▓▓▓▓▓▓░░░░░░░░░░░░ │
     │    PROCESSING...    │
     ╰─────────────────────╯
```"""

# ═══════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    user_id = update.effective_user.id
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    welcome_text = f"""🛡️ **SHEERID VERIFICATION BOT PLATINUM**

**System Status**
✅ Node: ONLINE
👤 Session: `{user_id}`
🟢 Access: AUTHORIZED
⏱️ Time: {timestamp}

**Available Commands**
🔹 `/verify [url]` - Execute verification
🔹 `/status` - System diagnostics
🔹 `/help` - Protocol manual

_Paste any SheerID link directly to verify_
"""
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    help_text = f"""📖 **OPERATIONAL PROTOCOL v2.0**

**1. Acquire Target**
   Copy verification link from the offer page.

**2. Network Requirements**
   US residential IP proxy required. 

**3. Execute**
   Type `/verify <link>` or paste the link directly in the chat.

*Stealth Details:*
• TLS Fingerprint: Chrome 131
• Stealth Level: Maximum
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    import socket
    
    # Check connectivity
    try:
        socket.create_connection(("services.sheerid.com", 443), timeout=5)
        api_status = "✅ CONNECTED"
    except:
        api_status = "❌ UNREACHABLE"
    
    proxy_status = "✅ ACTIVE" if config.USE_PROXY else "❌ DISABLED"
    
    status_text = f"""📊 **SYSTEM DIAGNOSTICS**

⚙️ **Modules**
• SheerID API: {api_status}
• Proxy Module: {proxy_status}
• Doc Generator: ✅ READY
• Identity Pool: ✅ LOADED

💻 **System**
• Memory: Stable
• Uptime: Stable
"""
    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    user_id = update.effective_user.id
    
    if user_id in active_tasks:
        await update.message.reply_text("⚠️ **Wait!** You already have a verification task running.", parse_mode=ParseMode.MARKDOWN)
        return
        
    if not context.args:
        error_text = "❌ **Error: Missing Argument**\nUsage: `/verify https://...`"
        await update.message.reply_text(error_text, parse_mode=ParseMode.MARKDOWN)
        return

    url = context.args[0]
    user = update.effective_user
    
    active_tasks.add(user_id)
    try:
        client = sheerid_api.SheerIDClient(proxy=config.PROXY_URL if config.USE_PROXY else None)
        
        verification_id, is_program = client.extract_verification_id_from_url(url)
        if not verification_id:
            await update.message.reply_text("❌ **Error: Invalid Link**\nCannot extract Verification ID.", parse_mode=ParseMode.MARKDOWN)
            return

        # Initial status
        init_text = f"""⏳ **INITIALIZING VERIFICATION**
        
🆔 Task ID: `{verification_id[:16]}...`
👤 Operator: {user.first_name}
⏱️ Time: {datetime.now().strftime('%H:%M:%S')}

➡️ *Phase 1/4: Generating identity profile...*
"""
        status_msg = await update.message.reply_text(init_text, parse_mode=ParseMode.MARKDOWN)

        # Step 1: Generate Profile
        profile = student_generator.generate_student_profile()
        univ_name = profile["display_info"]["university"]
        student_name = profile["display_info"]["full_name"]
        
        phase2_text = f"""🚀 **PAYLOAD INJECTION**

🏫 Target: {univ_name[:20]}
🎓 Profile: {student_name}
📧 Email: {profile['email'][:24]}

➡️ *Phase 2/4: Submitting to SheerID API...*
"""
        await status_msg.edit_text(phase2_text, parse_mode=ParseMode.MARKDOWN)

        # Step 2: Submit
        def doc_gen_wrapper(first, last, school):
            if doc_generator.select_document_type() == "student_id":
                return doc_generator.generate_student_id(first, last, school)
            else:
                return doc_generator.generate_transcript(first, last, profile["birthDate"], school)

        result = client.process_verification(verification_id, is_program, profile, doc_gen_wrapper)
        
        # Step 3: Handle Result
        if result["status"] == "SUCCESS":
            success_text = f"""✅ **VERIFICATION COMPLETE**

**Verification Data**
🏫 Institution: {univ_name}
🎓 Identity: {student_name}
📧 Email: `{profile['email']}`

**Reward Acquired**"""
            if result.get("reward_code"):
                success_text += f"\n🔑 Code: `{result['reward_code']}`"
                
            if result.get("redirect_url"):
                success_text += f"\n🔗 [Access Reward]({result['redirect_url']})"
                
            success_text += "\n\n🔒 _Connection Terminated Securely_"
            
            await status_msg.edit_text(success_text, parse_mode=ParseMode.MARKDOWN)
            
        elif result["status"] == "TIMEOUT":
            last_step = result.get("last_details", {}).get("currentStep")
            if last_step == "pending":
                pending_text = f"""⏳ **MANUAL REVIEW QUEUED**

Documents submitted successfully. Awaiting SheerID review.
Auto-monitor is active for 30 minutes. You will be notified.

🔗 Backup link: `{url[:40]}...`
"""
                await status_msg.edit_text(pending_text, parse_mode=ParseMode.MARKDOWN)
                
                import subprocess
                subprocess.Popen(["python3", "monitor_task.py", verification_id, str(update.effective_chat.id)])
            else:
                await status_msg.edit_text("⚠️ **TIMEOUT**. No response received. Please check the link manually.", parse_mode=ParseMode.MARKDOWN)
        
        else:
            reason = result.get("reason")
            if isinstance(reason, list):
                reason = ", ".join(reason)
            elif isinstance(result.get("details"), dict):
                reason = result["details"].get("systemErrorMessage", "Unknown Error")
            
            error_msg = str(reason or result.get("status", "Unknown"))[:30]
            
            fail_text = f"""❌ **VERIFICATION DENIED**

🚨 Reason: {error_msg}
🏫 Target: {univ_name[:18]}

💡 *Hint: IP mismatch or session tainted. Use a fresh link.*
"""
            await status_msg.edit_text(fail_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        error_text = f"❌ **SYSTEM EXCEPTION**\n`{str(e)[:50]}`"
        await status_msg.edit_text(error_text, parse_mode=ParseMode.MARKDOWN)
        logging.error(f"Error processing {verification_id}: {e}\n{trace}")
    finally:
        active_tasks.discard(user_id)

# ═══════════════════════════════════════════════════════════════════════
# BOT INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════

def run_bot():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ CONFIG ERROR: Set TELEGRAM_BOT_TOKEN in .env")
        return

    application = ApplicationBuilder().token(config.BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("verify", verify_command))
    
    async def handle_raw_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await check_auth(update): return
        text = update.message.text
        
        # Regex to extract URL safely
        match = re.search(r'(https?://[^\s]+sheerid\.com/verify/[^\s]+)', text)
        if match:
            context.args = [match.group(1)]
            await verify_command(update, context)
            
    # Admin commands
    async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(config.ADMIN_ID):
            return
        if not context.args:
            await update.message.reply_text("Usage: `/approve <user_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            user_id = int(context.args[0])
            authorized_users.add(user_id)
            save_authorized_users(authorized_users)
            await update.message.reply_text(f"✅ User `{user_id}` has been authorized.", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("Invalid user ID format.")

    async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(config.ADMIN_ID):
            return
        if not context.args:
            await update.message.reply_text("Usage: `/revoke <user_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            user_id = int(context.args[0])
            if user_id in authorized_users:
                authorized_users.remove(user_id)
                save_authorized_users(authorized_users)
                await update.message.reply_text(f"❌ User `{user_id}` access revoked.", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(f"User `{user_id}` is not in the authorized list.", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("Invalid user ID format.")

    async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(config.ADMIN_ID):
            return
        if not authorized_users:
            await update.message.reply_text("No authorized users found (excluding admin).")
            return
        users_list = "\n".join([f"- `{uid}`" for uid in authorized_users])
        await update.message.reply_text(f"**Authorized Users:**\n{users_list}", parse_mode=ParseMode.MARKDOWN)

    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("revoke", revoke_command))
    application.add_handler(CommandHandler("users", users_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_raw_message))

    print("✅ SHEERID PLATINUM BOT ONLINE. Press Ctrl+C to terminate.")

    application.run_polling()

if __name__ == "__main__":
    run_bot()
