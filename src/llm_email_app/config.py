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
    DEMO_MODE: bool = _as_bool(os.getenv('DEMO_MODE', 'false'), default=False)
    MAX_TOKEN: int = int(os.getenv('MAX_TOKEN', '5120'))
    DEMO_REFERENCE_TIME: str = os.getenv('DEMO_REFERENCE_TIME', '').strip()
    DEMO_EMAIL_FIXTURE_PATH: Path = Path(os.getenv('DEMO_EMAIL_FIXTURE_PATH') or (BASE_DIR / 'src' / 'llm_email_app' / 'demo_fixtures' / 'mailbox.json'))
    DEMO_CALENDAR_FIXTURE_PATH: Path = Path(os.getenv('DEMO_CALENDAR_FIXTURE_PATH') or (BASE_DIR / 'src' / 'llm_email_app' / 'demo_fixtures' / 'calendar.json'))
    DEMO_EMAIL_STATE_PATH: Path = Path(os.getenv('DEMO_EMAIL_STATE_PATH') or (BASE_DIR / 'tmp' / 'demo_mailbox_state.json'))
    DEMO_CALENDAR_STATE_PATH: Path = Path(os.getenv('DEMO_CALENDAR_STATE_PATH') or (BASE_DIR / 'tmp' / 'demo_calendar_state.json'))

    # Automation / background processing knobs
    BACKGROUND_REFRESH_INTERVAL_MINUTES: int = int(os.getenv('BACKGROUND_REFRESH_INTERVAL_MINUTES', '10'))
    AUTO_LABEL_RULES_PATH: Path = Path(os.getenv('AUTO_LABEL_RULES_PATH') or (BASE_DIR / 'data' / 'rules.json'))
    AUTO_LABEL_PROCESSED_PATH: Path = Path(os.getenv('AUTO_LABEL_PROCESSED_PATH') or (BASE_DIR / 'tmp' / 'auto_label_processed.json'))
    AUTO_LABEL_ENABLED_DEFAULT: bool = _as_bool(os.getenv('AUTO_LABEL_ENABLED_DEFAULT', 'false'), default=False)
    AUTO_LABEL_LOOKBACK_DAYS: int = int(os.getenv('AUTO_LABEL_LOOKBACK_DAYS', '7'))
    AUTO_LABEL_MAX_PER_CYCLE: int = int(os.getenv('AUTO_LABEL_MAX_PER_CYCLE', '20'))
    AUTO_LABEL_REQUEST_INTERVAL_SECONDS: float = float(os.getenv('AUTO_LABEL_REQUEST_INTERVAL_SECONDS', '5'))

    # Agent runtime
    AGENT_ENABLED: bool = _as_bool(os.getenv('AGENT_ENABLED', 'true'), default=True)
    AGENT_MODE: str = os.getenv('AGENT_MODE', 'semi_auto').strip().lower() or 'semi_auto'
    AGENT_SHADOW_MODE: bool = _as_bool(os.getenv('AGENT_SHADOW_MODE', 'false'), default=False)
    AGENT_MAX_STEPS: int = int(os.getenv('AGENT_MAX_STEPS', '8'))
    AGENT_MIN_CONFIDENCE: float = float(os.getenv('AGENT_MIN_CONFIDENCE', '0.75'))
    AGENT_AUTO_WRITE_RISK_LIMIT: str = os.getenv('AGENT_AUTO_WRITE_RISK_LIMIT', 'external_write').strip().lower() or 'external_write'
    AGENT_MEMORY_DIR: Path = Path(os.getenv('AGENT_MEMORY_DIR') or (BASE_DIR / 'data' / 'memory'))
    AGENT_APPROVALS_PATH: Path = Path(os.getenv('AGENT_APPROVALS_PATH') or (BASE_DIR / 'tmp' / 'agent_approvals.json'))
    AGENT_WORK_ITEMS_PATH: Path = Path(os.getenv('AGENT_WORK_ITEMS_PATH') or (BASE_DIR / 'tmp' / 'agent_work_items.json'))
    AGENT_THREADS_PATH: Path = Path(os.getenv('AGENT_THREADS_PATH') or (BASE_DIR / 'tmp' / 'agent_threads.json'))
    AGENT_TIMELINE_PATH: Path = Path(os.getenv('AGENT_TIMELINE_PATH') or (BASE_DIR / 'tmp' / 'agent_timeline.json'))
    AGENT_RUNS_PATH: Path = Path(os.getenv('AGENT_RUNS_PATH') or (BASE_DIR / 'tmp' / 'agent_runs.json'))
    AGENT_CHECKPOINTS_PATH: Path = Path(os.getenv('AGENT_CHECKPOINTS_PATH') or (BASE_DIR / 'tmp' / 'agent_checkpoints.sqlite'))
    AGENT_PROCESSED_PATH: Path = Path(os.getenv('AGENT_PROCESSED_PATH') or (BASE_DIR / 'tmp' / 'agent_processed.json'))


settings = Settings()
