import os
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

class Config:
    # Telegram Bot Token
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # Maximum file size for downloads (in bytes)
    # Telegram bot API limit is 50MB for bots
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 50 * 1024 * 1024))
    
    # Download directory (optional, currently using current dir)
    DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', os.getcwd())

    # Validate configuration
    if not BOT_TOKEN:
        raise ValueError("No BOT_TOKEN provided. Please set the BOT_TOKEN environment variable.")
