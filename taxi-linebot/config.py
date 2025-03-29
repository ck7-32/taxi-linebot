import os
from dotenv import load_dotenv

# 確保正確載入.env檔案
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

class Config:
    # Line API
    LINE_CHANNEL_ACCESS_TOKEN = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
    LINE_CHANNEL_SECRET = os.environ['LINE_CHANNEL_SECRET']
    
    # MongoDB
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/taxi_linebot')
    
    # Application
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    
    # Registration
    PASSWORD_SALT = os.getenv('PASSWORD_SALT', 'your-password-salt-here')
    EMAIL_VERIFICATION_EXPIRE = int(os.getenv('EMAIL_VERIFICATION_EXPIRE', '3600'))  # 1 hour
    
    # Email Configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
