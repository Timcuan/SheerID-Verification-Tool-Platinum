"""
Telegram Bot Interface for SheerID Verification
PLATINUM EDITION — Mobile-First UI
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

# ═══════════════════════════════════════════════
# PERSISTENCE
# ═══════════════════════════════════════════════

AUTHORIZED_USERS_FILE = "authorized_users.json"
active_tasks: set = set()

def load_authorized_users() -> set:
    if not os.path.exists(AUTHORIZED_USERS_FILE):
        return set()
    try:
        with open(AUTHORIZED_USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Expected a list")
        return set(int(uid) for uid in data)
    except Exception as e:
        logging.getLogger(__name__).error(f"[AUTH] Load failed: {e}")
        return set()

def save_authorized_users(users_set: set) -> bool:
    try:
        dir_path = os.path.dirname(os.path.abspath(AUTHORIZED_USERS_FILE)) or "."
        fd, tmp = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sorted(int(u) for u in users_set), f, indent=2)
            shutil.move(tmp, AUTHORIZED_USERS_FILE)
        except Exception:
            os.unlink(tmp)
            raise
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f"[AUTH] Save failed: {e}")
        return False

authorized_users: set = load_authorized_users()

# ═══════════════════════════════════════════════
# AUTHORIZATION
# ═══════════════════════════════════════════════

def get_admin_id() -> int | None:
    try:
        return int(config.ADMIN_ID) if config.ADMIN_ID else None
    except (ValueError, TypeError):
        return None

def is_admin(user_id: int) -> bool:
    admin = get_admin_id()
    return admin is not None and user_id == admin

def is_authorized(user_id: int) -> bool:
    return is_admin(user_id) or user_id in authorized_users

async def _reply(update: Update, text: str, **kwargs):
    """Send a reply that works for both message and callback_query updates."""
    if update.message:
        return await update.message.reply_text(text, **kwargs)
    if update.callback_query and update.callback_query.message:
        return await update.callback_query.message.reply_text(text, **kwargs)

async def check_auth(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    if is_authorized(user.id):
        return True
    logging.getLogger(__name__).warning(
        f"[AUTH] Denied: id={user.id} @{getattr(user, 'username', '?')}"
    )
    await _reply(
        update,
        "\U0001f512 *Akses Ditolak*\n\n"
        f"ID kamu: `{user.id}`\n"
        "Hubungi admin untuk meminta akses.",
        parse_mode=ParseMode.MARKDOWN
    )
    return False

# ═══════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════

def kb_main():
    """Main menu — 3 rows, mobile-friendly."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u26a1 Mulai Verifikasi", callback_data="launch_verify")],
        [
            InlineKeyboardButton("\U0001f4ca Status Sistem", callback_data="show_status"),
            InlineKeyboardButton("\U0001f4cb Panduan",       callback_data="show_help"),
        ],
    ])

def kb_back():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2190 Kembali ke Menu", callback_data="main_menu")]
    ])

def kb_verify_ready():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2190 Kembali ke Menu", callback_data="main_menu")]
    ])

# ═══════════════════════════════════════════════
# TEXT TEMPLATES
# ═══════════════════════════════════════════════

def txt_home(user_first_name: str) -> str:
    now = datetime.now().strftime("%H:%M")
    return (
        "\U0001f6e1 *SheerID Platinum Bot*\n\n"
        f"Halo, *{user_first_name}!* \U0001f44b\n"
        f"Sistem aktif pukul `{now}`. Semua siap.\n\n"
        "Pilih menu di bawah untuk mulai:"
    )

def txt_verify_ready() -> str:
    return (
        "\u26a1 *Siap Verifikasi!*\n\n"
        "Tinggal salin \u0026 tempel link SheerID kamu langsung ke sini.\n\n"
        "Contoh format:\n"
        "`https://services.sheerid.com/verify/...`\n\n"
        "_Bot akan otomatis mendeteksi link-nya._"
    )

def txt_status(api_ok: bool) -> str:
    api = "\U0001f7e2 Terhubung" if api_ok else "\U0001f534 Tidak Terjangkau"
    proxy = "\U0001f7e2 Aktif" if config.USE_PROXY else "\u26aa Nonaktif"
    now = datetime.now().strftime("%H:%M:%S")
    return (
        "\U0001f4ca *Status Sistem*\n\n"
        f"\U0001f310 SheerID API \u2014 {api}\n"
        f"\U0001f500 Proxy \u2014 {proxy}\n"
        f"\U0001f4c4 Dokumen Engine \u2014 \U0001f7e2 Siap\n"
        f"\U0001f393 Database ID \u2014 \U0001f7e2 Dimuat\n\n"
        f"\U0001f550 Dicek pukul `{now}`"
    )

def txt_help() -> str:
    return (
        "\U0001f4cb *Panduan Penggunaan*\n\n"
        "*1\ufe0f\u20e3 Dapatkan Link*\n"
        "Buka halaman promo SheerID dan salin link verifikasinya.\n\n"
        "*2\ufe0f\u20e3 Tempel ke Bot*\n"
        "Paste langsung di sini, atau ketik:\n"
        "`/verify <link>`\n\n"
        "*3\ufe0f\u20e3 Tunggu Proses*\n"
        "Bot akan buat profil mahasiswa palsu, submit, dan upload dokumen \u2014 otomatis.\n\n"
        "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
        "\U0001f4cc *Syarat:*\n"
        "\u2022 Proxy residensial US (sudah terpasang)\n"
        "\u2022 Link program SheerID yang valid\n\n"
        "\U0001f527 *Perintah Admin:*\n"
        "`/approve <id>` \u2014 Beri akses\n"
        "`/revoke <id>`  \u2014 Cabut akses\n"
        "`/users`        \u2014 Daftar pengguna"
    )

# ═══════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(
        txt_home(update.effective_user.first_name),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_main()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(txt_help(), parse_mode=ParseMode.MARKDOWN, reply_markup=kb_back())

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    try:
        socket.create_connection(("services.sheerid.com", 443), timeout=5)
        api_ok = True
    except Exception:
        api_ok = False
    await update.message.reply_text(txt_status(api_ok), parse_mode=ParseMode.MARKDOWN, reply_markup=kb_back())

# ═══════════════════════════════════════════════
# CALLBACK HANDLER (Inline Buttons)
# ═══════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_authorized(query.from_user.id):
        await query.answer("\u26d4 Akses ditolak", show_alert=True)
        return

    data = query.data

    if data == "main_menu":
        await query.edit_message_text(
            txt_home(query.from_user.first_name),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main()
        )

    elif data == "show_status":
        try:
            socket.create_connection(("services.sheerid.com", 443), timeout=5)
            api_ok = True
        except Exception:
            api_ok = False
        await query.edit_message_text(
            txt_status(api_ok),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_back()
        )

    elif data == "show_help":
        await query.edit_message_text(
            txt_help(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_back()
        )

    elif data == "launch_verify":
        await query.edit_message_text(
            txt_verify_ready(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_verify_ready()
        )

# ═══════════════════════════════════════════════
# VERIFY COMMAND
# ═══════════════════════════════════════════════

SPINNERS = ["\U0001f4e1", "\u2699\ufe0f", "\U0001f504", "\u23f3"]

async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    user_id = update.effective_user.id

    if user_id in active_tasks:
        await update.message.reply_text(
            "\u23f3 *Masih Berjalan*\n\n"
            "Verifikasi kamu sebelumnya belum selesai.\n"
            "Tunggu dulu ya!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if not context.args:
        await update.message.reply_text(
            "\u274c *Link Tidak Ditemukan*\n\n"
            "Gunakan perintah ini:\n"
            "`/verify <link_sheerid>`\n\n"
            "Atau paste langsung link-nya ke chat.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    url = context.args[0]
    user = update.effective_user
    active_tasks.add(user_id)
    status_msg = None

    try:
        client = sheerid_api.SheerIDClient(proxy=config.PROXY_URL if config.USE_PROXY else None)

        # Ekstrak ID verifikasi (non-blocking)
        verification_id, is_program = await asyncio.to_thread(
            client.extract_verification_id_from_url, url
        )
        if not verification_id:
            await update.message.reply_text(
                "\u274c *Link Tidak Valid*\n\n"
                "Pastikan link yang kamu kirim adalah link verifikasi SheerID yang benar.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        tid = verification_id[:14]

        # Fase 1 — Inisialisasi
        status_msg = await update.message.reply_text(
            "\u26a1 *Verifikasi Dimulai*\n\n"
            f"\U0001f194 ID: `{tid}...`\n"
            f"\U0001f464 Pengguna: *{user.first_name}*\n"
            f"\U0001f550 Waktu: `{datetime.now().strftime('%H:%M:%S')}`\n\n"
            "\U0001f52c _Fase 1/4 \u2014 Membuat profil identitas..._",
            parse_mode=ParseMode.MARKDOWN
        )

        # Fase 2 — Generate profil (non-blocking)
        profile = await asyncio.to_thread(student_generator.generate_student_profile)
        univ = profile["display_info"]["university"]
        name = profile["display_info"]["full_name"]
        email = profile["email"]

        await status_msg.edit_text(
            "\u26a1 *Sedang Memproses...*\n\n"
            f"\U0001f393 *{name}*\n"
            f"\U0001f3eb _{univ}_\n"
            f"\U0001f4e7 `{email[:28]}`\n\n"
            "\U0001f4e1 _Fase 2/4 \u2014 Mengirim ke SheerID API..._",
            parse_mode=ParseMode.MARKDOWN
        )

        # Fase 3 — Submit + live ticker
        def doc_gen(first, last, school):
            if doc_generator.select_document_type() == "student_id":
                return doc_generator.generate_student_id(first, last, school)
            return doc_generator.generate_transcript(first, last, profile["birthDate"], school)

        ticker_done = asyncio.Event()

        async def live_ticker():
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
                        f"{icon} *Memproses Dokumen...*\n\n"
                        f"\U0001f393 *{name}*\n"
                        f"\U0001f3eb _{univ}_\n"
                        f"\U0001f4e7 `{email[:28]}`\n\n"
                        f"_Fase 3/4 \u2014 Berkomunikasi dengan SheerID... ({elapsed}d)_",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass

        ticker_task = asyncio.create_task(live_ticker())
        try:
            result = await asyncio.to_thread(
                client.process_verification, verification_id, is_program, profile, doc_gen
            )
        finally:
            ticker_done.set()
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass

        # Fase 4 — Tampilkan hasil
        outcome = result.get("status", "UNKNOWN")

        if outcome == "SUCCESS":
            msg = (
                "\u2705 *Verifikasi Berhasil!*\n\n"
                f"\U0001f393 *{name}*\n"
                f"\U0001f3eb _{univ}_\n"
                f"\U0001f4e7 `{email}`\n"
            )
            if result.get("reward_code"):
                msg += f"\n\U0001f381 Kode: `{result['reward_code']}`"
            if result.get("redirect_url"):
                msg += f"\n\U0001f517 [Klaim Hadiah]({result['redirect_url']})"
            msg += "\n\n\U0001f512 _Sesi selesai dengan aman._"
            await status_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

        elif outcome == "TIMEOUT":
            last_step = result.get("last_details", {}).get("currentStep")
            if last_step == "pending":
                await status_msg.edit_text(
                    "\u23f3 *Menunggu Review Manual*\n\n"
                    "Dokumen sudah dikirim.\n"
                    "SheerID sedang mereview secara manual.\n\n"
                    "_Kamu akan diberi notifikasi (maks. 30 menit)._",
                    parse_mode=ParseMode.MARKDOWN
                )
                import subprocess
                subprocess.Popen(["python3", "monitor_task.py", verification_id, str(update.effective_chat.id)])
            else:
                await status_msg.edit_text(
                    "\u231b *Timeout*\n\n"
                    "Tidak ada respons dari SheerID.\n"
                    "Coba lagi dengan link yang baru.",
                    parse_mode=ParseMode.MARKDOWN
                )

        else:
            reason = result.get("reason")
            if isinstance(reason, list):
                reason = ", ".join(reason)
            elif isinstance(result.get("details"), dict):
                reason = result["details"].get("systemErrorMessage", "Unknown")
            err = str(reason or outcome)[:80]
            await status_msg.edit_text(
                "\u274c *Verifikasi Gagal*\n\n"
                f"\U0001f6a8 Alasan: _{err}_\n\n"
                "\U0001f4a1 _Coba link baru. IP atau sesi mungkin sudah terkontaminasi._",
                parse_mode=ParseMode.MARKDOWN
            )

    except Exception as e:
        import traceback
        logger.error(f"verify_command error: {e}\n{traceback.format_exc()}")
        err_text = (
            "\U0001f4a5 *Error Sistem*\n\n"
            f"`{str(e)[:80]}`"
        )
        try:
            if status_msg:
                await status_msg.edit_text(err_text, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(err_text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
    finally:
        active_tasks.discard(user_id)

# ═══════════════════════════════════════════════
# BOT STARTUP
# ═══════════════════════════════════════════════

def run_bot():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\u274c CONFIG ERROR: Set TELEGRAM_BOT_TOKEN in .env")
        return

    application = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Core commands
    application.add_handler(CommandHandler("start",  start))
    application.add_handler(CommandHandler("help",   help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("verify", verify_command))

    # Inline button callback
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Auto-detect pasted SheerID links in plain messages
    async def handle_raw(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await check_auth(update):
            return
        text = update.message.text or ""
        match = re.search(r'(https?://[^\s]+sheerid\.com/verify[^\s]*)', text)
        if match:
            context.args = [match.group(1)]
            await verify_command(update, context)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_raw))

    # ── Admin commands ───────────────────────────────────────

    def _require_admin(uid: int) -> bool:
        return get_admin_id() is not None and is_admin(uid)

    async def _no_admin_cfg(update: Update):
        await update.message.reply_text(
            "\u26a0\ufe0f `ADMIN_ID` belum diatur di `.env`.\n"
            "Perintah admin tidak aktif.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if get_admin_id() is None:
            await _no_admin_cfg(update); return
        if not is_admin(update.effective_user.id):
            return
        if not context.args:
            await update.message.reply_text("Penggunaan: `/approve <user_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            uid = int(context.args[0])
            if is_admin(uid):
                await update.message.reply_text("\u2139\ufe0f User tersebut sudah menjadi admin.")
                return
            authorized_users.add(uid)
            if save_authorized_users(authorized_users):
                await update.message.reply_text(f"\u2705 User `{uid}` berhasil diberi akses.", parse_mode=ParseMode.MARKDOWN)
            else:
                authorized_users.discard(uid)
                await update.message.reply_text("\u274c Gagal menyimpan. Cek ruang disk/permission.")
        except ValueError:
            await update.message.reply_text("\u274c ID tidak valid \u2014 harus berupa angka.")

    async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if get_admin_id() is None:
            await _no_admin_cfg(update); return
        if not is_admin(update.effective_user.id):
            return
        if not context.args:
            await update.message.reply_text("Penggunaan: `/revoke <user_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            uid = int(context.args[0])
            if is_admin(uid):
                await update.message.reply_text("\u26d4 Tidak bisa mencabut akses admin sendiri.")
                return
            if uid not in authorized_users:
                await update.message.reply_text(f"User `{uid}` tidak ada dalam daftar.", parse_mode=ParseMode.MARKDOWN)
                return
            authorized_users.remove(uid)
            if save_authorized_users(authorized_users):
                await update.message.reply_text(f"\U0001f6ab Akses user `{uid}` dicabut.", parse_mode=ParseMode.MARKDOWN)
            else:
                authorized_users.add(uid)
                await update.message.reply_text("\u274c Gagal menyimpan. Cek ruang disk/permission.")
        except ValueError:
            await update.message.reply_text("\u274c ID tidak valid \u2014 harus berupa angka.")

    async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if get_admin_id() is None:
            await _no_admin_cfg(update); return
        if not is_admin(update.effective_user.id):
            return
        if not authorized_users:
            await update.message.reply_text("Belum ada pengguna yang diizinkan (selain admin).")
            return
        count = len(authorized_users)
        rows = "\n".join(f"\u2022 `{uid}`" for uid in sorted(authorized_users))
        await update.message.reply_text(
            f"\U0001f465 *Pengguna Terotorisasi* ({count})\n\n{rows}",
            parse_mode=ParseMode.MARKDOWN
        )

    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("revoke",  revoke_command))
    application.add_handler(CommandHandler("users",   users_command))

    print("\u2705 SHEERID PLATINUM BOT ONLINE")

    # Register command menu (shows in "/" picker on Telegram clients)
    async def post_init(app):
        from telegram import BotCommand
        commands = [
            BotCommand("start",  "Menu utama"),
            BotCommand("verify", "Verifikasi link SheerID"),
            BotCommand("status", "Status sistem"),
            BotCommand("help",   "Panduan penggunaan"),
        ]
        await app.bot.set_my_commands(commands)

    application.post_init = post_init
    application.run_polling()


if __name__ == "__main__":
    run_bot()
