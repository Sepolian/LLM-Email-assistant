from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env')


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


class Settings:
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY')
    GOOGLE_CLIENT_ID: str = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET: str = os.getenv('GOOGLE_CLIENT_SECRET')
    GOOGLE_OAUTH_REDIRECT_URI: str = os.getenv('GOOGLE_OAUTH_REDIRECT_URI')
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'your-secret-key-here')
    BACKEND_PORT: int = int(os.getenv('BACKEND_PORT', '8000'))
    DRY_RUN: bool = _as_bool(os.getenv('DRY_RUN', 'true'), default=True)
    MAX_TOKEN: int = int(os.getenv('MAX_TOKEN', '5120'))

    # Automation / background processing knobs
    BACKGROUND_REFRESH_INTERVAL_MINUTES: int = int(os.getenv('BACKGROUND_REFRESH_INTERVAL_MINUTES', '10'))
    AUTO_LABEL_RULES_PATH: Path = Path(os.getenv('AUTO_LABEL_RULES_PATH') or (BASE_DIR / 'data' / 'rules.json'))
    AUTO_LABEL_PROCESSED_PATH: Path = Path(os.getenv('AUTO_LABEL_PROCESSED_PATH') or (BASE_DIR / 'tmp' / 'auto_label_processed.json'))
    AUTO_LABEL_ENABLED_DEFAULT: bool = _as_bool(os.getenv('AUTO_LABEL_ENABLED_DEFAULT', 'false'), default=False)
    AUTO_LABEL_LOOKBACK_DAYS: int = int(os.getenv('AUTO_LABEL_LOOKBACK_DAYS', '7'))
    AUTO_LABEL_MAX_PER_CYCLE: int = int(os.getenv('AUTO_LABEL_MAX_PER_CYCLE', '20'))
    AUTO_LABEL_REQUEST_INTERVAL_SECONDS: float = float(os.getenv('AUTO_LABEL_REQUEST_INTERVAL_SECONDS', '5'))


settings = Settings()
