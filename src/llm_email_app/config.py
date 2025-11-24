from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env')

class Settings:
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY')
    GOOGLE_CLIENT_ID: str = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET: str = os.getenv('GOOGLE_CLIENT_SECRET')
    GOOGLE_OAUTH_REDIRECT_URI: str = os.getenv('GOOGLE_OAUTH_REDIRECT_URI')
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'your-secret-key-here')
    DRY_RUN: bool = os.getenv('DRY_RUN', 'true').lower() in ('1', 'true', 'yes')
    MAX_TOKEN: int = int(os.getenv('MAX_TOKEN', '5120'))
    
settings = Settings()
