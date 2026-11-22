import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "38138069"))
API_HASH = os.getenv("API_HASH", "2ed313ebcc45cbcf65d1fc736ec71681")
BOT_TOKEN = os.getenv("BOT_TOKEN", "9011562157:AAESDsnVTiudMRkq-XCT1l-fN61UalxOFKg")
OWNER_ID = int(os.getenv("OWNER_ID", "8724182918"))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "-1003947649552"))
START_IMG = os.getenv("START_IMG", "https://files.catbox.moe/fxl81r.jpg")
UPDATE_URL = os.getenv("UPDATE_URL", "https://t.me/NovaBot_Support")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/+KstoIqu4bgRlZGYx")
PORT = int(os.getenv("PORT", "8080"))
