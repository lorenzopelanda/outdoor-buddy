from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, \
    ConversationHandler, PersistenceInput, PicklePersistence
from processing import utils
from concurrent.futures import ProcessPoolExecutor
import requests
import os
import signal
import asyncio
import logging
from datetime import datetime, timedelta
import re
from dotenv import load_dotenv
import json
import sys
import tempfile
from mistralai import Mistral


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
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")


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
        "\n/route [Address] [distance in km] [level of training:\n\tbeginner,intermediate,advanced] -> to have a suggested bike track for your adventutres\n/stop -> to pause the Bot.",
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
            "Extract the following parameters from the text: address, distance (km), level, duration (hours), and ascent (optional). "
            "Return a JSON. Ignore irrelevant details.\n"
            f"Text: {message}\nOutput:"
        )

        async with Mistral(
            api_key=os.getenv("MISTRAL_API_KEY"),
        ) as mistral:
            response = await mistral.chat.complete_async(
                model="mistral-small-latest",
                messages=[
                    {
                        "content": prompt,
                        "role": "user",
                    },
                ], stream =False)

        response_text = response.choices[0].message.content.strip()
        response_text = re.sub(r"```json\n(.*?)\n```", r"\1", response_text, flags=re.DOTALL)

        return json.loads(response_text)
    except Exception as e:
        logger.error(f"Error in AI parsing: {e}")
        raise


async def route(update: Update, context: CallbackContext) -> int:
    if context.bot_data.get('is_paused', False):
        await update.message.reply_text("🛑 Bot is paused. Use /resume to continue.")
        return AWAITING_COMMAND

    try:
        if len(update.message.text) <= len("/route"):
            await update.message.reply_text("❌ Please provide route details after the /route command.")
            return AWAITING_COMMAND

        user_input = update.message.text[len("/route"):]
        try:
            params = await parse_input_with_ai(user_input)
        except Exception as e:
            logger.error(f"Error in AI parsing: {e}")
            # Fallback to default values
            params = {
                "address": "Via Vigna 10, Ciriè",
                "distance": 50,
                "level": "intermediate"
            }

        logger.info(f"Params after parsing: {params}")
        address = params["address"]
        distance = float(params["distance"])
        level = params["level"].lower()

        if distance <= 0:
            await update.message.reply_text("❌ Distance must be greater than 0.")
            return AWAITING_COMMAND

        if not re.match(r"beginner|intermediate|advanced", level):
            await update.message.reply_text("❌ Level must be 'beginner', 'intermediate', or 'advanced'.")
            return AWAITING_COMMAND

        # Tell the user we're processing
        message = await update.message.reply_text("🔄 Processing your route request. This may take a few minutes...")

        # Create a unique ID for this route request
        route_id = f"route_{update.effective_user.id}_{int(asyncio.get_event_loop().time())}"
        output_file = f"{route_id}.gpx"

        # Run the route planner in a separate Python process
        success = await run_route_planner_process(address, distance, level, output_file)

        if success:
            # Update the message to indicate success
            await message.edit_text("✅ Route successfully created. Check your email for the GPX file.")

            # Here you would add code to email the GPX file to the user
            # send_email_with_attachment(user_email, output_file)

            logger.info("Route creation completed, response sent.")
        else:
            await message.edit_text("❌ Failed to create route. Please try again with different parameters.")
    except Exception as e:
        logger.error(f"Error in route command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

    return AWAITING_COMMAND


async def run_route_planner_process(address, distance, level, output_file):
    """Run the route planner in a separate process with timeout"""
    try:
        # Create a temporary JSON file to pass parameters
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            params_file = f.name
            json.dump({
                "address": address,
                "distance": distance,
                "level": level,
                "output_file": output_file
            }, f)

        # Get the path to the dedicated route planner script
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'route_planner_process.py')

        # Make sure the script exists
        if not os.path.exists(script_path):
            logger.error(f"Route planner script not found at: {script_path}")
            return False

        # Run the script with timeout
        process = await asyncio.create_subprocess_exec(
            sys.executable, script_path, params_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            # Set a timeout (e.g., 5 minutes)
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0:
                logger.error(f"Route planning process failed with return code {process.returncode}")
                if stderr:
                    logger.error(f"STDERR: {stderr.decode()}")
                if stdout:
                    logger.info(f"STDOUT: {stdout.decode()}")
                return False

            logger.info("Route planning process completed successfully")
            return True
        except asyncio.TimeoutError:
            logger.error("Route planning process timed out after 5 minutes")
            process.kill()
            return False
    except Exception as e:
        logger.error(f"Failed to run route planner: {e}")
        return False
    finally:
        # Clean up temporary files
        try:
            os.unlink(params_file)
        except Exception:
            pass

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