import asyncio
import logging
import os
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from media_bot.config import BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS, WORK_DIR, MAX_FILE_MB, MAX_OUTPUT_MB
from media_bot import database as db
from media_bot.keyboards import main_menu, category_keyboard, OPS, cancel_keyboard
from media_bot.processor import process_file

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("mediashaper")

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise RuntimeError("Configura BOT_TOKEN, API_ID y API_HASH en las variables de entorno.")

app = Client("mediashaper_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
pending_files = {}
active_tasks = {}
active_jobs = {}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"MediaShaper Alternative: OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *_):
        return

def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    log.info("Health server listening on port %s", port)
    server.serve_forever()

def get_media(message):
    media = message.document or message.video or message.audio or message.photo or message.animation
    if not media:
        return None
    return media

def media_size(media):
    return getattr(media, "file_size", 0) or 0

def media_name(message, media):
    name = getattr(media, "file_name", None)
    if name:
        return Path(name).name
    if message.photo:
        return f"photo_{message.id}.jpg"
    if message.video:
        return f"video_{message.id}.mp4"
    if message.audio:
        return f"audio_{message.id}.mp3"
    if message.animation:
        return f"animation_{message.id}.gif"
    return f"file_{message.id}"

def supported_category(name, message):
    ext = Path(name).suffix.lower()
    if message.video or ext in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpeg", ".mpg"):
        return "video"
    if message.audio or ext in (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus", ".wma", ".aiff", ".alac"):
        return "audio"
    if message.photo or message.animation or ext in (".jpg", ".jpeg", ".png", ".webp", ".avif", ".heic", ".gif"):
        return "image"
    if ext in (".pdf", ".docx", ".xlsx", ".pptx"):
        return "docs"
    if ext in (".zip", ".tar", ".tgz", ".gz"):
        return "archive"
    return None

def is_admin(user_id):
    return user_id in ADMIN_IDS

@app.on_message(filters.command("start") & filters.private)
async def start(_, message):
    db.ensure_user(message.from_user)
    await message.reply_text(
        "👋 **Bienvenido a MediaShaper Alternative**\n\n"
        "Procesa vídeos, audio, imágenes, documentos y archivos desde Telegram.\n\n"
        "Envía un archivo o selecciona una categoría:",
        reply_markup=main_menu()
    )

@app.on_message(filters.command("help") & filters.private)
async def help_cmd(_, message):
    await message.reply_text(
        "**Comandos disponibles**\n"
        "/start — Menú principal\n/balance — Consultar saldo\n"
        "/history — Últimos trabajos\n/buy — Información de créditos\n"
        "/cancel — Cancelar tu operación activa\n\n"
        "Envía un archivo para ver las operaciones compatibles."
    )

@app.on_message(filters.command("balance") & filters.private)
async def balance_cmd(_, message):
    db.ensure_user(message.from_user)
    free, credits = db.balance(message.from_user.id)
    await message.reply_text(f"🎁 Trabajos gratuitos restantes: **{free}**\n💳 Créditos: **{credits}**")

@app.on_message(filters.command("history") & filters.private)
async def history_cmd(_, message):
    rows = db.history(message.from_user.id)
    if not rows:
        return await message.reply_text("Todavía no tienes operaciones.")
    lines = ["**Tus últimos trabajos:**"]
    for r in rows:
        stamp = time.strftime("%d/%m %H:%M", time.localtime(r["created_at"]))
        lines.append(f"• `{r['operation']}` — {r['status']} — {stamp}")
    await message.reply_text("\n".join(lines))

@app.on_message(filters.command("buy") & filters.private)
async def buy_cmd(_, message):
    await message.reply_text(
        "💳 **Créditos**\n\nEste proyecto incluye el sistema interno de créditos. "
        "La venta automática todavía no está conectada. Contacta con un administrador "
        "para que te asigne créditos."
    )

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(_, message):
    task = active_tasks.get(message.from_user.id)
    if task and not task.done():
        task.cancel()
        await message.reply_text("🛑 Solicitud de cancelación enviada.")
    else:
        await message.reply_text("No tienes ninguna operación activa.")

@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo | filters.animation))
async def receive_file(_, message):
    db.ensure_user(message.from_user)
    media = get_media(message)
    name = media_name(message, media)
    size = media_size(media)
    if size > MAX_FILE_MB * 1024 * 1024:
        return await message.reply_text(f"El límite configurado de entrada es {MAX_FILE_MB} MB.")
    category = supported_category(name, message)
    if not category:
        return await message.reply_text("Formato no reconocido o todavía no compatible.")
    pending_files[message.from_user.id] = {
        "message": message,
        "name": name,
        "category": category,
        "size": size
    }
    await message.reply_text(
        f"📁 **Archivo recibido**\n`{name}`\n"
        f"📦 Tamaño: {size / 1024 / 1024:.2f} MB\n\n"
        "Selecciona qué deseas hacer:",
        reply_markup=category_keyboard(category)
    )

@app.on_callback_query()
async def callbacks(_, query):
    user_id = query.from_user.id
    data = query.data or ""
    await query.answer()
    if data == "home":
        return await query.message.edit_text("Selecciona una categoría o envíame un archivo:", reply_markup=main_menu())
    if data == "balance":
        free, credits = db.balance(user_id)
        return await query.message.edit_text(
            f"🎁 Trabajos gratuitos restantes: **{free}**\n💳 Créditos: **{credits}**",
            reply_markup=main_menu()
        )
    if data == "history":
        rows = db.history(user_id)
        text = "**Historial**\n" + ("\n".join(
            f"• `{r['operation']}` — {r['status']}" for r in rows
        ) if rows else "Todavía no tienes operaciones.")
        return await query.message.edit_text(text, reply_markup=main_menu())
    if data.startswith("cat:"):
        category = data.split(":", 1)[1]
        return await query.message.edit_text("Selecciona una operación:", reply_markup=category_keyboard(category))
    if data == "cancel":
        task = active_tasks.get(user_id)
        if task and not task.done():
            task.cancel()
            return await query.message.edit_text("🛑 Cancelación solicitada. Limpiando el trabajo…")
        return await query.message.edit_text("No hay una operación activa.")
    if data.startswith("op:"):
        if user_id in active_tasks and not active_tasks[user_id].done():
            return await query.message.reply_text("Ya tienes una operación en curso. Cancélala antes de iniciar otra.")
        item = pending_files.get(user_id)
        if not item:
            return await query.message.reply_text("No encuentro un archivo pendiente. Envíalo otra vez.")
        code = data.split(":", 1)[1]
        if not any(code == c for _, c in OPS.get(item["category"], [])):
            return await query.message.reply_text("Esa operación no corresponde al tipo de archivo.")
        allowed, reason = db.can_run(user_id, 1)
        if not allowed:
            return await query.message.reply_text(reason)
        task = asyncio.create_task(run_job(user_id, item, code, query.message))
        active_tasks[user_id] = task

async def run_job(user_id, item, code, menu_message):
    cost = 1
    job_id = None
    work = WORK_DIR / f"{user_id}_{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    status_msg = await menu_message.reply_text(
        "⏳ Preparando archivo…\n`[░░░░░░░░░░] 0%`",
        reply_markup=cancel_keyboard()
    )
    charged = False
    try:
        if not db.charge(user_id, cost):
            raise RuntimeError("No tienes créditos suficientes.")
        charged = True
        job_id = db.add_job(user_id, code, item["name"])
        source = await item["message"].download(file_name=str(work / item["name"]))
        source_path = Path(source)
        last_update = 0

        async def progress(percent):
            nonlocal last_update
            now = time.monotonic()
            if now - last_update < 2 and percent < 95:
                return
            last_update = now
            filled = max(0, min(10, int(percent / 10)))
            bar = "█" * filled + "░" * (10-filled)
            try:
                await status_msg.edit_text(
                    f"⚙️ Procesando: **{percent}%**\n`[{bar}]`",
                    reply_markup=cancel_keyboard()
                )
            except Exception:
                pass

        await progress(5)
        result = await process_file(code, source_path, work / "out", progress)
        await progress(95)
        if not result.exists():
            raise RuntimeError("No se generó el archivo de salida.")
        size_mb = result.stat().st_size / 1024 / 1024
        if size_mb > MAX_OUTPUT_MB:
            raise RuntimeError(f"El resultado supera el límite configurado de {MAX_OUTPUT_MB} MB.")
        await progress(100)
        await app.send_document(
            user_id, str(result),
            caption=f"✅ **Procesamiento terminado**\nOperación: `{code}`\nTamaño: {size_mb:.2f} MB"
        )
        db.finish_job(job_id, "completed", result.name)
        await status_msg.edit_text("✅ Operación completada.")
    except asyncio.CancelledError:
        if job_id:
            db.finish_job(job_id, "cancelled")
        if charged:
            db.refund(user_id, cost)
        try:
            await status_msg.edit_text("🛑 Operación cancelada. Se han limpiado los archivos temporales.")
        except Exception:
            pass
    except Exception as exc:
        log.exception("Job failed for user %s", user_id)
        if job_id:
            db.finish_job(job_id, "failed", details=str(exc))
        if charged:
            db.refund(user_id, cost)
        try:
            await status_msg.edit_text(f"❌ **No se pudo completar la operación**\n`{str(exc)[:700]}`")
        except Exception:
            pass
    finally:
        shutil.rmtree(work, ignore_errors=True)
        active_tasks.pop(user_id, None)
        pending_files.pop(user_id, None)

@app.on_message(filters.command("addcredits") & filters.private)
async def addcredits_cmd(_, message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("No autorizado.")
    if len(message.command) != 3:
        return await message.reply_text("Uso: `/addcredits USER_ID CANTIDAD`")
    try:
        target, amount = int(message.command[1]), int(message.command[2])
        if amount <= 0 or amount > 100000:
            raise ValueError()
        db.add_credits(target, amount)
        await message.reply_text(f"Se añadieron {amount} créditos a `{target}`.")
    except ValueError:
        await message.reply_text("Parámetros inválidos.")

@app.on_message(filters.command("stats") & filters.private)
async def stats_cmd(_, message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("No autorizado.")
    users, jobs, running = db.user_stats()
    await message.reply_text(f"👥 Usuarios: {users}\n🧰 Trabajos: {jobs}\n⏳ En proceso: {running}")

if __name__ == "__main__":
    db.init_db()
    threading.Thread(target=start_health_server, daemon=True).start()
    log.info("Starting MediaShaper Alternative")
    app.run()
