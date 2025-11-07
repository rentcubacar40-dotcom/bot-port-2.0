# main.py
import asyncio
import socket
import json
import os
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = "8261018231:AAHNSNJffiUccU_IPc4J8cDkWYLcMTRn8UQ"
ADMIN_ID = 7363341763
ADMIN_USERNAME = "@Eliel_21"
DEFAULT_PORTS = [21, 22, 23, 25, 53, 80, 443, 3306, 8080]

PER_PORT_TIMEOUT = 0.6
MAX_CONCURRENCY = 50
PROGRESS_UPDATE_INTERVAL = 0.25
DELAY_BETWEEN_PORTS = 5.0
CHUNK_SIZE = 40

# ---------------- EMOJIS ----------------
PROGRESS_BLOCK = "🟩"  # bloque lleno
PROGRESS_EMPTY = "⬜"  # bloque vacío

# ---------------- ARCHIVOS ----------------
ALLOWED_FILE = "allowed.json"
ADMINS_FILE = "admins.json"

def load_json_list(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

def save_json_list(path, lst):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(lst, f)
    except Exception:
        pass

ALLOWED_USERS = load_json_list(ALLOWED_FILE)
ADMINS = load_json_list(ADMINS_FILE)

# ---------------- PERMISOS ----------------
def is_admin_principal(user):
    try:
        return int(user.id) == int(ADMIN_ID)
    except Exception:
        return False

def is_admin_user(user):
    if is_admin_principal(user):
        return True
    if getattr(user, "username", None) and ("@" + user.username) in ADMINS:
        return True
    if str(getattr(user, "id", "")) in ADMINS:
        return True
    return False

def user_allowed(user):
    if is_admin_principal(user): return True
    if is_admin_user(user): return True
    if getattr(user, "username", None) and ("@" + user.username) in ALLOWED_USERS:
        return True
    if str(getattr(user, "id", "")) in ALLOWED_USERS:
        return True
    return False

# ---------------- UTILIDADES ----------------
def is_valid_host(host: str) -> bool:
    ip_pattern = r"^(?:\d{1,3}\.){3}\d{1,3}$"
    domain_pattern = r"^(?=.{1,253}$)(?:[a-zA-Z0-9-]{1,63}\.)+[a-zA-Z]{2,63}$"
    return bool(re.match(ip_pattern, host)) or bool(re.match(domain_pattern, host))

async def try_connect(host: str, port: int, timeout: float) -> bool:
    try:
        def connect():
            with socket.create_connection((host, port), timeout):
                return True
        return await asyncio.to_thread(connect)
    except Exception:
        return False

def emoji_progress(percent: float) -> str:
    blocks = 10
    filled = int(percent * blocks)
    if filled < 0: filled = 0
    if filled > blocks: filled = blocks
    return PROGRESS_BLOCK * filled + PROGRESS_EMPTY * (blocks - filled)

async def chunked_send(reply_func, text: str, chunk: int = CHUNK_SIZE):
    lines = text.splitlines()
    if len(lines) <= chunk:
        await reply_func(text)
        return
    for i in range(0, len(lines), chunk):
        part = "\n".join(lines[i:i+chunk])
        await reply_func(part)
        await asyncio.sleep(0.20)

# ---------------- ESTADO GLOBAL ----------------
escaneo_en_progreso = False
cola_espera = []
current_scanner_id = None
current_scanner_name = ""
current_status_message = None
cancel_event = None

# ---------------- HELPERS COLA ----------------
async def update_queue_positions():
    global cola_espera
    nueva_cola = []
    for idx, entry in enumerate(cola_espera, start=1):
        user_id, username, update_obj, context_obj, pos_msg = entry
        try:
            await pos_msg.edit_text(
                f"⏳ Estás en la posición {idx} de la cola.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Salir de la cola", callback_data=f"salir_cola_{user_id}")]
                ])
            )
            nueva_cola.append(entry)
        except Exception:
            pass
    cola_espera = nueva_cola

async def pop_next_in_queue_and_start():
    global escaneo_en_progreso
    if not cola_espera:
        return False
    next_entry = cola_espera.pop(0)
    try:
        await next_entry[4].edit_text(f"▶️ Es tu turno @{next_entry[1]} — iniciando escaneo...")
    except Exception:
        pass
    try:
        await escanear(next_entry[2], next_entry[3])
    except Exception:
        escaneo_en_progreso = False
        await asyncio.sleep(0.1)
        return await pop_next_in_queue_and_start()
    return True

# ---------------- COMANDOS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "• `/escanear <host>` - Escanea puertos principales\n"
        "• `/escanear <host> <puertos separados por comas>` - Escanea puertos específicos\n"
        "• `/puerto <host> <n>` - Prueba un puerto específico\n"
        "• `/permitir <@usuario/id>` - Permite usuario (admins)\n"
        "• `/revocar <@usuario/id>` - Revoca usuario (admins)\n"
        "• `/agregar_admin <@usuario/id>` - Agrega admin (propietario)\n"
        "• `/quitar_admin <@usuario/id>` - Quita admin (propietario)\n"
        "• `/lista` - Muestra propietario/admins/usuarios/cola\n"
        "• `/guia` - Muestra guía detallada",
        parse_mode="Markdown"
    )

async def guia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "📖 *Guía del Bot Escáner de Puertos*\n\n"
        "*1) Comandos principales*\n"
        "• `/escanear <host>` → Escanea puertos principales: `21,22,23,25,53,80,443,3306,8080`\n"
        "• `/escanear <host> <puertos separados por comas>` → Escanea puertos específicos\n"
        "• `/puerto <host> <n>` → Prueba un puerto específico\n\n"
        "*2) Permisos*\n"
        "• `/permitir <@usuario/id>` - Solo administradores\n"
        "• `/revocar <@usuario/id>` - Revoca permisos\n"
        "• `/agregar_admin` y `/quitar_admin` - Solo propietario\n\n"
        "*3) Escaneo*\n"
        f"• Delay de {DELAY_BETWEEN_PORTS} s por puerto\n"
        "• Barra de progreso 🟩/⬜\n"
        "• Cancelable con ❌ (usuario o admin)\n\n"
        "*4) Cola*\n"
        "• Mensajes muestran posición en tiempo real\n"
        "• Se puede salir con el botón ❌ Salir de la cola\n\n"
        "*5) Consejos*\n"
        "• Usa puertos personalizados solo si sabes lo que haces\n"
        "• Respeta políticas de hosts escaneados\n"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

# ---------------- ADMIN ----------------
async def agregar_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_principal(user):
        await update.message.reply_text("❌ Solo el propietario puede agregar administradores.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /agregar_admin @usuario")
        return
    target = context.args[0].strip()
    if target in ADMINS:
        await update.message.reply_text("ℹ️ Ese usuario ya es administrador.")
        return
    ADMINS.append(target)
    save_json_list(ADMINS_FILE, ADMINS)
    await update.message.reply_text(f"✅ {target} ahora es administrador.")

async def quitar_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_principal(user):
        await update.message.reply_text("❌ Solo el propietario puede quitar administradores.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /quitar_admin @usuario")
        return
    target = context.args[0].strip()
    if target not in ADMINS:
        await update.message.reply_text("ℹ️ Ese usuario no es administrador.")
        return
    ADMINS.remove(target)
    save_json_list(ADMINS_FILE, ADMINS)
    await update.message.reply_text(f"✅ {target} ya no es administrador.")

# ---------------- PERMITIR / REVOCAR ----------------
async def permitir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_user(user):
        await update.message.reply_text("❌ Solo administradores pueden permitir usuarios.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /permitir @usuario")
        return
    target = context.args[0].strip()
    if target in ALLOWED_USERS:
        await update.message.reply_text("ℹ️ Ese usuario ya tenía permiso.")
        return
    ALLOWED_USERS.append(target)
    save_json_list(ALLOWED_FILE, ALLOWED_USERS)
    await update.message.reply_text(f"✅ {target} permitido.")

async def revocar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_user(user):
        await update.message.reply_text("❌ Solo administradores pueden revocar permisos.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /revocar @usuario")
        return
    target = context.args[0].strip()
    if target not in ALLOWED_USERS:
        await update.message.reply_text("ℹ️ Ese usuario no estaba permitido.")
        return
    ALLOWED_USERS.remove(target)
    save_json_list(ALLOWED_FILE, ALLOWED_USERS)
    await update.message.reply_text(f"✅ {target} revocado.")

# ---------------- LISTA ----------------
async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = []
    owner_display = ADMIN_USERNAME if ADMIN_USERNAME else str(ADMIN_ID)
    lines.append(f"{owner_display} 👑 Propietario")
    if ADMINS:
        lines.append("\n🛡 Administradores:")
        for a in ADMINS:
            lines.append(f"🛡 {a}")
    else:
        lines.append("\n🛡 Administradores: Ninguno")
    usuarios_solo = [u for u in ALLOWED_USERS if u not in ADMINS]
    if usuarios_solo:
        lines.append("\n👤 Usuarios permitidos:")
        for u in usuarios_solo:
            lines.append(f"👤 {u}")
    else:
        lines.append("\n👤 Usuarios permitidos: Ninguno")
    if cola_espera:
        lines.append("\n⏳ Cola actual:")
        for idx, u in enumerate(cola_espera, start=1):
            lines.append(f"{idx}. @{u[1]}")
    await update.message.reply_text("\n".join(lines))

# ---------------- ESCANEAR ----------------
async def escanear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global escaneo_en_progreso, cola_espera, current_scanner_id, current_scanner_name, current_status_message, cancel_event

    user = update.effective_user
    username = user.username or user.first_name

    if not user_allowed(user):
        await update.message.reply_text("❌ No tienes permiso para usar este comando.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("❌ Uso correcto: /escanear <host> [puertos separados por comas]")
        return

    host = context.args[0].strip()
    if not is_valid_host(host):
        await update.message.reply_text("❌ Host inválido.")
        return

    ports_to_scan = DEFAULT_PORTS.copy()
    if len(context.args) > 1:
        try:
            ports_str = context.args[1]
            ports_to_scan = [int(p.strip()) for p in ports_str.split(",") if 1 <= int(p.strip()) <= 65535]
        except Exception:
            await update.message.reply_text("❌ Puertos inválidos, deben ser números entre 1-65535 separados por comas.")
            return

    if escaneo_en_progreso:
        pos_msg = await update.message.reply_text(
            f"⏳ Estás en la cola posición {len(cola_espera)+1}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Salir de la cola", callback_data=f"salir_cola_{user.id}")]])
        )
        cola_espera.append((user.id, username, update, context, pos_msg))
        await update_queue_positions()
        return

    # Inicia escaneo
    escaneo_en_progreso = True
    current_scanner_id = user.id
    current_scanner_name = username
    cancel_event = asyncio.Event()

    current_status_message = await update.message.reply_text(
        f"🔎 Escaneando {host}...\nUsuario: @{username}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancel_scan")]])
    )

    scanned = 0
    open_p = []
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def worker(port):
        nonlocal scanned
        async with sem:
            if cancel_event.is_set():
                return
            ok = await try_connect(host, port, PER_PORT_TIMEOUT)
            scanned += 1
            open_p.append(f"{port} {'✅' if ok else '❌'}")
            await asyncio.sleep(DELAY_BETWEEN_PORTS)

    async def updater():
        total = len(ports_to_scan)
        while scanned < total and not cancel_event.is_set():
            percent = scanned / total
            bar = emoji_progress(percent)
            try:
                await current_status_message.edit_text(
                    f"🔎 Escaneando {host}\n{int(percent*100)}%\n{bar}\nUsuario: @{username}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancel_scan")]])
                )
            except Exception:
                pass
            await asyncio.sleep(PROGRESS_UPDATE_INTERVAL)

    tasks = [asyncio.create_task(worker(p)) for p in ports_to_scan]
    updater_task = asyncio.create_task(updater())

    await asyncio.gather(*tasks, return_exceptions=True)
    updater_task.cancel()

    if cancel_event.is_set():
        try:
            await current_status_message.edit_text("🛑 Escaneo cancelado.")
        except Exception:
            pass
        escaneo_en_progreso = False
        cancel_event = None
        await pop_next_in_queue_and_start()
        return

    try:
        await current_status_message.delete()
    except Exception:
        pass

    lines = [f"📤 Resultados para {host}\nUsuario: @{username}\nPuertos:"]
    lines.extend(open_p)

    await chunked_send(update.message.reply_text, "\n".join(lines))

    escaneo_en_progreso = False
    cancel_event = None
    await pop_next_in_queue_and_start()

# ---------------- PUERTO ----------------
async def puerto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user_allowed(user):
        await update.message.reply_text("❌ No tienes permiso para usar este comando.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /puerto <host> <n>")
        return
    host = context.args[0]
    port = int(context.args[1])
    if not (1 <= port <= 65535):
        await update.message.reply_text("❌ Puerto inválido.")
        return
    msg = await update.message.reply_text("🔎 Probando puerto...")
    ok = await try_connect(host, port, PER_PORT_TIMEOUT)
    await msg.edit_text(f"Puerto {port} en {host}: {'✅ abierto' if ok else '❌ cerrado'}")

# ---------------- CALLBACK ----------------
async def cancel_scan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cancel_event
    q = update.callback_query
    await q.answer()
    user = q.from_user
    if not (is_admin_user(user) or user.id == current_scanner_id):
        await q.answer("Solo el usuario o un administrador puede cancelar.", show_alert=True)
        return
    if cancel_event:
        cancel_event.set()
    try:
        await q.edit_message_text("🛑 Escaneo cancelado.")
    except Exception:
        pass

async def salir_cola_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cola_espera
    q = update.callback_query
    await q.answer()
    user = q.from_user
    user_id_in_cb = int(q.data.replace("salir_cola_", ""))
    if user.id != user_id_in_cb:
        await q.answer("Solo puedes salir tú de la cola.", show_alert=True)
        return
    # Elimina de la cola
    cola_espera = [c for c in cola_espera if c[0] != user.id]
    try:
        await q.edit_message_text("✅ Has salido de la cola.")
    except Exception:
        pass
    await update_queue_positions()

# ---------------- RUN ----------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("guia", guia))
app.add_handler(CommandHandler("lista", lista))
app.add_handler(CommandHandler("permitir", permitir))
app.add_handler(CommandHandler("revocar", revocar))
app.add_handler(CommandHandler("agregar_admin", agregar_admin))
app.add_handler(CommandHandler("quitar_admin", quitar_admin))
app.add_handler(CommandHandler("escanear", escanear))
app.add_handler(CommandHandler("puerto", puerto))
app.add_handler(CallbackQueryHandler(cancel_scan_callback, pattern="cancel_scan"))
app.add_handler(CallbackQueryHandler(salir_cola_callback, pattern="salir_cola_"))

app.run_polling()
