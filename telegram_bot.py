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
import tempfile
import shutil

# -----------------------------------------------------------------
# PERSISTENCE — Thread-safe, atomic file writes
# -----------------------------------------------------------------

AUTHORIZED_USERS_FILE = "authorized_users.json"
active_tasks: set = set()  # Per-user concurrency lock

def load_authorized_users() -> set:
    """Load authorized users from disk. Returns empty set on any failure."""
    if not os.path.exists(AUTHORIZED_USERS_FILE):
        return set()
    try:
        with open(AUTHORIZED_USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Expected a list in authorized_users.json")
        return set(int(uid) for uid in data)
    except Exception as e:
        logger_init = logging.getLogger(__name__)
        logger_init.error(f"[AUTH] Could not load {AUTHORIZED_USERS_FILE}: {e}. Starting with empty set.")
        return set()

def save_authorized_users(users_set: set) -> bool:
    """
    Atomically save authorized users to disk.
    Writes to a temp file first, then renames, so the main file is never corrupted.
    Returns True on success, False on failure.
    """
    try:
        dir_path = os.path.dirname(os.path.abspath(AUTHORIZED_USERS_FILE)) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sorted(int(uid) for uid in users_set), f, indent=2)
            shutil.move(tmp_path, AUTHORIZED_USERS_FILE)
        except Exception:
            os.unlink(tmp_path)
            raise
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f"[AUTH] Failed to save authorized users: {e}")
        return False

authorized_users: set = load_authorized_users()

# -----------------------------------------------------------------
# AUTHORIZATION
# -----------------------------------------------------------------

def get_admin_id() -> int | None:
    """Safely retrieve ADMIN_ID as int, or None if not configured."""
    try:
        return int(config.ADMIN_ID) if config.ADMIN_ID else None
    except (ValueError, TypeError):
        return None

def is_admin(user_id: int) -> bool:
    """Check if user_id is the configured admin."""
    admin = get_admin_id()
    return admin is not None and user_id == admin

def is_authorized(user_id: int) -> bool:
    """Return True if user is admin or in the authorized_users set."""
    return is_admin(user_id) or user_id in authorized_users

async def get_reply_fn(update: Update):
    """Return the correct reply function regardless of update type."""
    if update.message:
        return update.message.reply_text
    if update.callback_query:
        return update.callback_query.message.reply_text
    return None

async def check_auth(update: Update) -> bool:
    """
    Verify the user is authorized.
    Works for both command and callback_query contexts.
    Logs all unauthorized access attempts.
    """
    user = update.effective_user
    if user is None:
        return False
    user_id = user.id
    if is_authorized(user_id):
        return True

    # Log unauthorized attempt
    logging.getLogger(__name__).warning(
        f"[AUTH] Unauthorized access attempt: user_id={user_id} "
        f"username=@{getattr(user, 'username', 'N/A')} "
        f"name={getattr(user, 'full_name', 'N/A')}"
    )

    msg = (
        "\U0001f512 *ACCESS DENIED*\n"
        f"Your ID: `{user_id}`\n"
        "Contact the administrator to request access."
    )
    reply_fn = await get_reply_fn(update)
    if reply_fn:
        try:
            await reply_fn(msg, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
    return False

# -----------------------------------------------------------------
# LOGGING
# -----------------------------------------------------------------

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------

DIV = "\u2501" * 22

# -----------------------------------------------------------------
# MENUS
# -----------------------------------------------------------------

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u26a1  Launch Verification", callback_data="launch_verify")],
        [
            InlineKeyboardButton("\U0001f4ca Status",  callback_data="show_status"),
            InlineKeyboardButton("\U0001f4d6 Help",    callback_data="show_help"),
        ],
    ])

def back_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="main_menu")]
    ])

# -----------------------------------------------------------------
# SHARED RENDERERS
# -----------------------------------------------------------------

async def render_status(send_fn, edit=False):
    try:
        socket.create_connection(("services.sheerid.com", 443), timeout=5)
        api_status = "\U0001f7e2 Connected"
    except Exception:
        api_status = "\U0001f534 Unreachable"

    proxy_status = "\U0001f7e2 Active" if config.USE_PROXY else "\u26aa Disabled"
    proxy_display = f"`{config.PROXY_URL[:30]}...`" if config.USE_PROXY else "_None_"

    msg = (
        "\U0001f4ca *SYSTEM STATUS*\n"
        f"{DIV}\n"
        f"\U0001f310 SheerID API  \u2192 {api_status}\n"
        f"\U0001f500 Proxy        \u2192 {proxy_status}\n"
        f"\U0001f4c4 Doc Engine   \u2192 \U0001f7e2 Ready\n"
        f"\U0001f393 Identity DB  \u2192 \U0001f7e2 Loaded\n"
        f"{DIV}\n"
        f"\U0001f517 Proxy: {proxy_display}\n"
        f"\U0001f550 Checked: `{datetime.now().strftime('%H:%M:%S')}`"
    )
    await send_fn(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

async def render_help(send_fn, edit=False):
    msg = (
        "\U0001f4d6 *HOW TO USE*\n"
        f"{DIV}\n"
        "*Step 1 \u2014 Get the Link*\n"
        "Open the SheerID offer page and copy the verification URL.\n\n"
        "*Step 2 \u2014 Start Verification*\n"
        "Paste the link directly in chat, or use:\n"
        "`/verify <link>`\n\n"
        "*Step 3 \u2014 Wait*\n"
        "The bot will auto-generate a student profile, submit it, and handle document uploads automatically.\n\n"
        f"{DIV}\n"
        "\U0001f4cc *Requirements*\n"
        "\u2022 US residential proxy (configured)\n"
        "\u2022 Valid SheerID program link\n\n"
        "\U0001f527 *Admin Commands*\n"
        "\u2022 `/approve <id>` \u2014 Grant access\n"
        "\u2022 `/revoke <id>`  \u2014 Revoke access\n"
        "\u2022 `/users`        \u2014 List authorized users"
    )
    await send_fn(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

# -----------------------------------------------------------------
# COMMAND HANDLERS
# -----------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    user = update.effective_user
    now = datetime.now().strftime("%d %b %Y \u00b7 %H:%M")
    msg = (
        "\U0001f6e1\ufe0f *SHEERID PLATINUM*\n"
        f"{DIV}\n"
        f"\U0001f464 User: *{user.first_name}*\n"
        f"\U0001f7e2 Status: *Online*\n"
        f"\U0001f550 Time: `{now}`\n"
        f"{DIV}\n"
        "_Paste a SheerID link or use the menu below._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await render_help(update.message.reply_text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await render_status(update.message.reply_text)

# -----------------------------------------------------------------
# CALLBACK HANDLER
# -----------------------------------------------------------------

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_authorized(query.from_user.id):
        await query.answer("\u26d4 Access Denied", show_alert=True)
        return

    data = query.data

    if data == "main_menu":
        user = query.from_user
        now = datetime.now().strftime("%d %b %Y \u00b7 %H:%M")
        msg = (
            "\U0001f6e1\ufe0f *SHEERID PLATINUM*\n"
            f"{DIV}\n"
            f"\U0001f464 User: *{user.first_name}*\n"
            f"\U0001f7e2 Status: *Online*\n"
            f"\U0001f550 Time: `{now}`\n"
            f"{DIV}\n"
            "_Paste a SheerID link or use the menu below._"
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

    elif data == "show_status":
        await render_status(query.edit_message_text, edit=True)

    elif data == "show_help":
        await render_help(query.edit_message_text, edit=True)

    elif data == "launch_verify":
        msg = (
            "\u26a1 *READY TO VERIFY*\n"
            f"{DIV}\n"
            "Paste your SheerID verification link directly in the chat.\n\n"
            "Or use: `/verify <link>`"
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

# -----------------------------------------------------------------
# VERIFY COMMAND
# -----------------------------------------------------------------

async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    user_id = update.effective_user.id

    if user_id in active_tasks:
        await update.message.reply_text(
            "\u26a0\ufe0f *Already Running*\nYou have a verification in progress. Please wait.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if not context.args:
        await update.message.reply_text(
            "\u274c *Missing Link*\nUsage: `/verify <sheerid_url>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    url = context.args[0]
    user = update.effective_user
    active_tasks.add(user_id)
    status_msg = None

    try:
        client = sheerid_api.SheerIDClient(proxy=config.PROXY_URL if config.USE_PROXY else None)

        # Phase 1 — Extract ID (in thread, non-blocking)
        verification_id, is_program = await asyncio.to_thread(
            client.extract_verification_id_from_url, url
        )
        if not verification_id:
            await update.message.reply_text(
                "\u274c *Invalid Link*\nCould not extract a Verification ID from the URL.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        tid = verification_id[:16]
        status_msg = await update.message.reply_text(
            "\u26a1 *VERIFICATION STARTED*\n"
            f"{DIV}\n"
            f"\U0001f194 Task: `{tid}...`\n"
            f"\U0001f464 User: *{user.first_name}*\n"
            f"\U0001f550 Time: `{datetime.now().strftime('%H:%M:%S')}`\n"
            f"{DIV}\n"
            "\U0001f52c _Phase 1/4 \u00b7 Building identity profile..._",
            parse_mode=ParseMode.MARKDOWN
        )

        # Phase 2 — Generate profile (in thread)
        profile = await asyncio.to_thread(student_generator.generate_student_profile)
        univ_name = profile["display_info"]["university"]
        student_name = profile["display_info"]["full_name"]
        email = profile["email"]

        await status_msg.edit_text(
            "\u26a1 *VERIFICATION IN PROGRESS*\n"
            f"{DIV}\n"
            f"\U0001f393 Identity: *{student_name}*\n"
            f"\U0001f3eb School: _{univ_name}_\n"
            f"\U0001f4e7 Email: `{email[:28]}`\n"
            f"{DIV}\n"
            "\U0001f4e1 _Phase 2/4 \u00b7 Submitting to SheerID API..._",
            parse_mode=ParseMode.MARKDOWN
        )

        # Phase 3 — Process & upload docs (blocking, run in thread with live ticker)
        def doc_gen_wrapper(first, last, school):
            if doc_generator.select_document_type() == "student_id":
                return doc_generator.generate_student_id(first, last, school)
            return doc_generator.generate_transcript(first, last, profile["birthDate"], school)

        SPINNERS = ["\U0001f4e1", "\u2699\ufe0f", "\U0001f504", "\u23f3"]
        ticker_done = asyncio.Event()

        async def live_ticker():
            """Edits the progress message every 3 s during the blocking API call."""
            elapsed = 0
            i = 0
            while not ticker_done.is_set():
                await asyncio.sleep(3)
                if ticker_done.is_set():
                    break
                elapsed += 3
                icon = SPINNERS[i % len(SPINNERS)]
                i += 1
                try:
                    await status_msg.edit_text(
                        "\u26a1 *VERIFICATION IN PROGRESS*\n"
                        f"{DIV}\n"
                        f"\U0001f393 Identity: *{student_name}*\n"
                        f"\U0001f3eb School: _{univ_name}_\n"
                        f"\U0001f4e7 Email: `{email[:28]}`\n"
                        f"{DIV}\n"
                        f"{icon} _Phase 3/4 \u00b7 Talking to SheerID... ({elapsed}s)_",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass  # Silently ignore "message not modified" errors

        ticker_task = asyncio.create_task(live_ticker())
        try:
            result = await asyncio.to_thread(
                client.process_verification, verification_id, is_program, profile, doc_gen_wrapper
            )
        finally:
            ticker_done.set()
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass

        # Phase 4 — Show result
        outcome = result.get("status", "UNKNOWN")

        if outcome == "SUCCESS":
            msg = (
                "\u2705 *VERIFICATION COMPLETE*\n"
                f"{DIV}\n"
                f"\U0001f393 Identity: *{student_name}*\n"
                f"\U0001f3eb School: _{univ_name}_\n"
                f"\U0001f4e7 Email: `{email}`\n"
                f"{DIV}\n"
            )
            if result.get("reward_code"):
                msg += f"\U0001f381 Code: `{result['reward_code']}`\n"
            if result.get("redirect_url"):
                msg += f"\U0001f517 [Claim Reward]({result['redirect_url']})\n"
            msg += "\n\U0001f512 _Session terminated securely._"
            await status_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

        elif outcome == "TIMEOUT":
            last_step = result.get("last_details", {}).get("currentStep")
            if last_step == "pending":
                await status_msg.edit_text(
                    "\u23f3 *MANUAL REVIEW QUEUED*\n"
                    f"{DIV}\n"
                    "Documents submitted. SheerID is reviewing manually.\n"
                    "You will be notified when complete (up to 30 min).\n"
                    f"{DIV}\n"
                    f"\U0001f517 Reference: `{url[:40]}...`",
                    parse_mode=ParseMode.MARKDOWN
                )
                import subprocess
                subprocess.Popen(["python3", "monitor_task.py", verification_id, str(update.effective_chat.id)])
            else:
                await status_msg.edit_text(
                    "\u231b *TIMEOUT*\nNo response from SheerID. Try again with a fresh link.",
                    parse_mode=ParseMode.MARKDOWN
                )

        else:
            reason = result.get("reason")
            if isinstance(reason, list):
                reason = ", ".join(reason)
            elif isinstance(result.get("details"), dict):
                reason = result["details"].get("systemErrorMessage", "Unknown")
            error_msg = str(reason or outcome)[:60]

            await status_msg.edit_text(
                "\u274c *VERIFICATION FAILED*\n"
                f"{DIV}\n"
                f"\U0001f6a8 Reason: _{error_msg}_\n"
                f"\U0001f3eb School: {univ_name[:30]}\n"
                f"{DIV}\n"
                "\U0001f4a1 _Try a fresh link. IP or session may be tainted._",
                parse_mode=ParseMode.MARKDOWN
            )

    except Exception as e:
        import traceback
        logger.error(f"verify_command error: {e}\n{traceback.format_exc()}")
        err_text = f"\U0001f4a5 *System Error*\n`{str(e)[:80]}`"
        try:
            if status_msg:
                await status_msg.edit_text(err_text, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(err_text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
    finally:
        active_tasks.discard(user_id)

# -----------------------------------------------------------------
# BOT INITIALIZATION
# -----------------------------------------------------------------

def run_bot():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\u274c CONFIG ERROR: Set TELEGRAM_BOT_TOKEN in .env")
        return

    application = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Core commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("verify", verify_command))

    # Inline button callbacks
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Raw SheerID link detection (in any plain message)
    async def handle_raw_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await check_auth(update):
            return
        text = update.message.text
        match = re.search(r'(https?://[^\s]+sheerid\.com/verify/[^\s]+)', text)
        if match:
            context.args = [match.group(1)]
            await verify_command(update, context)

    # Admin commands — all guarded by is_admin(), not raw string compare
    def _require_admin(uid: int) -> bool:
        return get_admin_id() is not None and is_admin(uid)

    async def _no_admin_configured(update: Update):
        await update.message.reply_text(
            "\u26a0\ufe0f `ADMIN_ID` is not set in `.env`. Admin commands are disabled.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid_caller = update.effective_user.id
        if get_admin_id() is None:
            await _no_admin_configured(update)
            return
        if not is_admin(uid_caller):
            return
        if not context.args:
            await update.message.reply_text("Usage: `/approve <user_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            uid = int(context.args[0])
            if is_admin(uid):
                await update.message.reply_text("\u2139\ufe0f That user is already the admin.")
                return
            authorized_users.add(uid)
            if save_authorized_users(authorized_users):
                await update.message.reply_text(f"\u2705 User `{uid}` authorized.", parse_mode=ParseMode.MARKDOWN)
            else:
                authorized_users.discard(uid)  # Roll back on disk error
                await update.message.reply_text("\u274c Failed to persist. Check disk space/permissions.")
        except ValueError:
            await update.message.reply_text("\u274c Invalid user ID \u2014 must be a number.")

    async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid_caller = update.effective_user.id
        if get_admin_id() is None:
            await _no_admin_configured(update)
            return
        if not is_admin(uid_caller):
            return
        if not context.args:
            await update.message.reply_text("Usage: `/revoke <user_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            uid = int(context.args[0])
            if is_admin(uid):
                await update.message.reply_text("\u26d4 You cannot revoke your own admin access.")
                return
            if uid not in authorized_users:
                await update.message.reply_text(f"User `{uid}` is not in the authorized list.", parse_mode=ParseMode.MARKDOWN)
                return
            authorized_users.remove(uid)
            if save_authorized_users(authorized_users):
                await update.message.reply_text(f"\U0001f6ab User `{uid}` access revoked.", parse_mode=ParseMode.MARKDOWN)
            else:
                authorized_users.add(uid)  # Roll back on disk error
                await update.message.reply_text("\u274c Failed to persist. Check disk space/permissions.")
        except ValueError:
            await update.message.reply_text("\u274c Invalid user ID \u2014 must be a number.")

    async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid_caller = update.effective_user.id
        if get_admin_id() is None:
            await _no_admin_configured(update)
            return
        if not is_admin(uid_caller):
            return
        if not authorized_users:
            await update.message.reply_text("No authorized users (excluding admin).")
            return
        count = len(authorized_users)
        users_list = "\n".join([f"\u2022 `{uid}`" for uid in sorted(authorized_users)])
        await update.message.reply_text(
            f"\U0001f465 *Authorized Users* ({count})\n{DIV}\n{users_list}",
            parse_mode=ParseMode.MARKDOWN
        )


    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("revoke", revoke_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_raw_message))

    print("\u2705 SHEERID PLATINUM BOT ONLINE. Press Ctrl+C to terminate.")
    application.run_polling()


if __name__ == "__main__":
    run_bot()
