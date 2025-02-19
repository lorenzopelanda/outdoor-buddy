from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import requests
from geopy.geocoders import Nominatim
import asyncio
import os
import logging

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

URL = "http://api.weatherapi.com/v1"

# Get environment variables
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

if not TOKEN or not API_KEY:
    print("Error: missing environment variables.")
    exit(1)


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
    response = requests.get(f"{URL}/current.json", params=params)

    if response.status_code == 200:
        data = response.json()
        city_name = data["location"]["name"]
        temp = data["current"]["temp_c"]
        description = data["current"]["condition"]["text"]
        await update.message.reply_text(f"📍 {city_name}\n🌡 Temperature: {temp}°C\n🌤 {description}")
    else:
        await update.message.reply_text("❌ Municipality not found.")


async def position(update: Update, context: CallbackContext) -> None:
    """Gets the weather for the current position"""
    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude

        logging.info(f"📍 Coordinates received: Lat {lat}, Lon {lon}")

        params = {"key": API_KEY, "q": f"{lat},{lon}", "lang": "en"}
        response = requests.get(f"{URL}/current.json", params=params)

        if response.status_code == 200:
            data = response.json()
            city = data["location"]["name"]
            temp = data["current"]["temp_c"]
            description = data["current"]["condition"]["text"]
            await update.message.reply_text(f"📍 {city}\n🌡 Temperature: {temp}°C\n🌤 {description}")
        else:
            await update.message.reply_text("❌ Error fetching the weather info.")


async def stop(update: Update, context: CallbackContext) -> None:
    """Stops the bot"""
    await update.message.reply_text("🛑 Bot is stopping...")
    await context.application.stop()


def main() -> None:
    """Start the bot."""
    # Create the Application
    app = Application.builder().token(TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.LOCATION, position))

    # Start the bot
    print("Bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()