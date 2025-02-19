from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import requests
import os

# URL and API key for the weather API
URL = "http://api.weatherapi.com/v1"
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

is_paused = False


async def start(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
    else:
        keyboard = [[KeyboardButton("📍 Send current position", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "Hi! Welcome to OutdoorBuddyBot\nUse:\n/weather [Municipality] -> to have the current weather.\n/stop -> to pause the Bot.",
            reply_markup=reply_markup)


async def weather(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return

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


async def stop(update: Update, context: CallbackContext) -> None:
    global is_paused
    is_paused = True
    await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")


async def resume(update: Update, context: CallbackContext) -> None:
    global is_paused
    is_paused = False
    await update.message.reply_text("▶️  Bot resumed.\nYou can now use commands again.")


async def position(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return

    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude

        print(f"📍 Coordinates received: Lat {lat}, Lon {lon}")  # DEBUG

        # API call to get weather info
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


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("resume", resume))  #
    app.add_handler(MessageHandler(filters.LOCATION, position))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()