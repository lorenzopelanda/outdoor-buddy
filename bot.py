from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.error import Conflict, NetworkError, TelegramError
import requests
import os
import logging
import signal
import sys
import asyncio
import time
import atexit
import psutil

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

URL = "http://api.weatherapi.com/v1"
PID_FILE = "/tmp/weather_bot.pid"

# Get environment variables
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

if not TOKEN or not API_KEY:
    logger.error("Error: missing environment variables.")
    exit(1)


def cleanup_pid():
    """Remove PID file if it exists"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info("PID file removed")
    except Exception as e:
        logger.error(f"Error removing PID file: {e}")


def kill_existing_process():
    """Kill any existing bot process"""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            try:
                process = psutil.Process(old_pid)
                process.terminate()
                process.wait(timeout=5)  # Wait up to 5 seconds for the process to terminate
                logger.info(f"Terminated old process with PID {old_pid}")
            except psutil.NoSuchProcess:
                logger.info(f"No process found with PID {old_pid}")
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
            finally:
                cleanup_pid()
    except Exception as e:
        logger.error(f"Error reading PID file: {e}")
        cleanup_pid()


async def error_handler(update: object, context: CallbackContext) -> None:
    """Handle errors caused by updates."""
    logger.error(f"Error caused by update {update}: {context.error}")

    if isinstance(context.error, Conflict):
        logger.info("Conflict detected, attempting to resolve...")
        kill_existing_process()
        await asyncio.sleep(2)
    elif isinstance(context.error, NetworkError):
        logger.info("Network error detected, waiting before retry...")
        await asyncio.sleep(5)


async def start(update: Update, context: CallbackContext) -> None:
    """Show the welcome message and the available commands"""
    keyboard = [[KeyboardButton("📍 Send current position", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "Hi! Welcome to OutdoorBuddyBot\nUse:\n/weather [Municipality] -> to have the current weather.\n/stop -> to pause the Bot.",
        reply_markup=reply_markup
    )


async def weather(update: Update, context: CallbackContext) -> None:
    """Gets the weather for the specified city"""
    if not context.args:
        await update.message.reply_text("❌ Use:\n`/weather [City name]`", parse_mode="Markdown")
        return

    city = " ".join(context.args)
    params = {"key": API_KEY, "q": city, "lang": "en"}

    try:
        response = requests.get(f"{URL}/current.json", params=params)
        response.raise_for_status()

        data = response.json()
        city_name = data["location"]["name"]
        temp = data["current"]["temp_c"]
        description = data["current"]["condition"]["text"]
        await update.message.reply_text(f"📍 {city_name}\n🌡 Temperature: {temp}°C\n🌤 {description}")
    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
        await update.message.reply_text("❌ Municipality not found or error fetching data.")


async def position(update: Update, context: CallbackContext) -> None:
    """Gets the weather for the current position"""
    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude

        logger.info(f"📍 Coordinates received: Lat {lat}, Lon {lon}")

        params = {"key": API_KEY, "q": f"{lat},{lon}", "lang": "en"}
        try:
            response = requests.get(f"{URL}/current.json", params=params)
            response.raise_for_status()

            data = response.json()
            city = data["location"]["name"]
            temp = data["current"]["temp_c"]
            description = data["current"]["condition"]["text"]
            await update.message.reply_text(f"📍 {city}\n🌡 Temperature: {temp}°C\n🌤 {description}")
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            await update.message.reply_text("❌ Error fetching the weather info.")


async def stop(update: Update, context: CallbackContext) -> None:
    """Stops the bot"""
    logger.info("Stopping the bot...")
    await update.message.reply_text("🛑 Bot is stopping...")
    cleanup_pid()
    await context.application.stop()
    sys.exit(0)


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    cleanup_pid()
    sys.exit(0)


async def delete_webhook_and_wait():
    """Delete webhook and wait to ensure it's properly removed"""
    bot = Bot(TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    await bot.close()


async def main() -> None:
    """Start the bot."""
    try:
        # Kill any existing process and clean up
        kill_existing_process()

        # Save current PID
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))

        # Register cleanup handlers
        atexit.register(cleanup_pid)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Delete any existing webhook and wait
        await delete_webhook_and_wait()

        # Create the Application
        application = Application.builder().token(TOKEN).build()

        # Add error handler
        application.add_error_handler(error_handler)

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("weather", weather))
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(MessageHandler(filters.LOCATION, position))

        # Start the bot
        logger.info("Bot starting...")
        await application.initialize()
        await application.start()
        await application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )

    except Exception as e:
        logger.error(f"Error in main: {e}")
        cleanup_pid()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        cleanup_pid()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        cleanup_pid()