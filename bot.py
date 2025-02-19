from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import requests
from geopy.geocoders import Nominatim
import asyncio
import os
import logging
import signal

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

URL = "http://api.weatherapi.com/v1"

# Get environment variables
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

if not TOKEN or not API_KEY:
    logger.error("Error: missing environment variables.")
    exit(1)

# Global application variable
application = None


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
    global application
    logger.info("Stopping the bot...")
    await update.message.reply_text("🛑 Bot is stopping...")

    # Schedule the shutdown
    asyncio.create_task(shutdown())


async def shutdown():
    """Shutdown the application"""
    global application
    if application:
        await application.stop()
        await application.shutdown()
        logger.info("Bot has been stopped.")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    asyncio.create_task(shutdown())


def main() -> None:
    """Start the bot."""
    global application

    # Set up signal handlers
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


if __name__ == "__main__":
    main()