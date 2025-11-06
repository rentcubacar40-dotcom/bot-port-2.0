import os
import socket
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Variables de entorno
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Hola {user.first_name}, bienvenido al bot!\nUsa /scan <host> para escanear puertos"
    )

# Comando /scan
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Uso correcto: /scan <host>")
        return

    host = context.args[0]
    ports_to_check = [21, 22, 23, 25, 53, 80, 443, 3306, 8080]  # puedes ampliar
    result = f"Escaneo de {host}:\n"

    for port in ports_to_check:
        try:
            with socket.create_connection((host, port), timeout=1):
                result += f"Puerto {port}: ✅ Abierto\n"
        except:
            result += f"Puerto {port}: ❌ Cerrado\n"

    await update.message.reply_text(result)

# Crear aplicación
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("scan", scan))

# Ejecutar con polling
app.run_polling()
