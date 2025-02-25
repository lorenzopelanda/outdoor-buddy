from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, \
    ConversationHandler, PersistenceInput, PicklePersistence
from processing import utils
import requests
import os
import signal
import asyncio
import logging
from datetime import datetime, timedelta
import re
import openai
from dotenv import load_dotenv
import json
import sys

# Configurazione del logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# URL e chiavi API
URL = "http://api.weatherapi.com/v1"
load_dotenv()
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")
openai.api_key = os.getenv("MISTRAL_API_KEY")

# Stato della conversazione
AWAITING_COMMAND = 0
is_paused = False

# Configurazione della persistenza
persistence = PicklePersistence(
    filepath='bot_data.pickle',
    store_data=PersistenceInput(
        bot_data=True,
        chat_data=True,
        user_data=True,
        callback_data=True,
    )
)


async def start(update: Update, context: CallbackContext) -> int:
    global is_paused

    # Verifica se il bot è in pausa
    if context.bot_data.get('is_paused', False):
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return AWAITING_COMMAND

    keyboard = [[KeyboardButton("📍 Send current position", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "Hi! Welcome to OutdoorBuddyBot\nUse:\n/weather [Municipality] -> to have the current weather\n/forecast [Municipality] -> to see next 4 days forecast"
        "\n/history [Municipality] -> to see last 7 days temperatures\n/stop -> to pause the Bot.",
        reply_markup=reply_markup)

    return AWAITING_COMMAND


async def forecast(update: Update, context: CallbackContext) -> int:
    if context.bot_data.get('is_paused', False):
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return AWAITING_COMMAND

    if not context.args:
        await update.message.reply_text("❌ Use:\n/forecast [City name]")
        return AWAITING_COMMAND

    try:
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

            await update.message.reply_text(message)
        else:
            await update.message.reply_text("❌ Municipality not found.")
    except Exception as e:
        logger.error(f"Error in forecast command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching the forecast.")

    return AWAITING_COMMAND


async def weather(update: Update, context: CallbackContext) -> int:
    if context.bot_data.get('is_paused', False):
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return AWAITING_COMMAND

    if not context.args:
        await update.message.reply_text("❌ Use:\n/weather [City name]")
        return AWAITING_COMMAND

    try:
        city = " ".join(context.args)
        params = {"key": API_KEY, "q": city, "lang": "en"}
        response = requests.get(f"{URL}/current.json", params=params)

        if response.status_code == 200:
            data = response.json()
            city_name = data["location"]["name"]
            temp = data["current"]["temp_c"]
            description = data["current"]["condition"]["text"]
            await update.message.reply_text(
                f"📍 {city_name}\n🌡 Temperature: {temp}°C\n🌤 {description}"
            )
        else:
            await update.message.reply_text("❌ Municipality not found.")
    except Exception as e:
        logger.error(f"Error in weather command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching the weather.")

    return AWAITING_COMMAND


async def stop(update: Update, context: CallbackContext) -> int:
    # Salva lo stato di pausa nei dati persistenti
    context.bot_data['is_paused'] = True
    await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
    return AWAITING_COMMAND


async def resume(update: Update, context: CallbackContext) -> int:
    # Ripristina lo stato attivo nei dati persistenti
    context.bot_data['is_paused'] = False
    await update.message.reply_text("▶️ Bot resumed. You can now use commands again.")
    return AWAITING_COMMAND


async def position(update: Update, context: CallbackContext) -> int:
    if context.bot_data.get('is_paused', False):
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return AWAITING_COMMAND

    try:
        if update.message.location:
            lat = update.message.location.latitude
            lon = update.message.location.longitude

            logger.info(f"📍 Coordinates received: Lat {lat}, Lon {lon}")

            params = {"key": API_KEY, "q": f"{lat},{lon}", "lang": "en"}
            response = requests.get(f"{URL}/current.json", params=params)

            if response.status_code == 200:
                data = response.json()
                city = data["location"]["name"]
                temp = data["current"]["temp_c"]
                description = data["current"]["condition"]["text"]
                await update.message.reply_text(
                    f"📍 {city}\n🌡 Temperature: {temp}°C\n🌤 {description}"
                )
            else:
                await update.message.reply_text("❌ Error fetching the weather info.")
    except Exception as e:
        logger.error(f"Error in position handler: {e}")
        await update.message.reply_text("❌ An error occurred while processing your location.")

    return AWAITING_COMMAND


async def parse_input_with_ai(message: str) -> dict:
    try:
        prompt = (
            "Extract principal parameters and optional ones to plan a cycling route from the following text. "
            "Return a JSON with address, distance, level, duration, terrain (mandatory) and ascent (optional). "
            "Ignore irrelevant details.\n"
            f"Text: {message}\nOutput:"
        )

        response = openai.ChatCompletion.create(
            model="mistral-7b-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )

        return json.loads(response["choices"][0]["message"]["content"])
    except Exception as e:
        logger.error(f"Error in AI parsing: {e}")
        raise


async def route(update: Update, context: CallbackContext) -> int:
    if context.bot_data.get('is_paused', False):
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return AWAITING_COMMAND

    try:
        if len(update.message.text) <= len("/route "):
            await update.message.reply_text("❌ Please provide route details after the /route command.")
            return AWAITING_COMMAND

        user_input = update.message.text[len("/route "):]
        params = await parse_input_with_ai(user_input)

        address = params["address"]
        distance = float(params["distance"])
        level = params["level"].lower()
        duration = float(params["duration"])

        if distance <= 0:
            await update.message.reply_text("❌ Distance must be greater than 0.")
            return AWAITING_COMMAND

        if duration <= 0:
            await update.message.reply_text("❌ Duration must be greater than 0.")
            return AWAITING_COMMAND

        if not re.match(r"beginner|intermediate|advanced", level):
            await update.message.reply_text("❌ Level must be 'beginner', 'intermediate', or 'advanced'.")
            return AWAITING_COMMAND

        ascent = params.get("ascent", None)

        # Passa tutto alla funzione di pianificazione
        utils.plan_circular_route(address, distance, level, duration=duration, ascent=ascent)
        await update.message.reply_text("✅ Route successfully created. Check your email for the GPX file.")
    except Exception as e:
        logger.error(f"Error in route command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

    return AWAITING_COMMAND


async def error_handler(update: Update, context: CallbackContext) -> None:
    """Gestisce gli errori incontrati dal dispatcher."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ An error occurred while processing your request. Please try again later.")


def main() -> None:
    try:
        # Inizializza l'applicazione con persistenza
        application = ApplicationBuilder().token(TOKEN).persistence(persistence).build()

        # Gestione degli stati della conversazione
        states = {
            AWAITING_COMMAND: [
                CommandHandler("weather", weather),
                CommandHandler("forecast", forecast),
                CommandHandler("route", route),
                CommandHandler("stop", stop),
                CommandHandler("resume", resume),
                MessageHandler(filters.LOCATION, position),
            ]
        }

        # Handler per le conversazioni
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states=states,
            fallbacks=[CommandHandler("stop", stop)],
            name="main_conversation",
            persistent=True,
        )

        application.add_handler(conv_handler)

        # Handler di errore globale
        application.add_error_handler(error_handler)

        # Avvia il polling
        logger.info("🤖 Telegram Bot started!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"Critical error starting the bot: {e}")
        # In un ambiente di produzione, potremmo voler riavviare il bot qui


if __name__ == "__main__":
    main()