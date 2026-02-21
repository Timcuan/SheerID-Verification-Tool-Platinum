"""
Telegram Bot Interface for SheerID Verification
PLATINUM EDITION — Futuristic UI with Interactive Menus
"""
import logging
import asyncio
from datetime import datetime
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
import socket

# ─────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────

AUTHORIZED_USERS_FILE = "authorized_users.json"
active_tasks = set()  # Per-user concurrency lock

def load_authorized_users():
    if os.path.exists(AUTHORIZED_USERS_FILE):
        try:
            with open(AUTHORIZED_USERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_authorized_users(users_set):
    with open(AUTHORIZED_USERS_FILE, "w") as f:
        json.dump(list(users_set), f)

authorized_users = load_authorized_users()

# ─────────────────────────────────────────────────────────────
# AUTHORIZATION
# ─────────────────────────────────────────────────────────────

def is_authorized(user_id: int) -> bool:
    if config.ADMIN_ID and str(user_id) == str(config.ADMIN_ID):
        return True
    return user_id in authorized_users

async def check_auth(update: Update) -> bool:
    user_id = update.effective_user.id
    if is_authorized(user_id):
        return True
    uid_str = f"`{user_id}`"
    msg = (
        "🔒 *ACCESS DENIED*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Your ID: {uid_str}\n"
        "Contact the administrator to request access."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    return False

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# UI CONSTANTS
# ─────────────────────────────────────────────────────────────

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"

# ─────────────────────────────────────────────────────────────
# MENUS (Inline Keyboards)
# ─────────────────────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡  Launch Verification", callback_data="launch_verify")],
        [
            InlineKeyboardButton("📊 Status", callback_data="show_status"),
            InlineKeyboardButton("📖 Help",   callback_data="show_help"),
        ],
    ])

def verify_info_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ])

# ─────────────────────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    user = update.effective_user
    now = datetime.now().strftime("%d %b %Y · %H:%M")
    msg = (
        "🛡️ *SHEERID PLATINUM*\n"
        f"{DIVIDER}\n"
        f"👤 User: *{user.first_name}*\n"
        f"🟢 Status: *Online*\n"
        f"🕐 Time: `{now}`\n"
        f"{DIVIDER}\n"
        "_Paste a SheerID link directly or use the menu below._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await _send_help(update.message.reply_text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await _send_status(update.message.reply_text)

# ─────────────────────────────────────────────────────────────
# CALLBACK QUERY HANDLER (Inline Button Presses)
# ─────────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not is_authorized(user_id):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    data = query.data

    if data == "main_menu":
        user = query.from_user
        now = datetime.now().strftime("%d %b %Y · %H:%M")
        msg = (
            "🛡️ *SHEERID PLATINUM*\n"
            f"{DIVIDER}\n"
            f"👤 User: *{user.first_name}*\n"
            f"🟢 Status: *Online*\n"
            f"🕐 Time: `{now}`\n"
            f"{DIVIDER}\n"
            "_Paste a SheerID link directly or use the menu below._"
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())

    elif data == "show_status":
        await _send_status(query.edit_message_text, edit=True)

    elif data == "show_help":
        await _send_help(query.edit_message_text, edit=True)

    elif data == "launch_verify":
        msg = (
            "⚡ *READY TO VERIFY*\n"
            f"{DIVIDER}\n"
            "Paste your SheerID verification link directly into the chat.\n\n"
            "You can also use:\n`/verify <link>`"
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=verify_info_keyboard())

# ─────────────────────────────────────────────────────────────
# STATUS & HELP (Shared Renderers)
# ─────────────────────────────────────────────────────────────

async def _send_status(reply_func, edit=False):
    # Check SheerID API connectivity
    try:
        socket.create_connection(("services.sheerid.com", 443), timeout=5)
        api_status = "🟢 Connected"
    except Exception:
        api_status = "🔴 Unreachable"

    proxy_status = "🟢 Active" if config.USE_PROXY else "⚪ Disabled"
    proxy_url_display = f"`{config.PROXY_URL[:30]}...`" if config.USE_PROXY else "_None_"

    msg = (
        "📊 *SYSTEM STATUS*\n"
        f"{DIVIDER}\n"
        f"🌐 SheerID API  → {api_status}\n"
        f"🔀 Proxy        → {proxy_status}\n"
        f"📄 Doc Engine   → 🟢 Ready\n"
        f"🎓 Identity DB  → 🟢 Loaded\n"
        f"{DIVIDER}\n"
        f"🔗 Proxy: {proxy_url_display}\n"
        f"🕐 Checked: `{datetime.now().strftime('%H:%M:%S')}`"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
    if edit:
        await reply_func(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await reply_func(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def _send_help(reply_func, edit=False):
    msg = (
        "📖 *HOW TO USE*\n"
        f"{DIVIDER}\n"
        "*Step 1 — Get the Link*\n"
        "Open the SheerID offer page and copy the verification URL.\n\n"
        "*Step 2 — Paste or Command*\n"
        "Paste the link directly here, or type:\n"
        "`/verify <link>`\n\n"
        "*Step 3 — Wait*\n"
        "The bot will auto-generate a fake student profile, submit it, and handle document uploads if needed.\n\n"
        f"{DIVIDER}\n"
        "📌 *Requirements*\n"
        "• US residential proxy (configured)\n"
        "• Valid SheerID program link\n\n"
        "🔧 *Admin Commands*\n"
        "• `/approve <id>` — Grant access\n"
        "• `/revoke <id>`  — Revoke access\n"
        "• `/users`        — List authorized users"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
    if edit:
        await reply_func(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await reply_func(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

# ─────────────────────────────────────────────────────────────
# VERIFY COMMAND
# ─────────────────────────────────────────────────────────────

async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    user_id = update.effective_user.id

    if user_id in active_tasks:
        await update.message.reply_text(
            "⚠️ *Already Running*\nYou have a verification in progress. Please wait for it to finish.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❌ *Missing Link*\nUsage: `/verify <sheerid_url>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    url = context.args[0]
    user = update.effective_user
    active_tasks.add(user_id)

    try:
        client = sheerid_api.SheerIDClient(proxy=config.PROXY_URL if config.USE_PROXY else None)

        verification_id, is_program = client.extract_verification_id_from_url(url)
        if not verification_id:
            await update.message.reply_text(
                "❌ *Invalid Link*\nCould not extract a Verification ID from the URL.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # ── Phase 1: Init ──────────────────────────────────
        tid = verification_id[:16]
        phase1 = (
            "⚡ *VERIFICATION STARTED*\n"
            f"{DIVIDER}\n"
            f"🆔 Task: `{tid}...`\n"
            f"👤 User: *{user.first_name}*\n"
            f"🕐 Time: `{datetime.now().strftime('%H:%M:%S')}`\n"
            f"{DIVIDER}\n"
            "🔬 _Phase 1/4 · Building identity profile..._"
        )
        status_msg = await update.message.reply_text(phase1, parse_mode=ParseMode.MARKDOWN)

        # ── Phase 2: Profile Generated ─────────────────────
        profile = student_generator.generate_student_profile()
        univ_name = profile["display_info"]["university"]
        student_name = profile["display_info"]["full_name"]
        email = profile["email"]

        phase2 = (
            "⚡ *VERIFICATION IN PROGRESS*\n"
            f"{DIVIDER}\n"
            f"🎓 Identity: *{student_name}*\n"
            f"🏫 School: _{univ_name}_\n"
            f"📧 Email: `{email[:28]}`\n"
            f"{DIVIDER}\n"
            "📡 _Phase 2/4 · Submitting to SheerID API..._"
        )
        await status_msg.edit_text(phase2, parse_mode=ParseMode.MARKDOWN)

        # ── Phase 3: Submit ────────────────────────────────
        def doc_gen_wrapper(first, last, school):
            if doc_generator.select_document_type() == "student_id":
                return doc_generator.generate_student_id(first, last, school)
            else:
                return doc_generator.generate_transcript(first, last, profile["birthDate"], school)

        phase3 = (
            "⚡ *VERIFICATION IN PROGRESS*\n"
            f"{DIVIDER}\n"
            f"🎓 Identity: *{student_name}*\n"
            f"🏫 School: _{univ_name}_\n"
            f"📧 Email: `{email[:28]}`\n"
            f"{DIVIDER}\n"
            "📄 _Phase 3/4 · Processing documents..._"
        )
        await status_msg.edit_text(phase3, parse_mode=ParseMode.MARKDOWN)

        result = client.process_verification(verification_id, is_program, profile, doc_gen_wrapper)

        # ── Phase 4: Result ────────────────────────────────
        status = result.get("status", "UNKNOWN")

        if status == "SUCCESS":
            success = (
                "✅ *VERIFICATION COMPLETE*\n"
                f"{DIVIDER}\n"
                f"🎓 Identity: *{student_name}*\n"
                f"🏫 School: _{univ_name}_\n"
                f"📧 Email: `{email}`\n"
                f"{DIVIDER}\n"
            )
            if result.get("reward_code"):
                success += f"🎁 Code: `{result['reward_code']}`\n"
            if result.get("redirect_url"):
                success += f"🔗 [Claim Reward]({result['redirect_url']})\n"
            success += f"\n🔒 _Session terminated securely._"
            await status_msg.edit_text(success, parse_mode=ParseMode.MARKDOWN)

        elif status == "TIMEOUT":
            last_step = result.get("last_details", {}).get("currentStep")
            if last_step == "pending":
                pending = (
                    "⏳ *MANUAL REVIEW QUEUED*\n"
                    f"{DIVIDER}\n"
                    "Documents were submitted. SheerID is reviewing them manually.\n"
                    "You will be notified when the review is complete (up to 30 min).\n"
                    f"{DIVIDER}\n"
                    f"🔗 Reference: `{url[:40]}...`"
                )
                await status_msg.edit_text(pending, parse_mode=ParseMode.MARKDOWN)
                import subprocess
                subprocess.Popen(["python3", "monitor_task.py", verification_id, str(update.effective_chat.id)])
            else:
                await status_msg.edit_text(
                    "⌛ *TIMEOUT*\nNo response from SheerID. Try again with a fresh link.",
                    parse_mode=ParseMode.MARKDOWN
                )

        else:
            reason = result.get("reason")
            if isinstance(reason, list):
                reason = ", ".join(reason)
            elif isinstance(result.get("details"), dict):
                reason = result["details"].get("systemErrorMessage", "Unknown")
            error_msg = str(reason or status)[:60]

            failed = (
                "❌ *VERIFICATION FAILED*\n"
                f"{DIVIDER}\n"
                f"🚨 Reason: _{error_msg}_\n"
                f"🏫 School: {univ_name[:30]}\n"
                f"{DIVIDER}\n"
                "💡 _Try a fresh link. IP or session may be tainted._"
            )
            await status_msg.edit_text(failed, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        import traceback
        logger.error(f"verify_command error: {e}\n{traceback.format_exc()}")
        try:
            await status_msg.edit_text(
                f"💥 *System Error*\n`{str(e)[:80]}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await update.message.reply_text(
                f"💥 *System Error*\n`{str(e)[:80]}`",
                parse_mode=ParseMode.MARKDOWN
            )
    finally:
        active_tasks.discard(user_id)

# ─────────────────────────────────────────────────────────────
# BOT INITIALIZATION
# ─────────────────────────────────────────────────────────────

def run_bot():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ CONFIG ERROR: Set TELEGRAM_BOT_TOKEN in .env")
        return

    application = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Core commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("verify", verify_command))

    # Inline button callbacks
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Raw SheerID link detection
    async def handle_raw_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await check_auth(update):
            return
        text = update.message.text
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
            uid = int(context.args[0])
            authorized_users.add(uid)
            save_authorized_users(authorized_users)
            await update.message.reply_text(f"✅ User `{uid}` authorized.", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID.")

    async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(config.ADMIN_ID):
            return
        if not context.args:
            await update.message.reply_text("Usage: `/revoke <user_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            uid = int(context.args[0])
            if uid in authorized_users:
                authorized_users.remove(uid)
                save_authorized_users(authorized_users)
                await update.message.reply_text(f"🚫 User `{uid}` access revoked.", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(f"User `{uid}` not found in authorized list.", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID.")

    async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(config.ADMIN_ID):
            return
        if not authorized_users:
            await update.message.reply_text("No authorized users (excluding admin).")
            return
        users_list = "\n".join([f"• `{uid}`" for uid in authorized_users])
        await update.message.reply_text(
            f"👥 *Authorized Users*\n{DIVIDER}\n{users_list}",
            parse_mode=ParseMode.MARKDOWN
        )

    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("revoke", revoke_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_raw_message))

    print("✅ SHEERID PLATINUM BOT ONLINE. Press Ctrl+C to terminate.")
    application.run_polling()


if __name__ == "__main__":
    run_bot()
