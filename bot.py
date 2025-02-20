from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import requests
import os
import signal
import asyncio
from datetime import datetime, timedelta
import re

# URL and API key for the weather API
URL = "http://api.weatherapi.com/v1"
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

is_paused = False
app = None

def escape_markdownv2(text):
    """Escape special characters for MarkdownV2 format."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def start(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        await update.message.reply_text("🛑 Bot is paused\\. Use /resume to continue\\.", parse_mode="MarkdownV2")
    else:
        keyboard = [[KeyboardButton("📍 Send current position", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "Hi\\! Welcome to OutdoorBuddyBot\nUse:\n/weather \\[Municipality\\] \\-\\> to have the current weather\n/forecast \\[Municipality\\] \\-\\> to see next 4 days forecast"
            "\n/history \\[Municipality\\] \\-\\> to see last 7 days temperatures\n/stop \\-\\> to pause the Bot\\.",
            parse_mode="MarkdownV2",
            reply_markup=reply_markup)

async def forecast(update: Update, context: CallbackContext) -> None:
    """Gets the weather forecast for the next 4 days of the specified city."""
    global is_paused
    if is_paused:
        await update.message.reply_text("🛑 Bot is paused\\. Use /resume to continue\\.", parse_mode="MarkdownV2")
        return

    if not context.args:
        await update.message.reply_text("❌ Use:\n`/forecast \\[City name\\]`", parse_mode="MarkdownV2")
        return

    city = " ".join(context.args)
    params = {"key": API_KEY, "q": city, "days": 5, "lang": "en"}
    response = requests.get(f"{URL}/forecast.json", params=params)

    if response.status_code == 200:
        data = response.json()
        city_name = escape_markdownv2(data["location"]["name"])
        forecast_days = data["forecast"]["forecastday"]

        message = f"📍 {city_name}\n🗓 Next days forecast:\n\n"
        for day in forecast_days[1:]:  # Skip today
            date = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
            max_temp = str(day["day"]["maxtemp_c"]).replace(".", "\\.")
            min_temp = str(day["day"]["mintemp_c"]).replace(".", "\\.")
            condition = escape_markdownv2(day["day"]["condition"]["text"])
            message += f"📅 *{date}*\n"
            message += f"🌡 Temperature: {min_temp}°C \\- {max_temp}°C\n"
            message += f"🌤 {condition}\n\n"

        await update.message.reply_text(message, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text("❌ Municipality not found\\.", parse_mode="MarkdownV2")

async def weather(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        await update.message.reply_text("🛑 Bot is paused\\. Use /resume to continue\\.", parse_mode="MarkdownV2")
        return

    if not context.args:
        await update.message.reply_text("❌ Use:\n`/weather \\[City name\\]`", parse_mode="MarkdownV2")
        return

    city = " ".join(context.args)
    params = {"key": API_KEY, "q": city, "lang": "en"}
    response = requests.get(f"{URL}/current.json", params=params)

    if response.status_code == 200:
        data = response.json()
        city_name = escape_markdownv2(data["location"]["name"])
        temp = data["current"]["temp_c"]
        description = escape_markdownv2(data["current"]["condition"]["text"])
        await update.message.reply_text(
            f"📍 {city_name}\n🌡 Temperature: {temp}°C\n🌤 {description}".replace(".", "\\."),
            parse_mode="MarkdownV2"
        )
    else:
        await update.message.reply_text("❌ Municipality not found\\.", parse_mode="MarkdownV2")

async def stop(update: Update, context: CallbackContext) -> None:
    global is_paused
    is_paused = True
    await update.message.reply_text("🛑 Bot is paused\\. Use /resume to continue\\.", parse_mode="MarkdownV2")

async def resume(update: Update, context: CallbackContext) -> None:
    global is_paused
    is_paused = False
    await update.message.reply_text("▶️ Bot resumed\\.\nYou can now use commands again\\.", parse_mode="MarkdownV2")

async def position(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        await update.message.reply_text("🛑 Bot is paused\\. Use /resume to continue\\.", parse_mode="MarkdownV2")
        return

    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude

        print(f"📍 Coordinates received: Lat {lat}, Lon {lon}")  # DEBUG

        params = {"key": API_KEY, "q": f"{lat},{lon}", "lang": "en"}
        response = requests.get(f"{URL}/current.json", params=params)

        if response.status_code == 200:
            data = response.json()
            city = escape_markdownv2(data["location"]["name"])
            temp = data["current"]["temp_c"]
            description = escape_markdownv2(data["current"]["condition"]["text"])
            await update.message.reply_text(
                f"📍 {city}\n🌡 Temperature: {temp}°C\n🌤 {description}".replace(".", "\\."),
                parse_mode="MarkdownV2"
            )
        else:
            await update.message.reply_text("❌ Error fetching the weather info\\.", parse_mode="MarkdownV2")

async def history(update: Update, context: CallbackContext) -> None:
    """Gets the daily average temperature for the last 7 days of the specified city."""
    if not context.args:
        await update.message.reply_text("❌ Use:\n`/history \\[City name\\]`", parse_mode="MarkdownV2")
        return

    city = " ".join(context.args)
    temperatures = []

    for i in range(1, 7):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        params = {"key": API_KEY, "q": city, "dt": date, "lang": "en"}
        response = requests.get(f"{URL}/history.json", params=params)

        if response.status_code == 200:
            data = response.json()
            temp = data["forecast"]["forecastday"][0]["day"]["avgtemp_c"]
            temperatures.append((date, temp))
        else:
            await update.message.reply_text(f"❌ Error fetching data for {date}\\.", parse_mode="MarkdownV2")
            return

    temperatures.sort(reverse=True, key=lambda x: x[0])

    city = escape_markdownv2(city)
    message = f"📍 {city}\n📅 Average daily temperatures \\(last 7 days\\):\n\n"
    for date, temp in temperatures:
        message += f"  • {date.replace('-', '\\-')}: {temp}°C\n".replace(".", "\\.")

    await update.message.reply_text(message, parse_mode="MarkdownV2")

def main():
    global app
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("forecast", forecast))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(MessageHandler(filters.LOCATION, position))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()