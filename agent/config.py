"""
Configuration module for the Data Q&A agent.

Loads API keys from environment variables or a .env file,
and defines paths and model settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists (project root, parent, or home)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.home() / ".env")

# ---------------------------------------------------------------------------
# Google Gemini settings
# ---------------------------------------------------------------------------
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")

# Model to use — Gemini 2.0 Flash is fast and cost-effective
MODEL_NAME: str = "gemini-2.0-flash"

# Temperature settings
TEMPERATURE_ROUTING: float = 0.0   # deterministic for classification
TEMPERATURE_SQL: float = 0.0       # deterministic for SQL generation
TEMPERATURE_SYNTHESIS: float = 0.3  # slightly creative for answer prose

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DB_PATH: Path = _PROJECT_ROOT / "data" / "quality.db"
PROCEDURES_DIR: Path = _PROJECT_ROOT / "data" / "procedures"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_config(strict: bool = False) -> None:
    """Validate configuration. If strict is True, requires GOOGLE_API_KEY."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    if not PROCEDURES_DIR.exists():
        raise FileNotFoundError(f"Procedures directory not found at {PROCEDURES_DIR}")
    if not GOOGLE_API_KEY:
        if strict:
            raise EnvironmentError(
                "GOOGLE_API_KEY is not set. "
                "Export it in your shell or add it to a .env file at the project root.\n"
                "  export GOOGLE_API_KEY='your-key-here'"
            )
        else:
            print("  ℹ️  [Notice] GOOGLE_API_KEY not configured — using built-in reasoning engine.")
