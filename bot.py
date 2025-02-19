from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import requests
from geopy.geocoders import Nominatim


URL = "http://api.weatherapi.com/v1"
import os

# Ottieni le variabili d'ambiente
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")

if not TOKEN or not API_KEY:
    print("Errore: variabili d'ambiente mancanti.")
    exit(1)

async def delete_webhook():
    bot = Bot(TOKEN)
    await bot.delete_webhook()

async def start(update: Update, context: CallbackContext) -> None:
    """Show the welcome message and the available commands"""
    keyboard = [[KeyboardButton("📍 Send current position", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text("Hi! Welcome to OutdoorBuddyBot\nUse:\n/weather [Municipality] -> to have the current weather.\n/stop -> to pause the Bot.",
                                    reply_markup=reply_markup)

async def weather(update: Update, context: CallbackContext) -> None:
    """Gets the weather for the specified city"""
    if not context.args:
        await update.message.reply_text("❌ Use:\n`/weather [City name]`", parse_mode="Markdown")
        return

    city = " ".join(context.args)

    # Call the WeatherAPI with the city name
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

        print(f"📍 Coordinates received: Lat {lat}, Lon {lon}")  # DEBUG

        # Call the WeatherAPI with the coordinates
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

async def send_weather(update: Update, city: str) -> None:
    """Ottiene e invia il meteo per la città specificata"""
    params = {"q": city, "appid": API_KEY, "units": "metric", "lang": "en"}
    response = requests.get(URL, params=params)

    if response.status_code == 200:
        data = response.json()
        temp = data["main"]["temp"]
        description = data["weather"][0]["description"]
        await update.message.reply_text(f"📍 {city}\n🌡 Temperature: {temp}°C\n🌤 {description}")
    else:
        await update.message.reply_text("❌ Municipality not found.")

async def stop(update: Update, context: CallbackContext) -> None:
    """Ferma il bot"""
    await update.message.reply_text("🛑 Bot is stopping...")
    await context.application.stop()

async def main():
    try:
        await delete_webhook()  # Rimuovi il webhook se è presente
        app = Application.builder().token(TOKEN).build()

        # Inizializza l'applicazione
        await app.initialize()  # Assicurati che questa riga sia "attesa"

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("weather", weather))
        app.add_handler(CommandHandler("stop", stop))
        app.add_handler(MessageHandler(filters.LOCATION, position))

        print("Bot in esecuzione...")
        await app.run_polling()  # Usa await per eseguire correttamente il polling

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        # Chiudi l'applicazione correttamente
        await app.shutdown()  # Assicurati che questa riga sia "attesa"

# Avvia la funzione main() direttamente, senza usare asyncio.run
if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()  # Usa il loop di eventi già attivo
    loop.run_until_complete(main())
