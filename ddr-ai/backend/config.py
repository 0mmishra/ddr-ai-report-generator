"""Configuration module for runtime settings and secrets."""

from __future__ import annotations

import os

from dotenv import load_dotenv


# Load environment variables from a .env file at startup.
load_dotenv()


def get_openrouter_api_key() -> str:
    """Return OpenRouter API key or raise a clear error if missing."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file before running the app."
        )
    return api_key


def get_openrouter_model() -> str:
    """Return OpenRouter model with a sensible default."""
    return os.getenv("OPENROUTER_MODEL", "openrouter/auto").strip() or "openrouter/auto"
