from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from processing import utils
import requests
import os
import signal
import asyncio
from datetime import datetime, timedelta
import re
import openai
from dotenv import load_dotenv
import json

# URL and API key for the weather API
URL = "http://api.weatherapi.com/v1"
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

load_dotenv()
openai.api_key = os.getenv("MISTRAL_API_KEY")
is_paused = False
app = None

def start(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
    else:
        keyboard = [[KeyboardButton("📍 Send current position", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        update.message.reply_text(
            "Hi! Welcome to OutdoorBuddyBot\nUse:\n/weather [Municipality] -> to have the current weather\n/forecast [Municipality] -> to see next 4 days forecast"
            "\n/history [Municipality] -> to see last 7 days temperatures\n/stop -> to pause the Bot.",
            reply_markup=reply_markup)

def forecast(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return

    if not context.args:
        update.message.reply_text("❌ Use:\n/forecast [City name]")
        return

    city = " ".join(context.args)
    params = {"key": API_KEY, "q": city, "days": 5, "lang": "en"}
    response = requests.get(f"{URL}/forecast.json", params=params)

    if response.status_code == 200:
        data = response.json()
        city_name = data["location"]["name"]
        forecast_days = data["forecast"]["forecastday"]

        message = f"📍 {city_name}\n🗓 Next days forecast:\n\n"
        for day in forecast_days[1:]:  # Skip today
            date = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
            max_temp = day["day"]["maxtemp_c"]
            min_temp = day["day"]["mintemp_c"]
            condition = day["day"]["condition"]["text"]
            message += f"📅 {date}\n"
            message += f"🌡 Temperature: {min_temp}°C - {max_temp}°C\n"
            message += f"🌤 {condition}\n\n"

        update.message.reply_text(message)
    else:
        update.message.reply_text("❌ Municipality not found.")

def weather(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return

    if not context.args:
        update.message.reply_text("❌ Use:\n/weather [City name]")
        return

    city = " ".join(context.args)
    params = {"key": API_KEY, "q": city, "lang": "en"}
    response = requests.get(f"{URL}/current.json", params=params)

    if response.status_code == 200:
        data = response.json()
        city_name = data["location"]["name"]
        temp = data["current"]["temp_c"]
        description = data["current"]["condition"]["text"]
        update.message.reply_text(
            f"📍 {city_name}\n🌡 Temperature: {temp}°C\n🌤 {description}"
        )
    else:
        update.message.reply_text("❌ Municipality not found.")

def stop(update: Update, context: CallbackContext) -> None:
    global is_paused
    is_paused = True
    update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")

def resume(update: Update, context: CallbackContext) -> None:
    global is_paused
    is_paused = False
    update.message.reply_text("▶️ Bot resumed. You can now use commands again.")

def position(update: Update, context: CallbackContext) -> None:
    global is_paused
    if is_paused:
        update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return

    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude

        print(f"📍 Coordinates received: Lat {lat}, Lon {lon}")  # DEBUG

        params = {"key": API_KEY, "q": f"{lat},{lon}", "lang": "en"}
        response = requests.get(f"{URL}/current.json", params=params)

        if response.status_code == 200:
            data = response.json()
            city = data["location"]["name"]
            temp = data["current"]["temp_c"]
            description = data["current"]["condition"]["text"]
            update.message.reply_text(
                f"📍 {city}\n🌡 Temperature: {temp}°C\n🌤 {description}"
            )
        else:
            update.message.reply_text("❌ Error fetching the weather info.")

def parse_input_with_ai(message: str) -> dict:
    """Usa AI per estrarre i parametri del percorso."""
    prompt = (
        "Estrarre i parametri principali e opzionali per pianificare un percorso ciclistico o di trekking dal seguente testo. "
        "Restituire un JSON con address, distance, level, duration, terrain (obbligatori) e ascent (opzionale). "
        "Ignorare dettagli non rilevanti.\n"
        f"Testo: {message}\nOutput:"
    )

    response = openai.ChatCompletion.create(
        model="mistral-7b-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return json.loads(response["choices"][0]["message"]["content"])


def route(update: Update, context: CallbackContext) -> None:
    """Gestisce il comando /route del bot Telegram."""
    global is_paused
    if is_paused:
        update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return

    try:
        user_input = update.message.text[len("/route "):]
        params = parse_input_with_ai(user_input)

        # Parametri obbligatori
        address = params["address"]
        distance = float(params["distance"])
        level = params["level"].lower()
        duration = float(params["duration"])
        terrain = params["terrain"].lower()

        if distance <= 0:
            update.message.reply_text("❌ Distance must be greater than 0.")
            return

        if duration <= 0:
            update.message.reply_text("❌ Duration must be greater than 0.")
            return

        if not re.match(r"principiante|intermedio|avanzato", level):
            update.message.reply_text("❌ Level must be 'principiante', 'intermedio', or 'avanzato'.")
            return

        if not re.match(r"sterrato|asfalto|misto", terrain):
            update.message.reply_text("❌ Terrain must be 'sterrato', 'asfalto', or 'misto'.")
            return

        # Parametro opzionale
        ascent = params.get("ascent", None)

        # Passa tutto alla funzione di pianificazione
        utils.plan_circular_route(address, distance, level, duration=duration, terrain=terrain, ascent=ascent)
        update.message.reply_text("✅ Route successfully created. Check your email for the GPX file.")

    except Exception as e:
        update.message.reply_text(f"❌ Error: {e}")

def main():
    global app
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("forecast", forecast))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("route",route))
    app.add_handler(MessageHandler(filters.LOCATION, position))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()