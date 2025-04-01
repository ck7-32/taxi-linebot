# --- config.py ---
import os
from dotenv import load_dotenv

# 確保正確載入.env檔案
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    # Line API
    LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
    LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

    # MongoDB
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'carpool_bot_db')

    # Application
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-secret-key')

    # Google Maps API Key (config 會讀取，即使模板不用)
    Maps_API_KEY = os.environ.get('Maps_API_KEY')

    # Matching Settings
    MATCH_INTERVAL_MINUTES = int(os.environ.get('MATCH_INTERVAL_MINUTES', 1))
    MATCH_TIMEOUT_MINUTES = int(os.environ.get('MATCH_TIMEOUT_MINUTES', 10))
    DESTINATION_PRECISION = int(os.environ.get('DESTINATION_PRECISION', 4))

    @staticmethod
    def check_essential_configs():
        essential = ['LINE_CHANNEL_ACCESS_TOKEN', 'LINE_CHANNEL_SECRET', 'MONGO_URI', 'MONGO_DB_NAME']
        missing = [key for key in essential if not getattr(Config, key)]
        if missing:
            raise ValueError(f"Missing essential configuration keys: {', '.join(missing)}")