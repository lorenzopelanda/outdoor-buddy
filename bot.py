from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import requests
import os
import logging
import signal
import sys
import atexit

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

URL = "http://api.weatherapi.com/v1"
LOCK_FILE = "/tmp/telegram_bot.lock"

# Get environment variables
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

if not TOKEN or not API_KEY:
    logger.error("Error: missing environment variables.")
    exit(1)


def check_single_instance():
    """Ensure only one instance of the bot is running"""
    if os.path.exists(LOCK_FILE):
        try:
            # Check if the process is still running
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            try:
                # Check if process with old PID exists
                os.kill(old_pid, 0)
                logger.error(f"Bot is already running with PID {old_pid}")
                sys.exit(1)
            except OSError:
                # Process not found, safe to remove lock file
                logger.info("Removing stale lock file")
                os.remove(LOCK_FILE)
        except (ValueError, IOError) as e:
            logger.error(f"Error reading lock file: {e}")
            os.remove(LOCK_FILE)

    # Create new lock file
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except IOError as e:
        logger.error(f"Could not create lock file: {e}")
        sys.exit(1)


def cleanup():
    """Remove the lock file on exit"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("Lock file removed")
    except Exception as e:
        logger.error(f"Error removing lock file: {e}")


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
    await context.application.stop()


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    cleanup()
    sys.exit(0)


def main() -> None:
    """Start the bot."""
    try:
        # Ensure single instance
        check_single_instance()

        # Register cleanup handlers
        atexit.register(cleanup)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Create the Application
        application = Application.builder().token(TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("weather", weather))
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(MessageHandler(filters.LOCATION, position))

        # Start the bot
        logger.info("Bot starting...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Error in main: {e}")
        cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()