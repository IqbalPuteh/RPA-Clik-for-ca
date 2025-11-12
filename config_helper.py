import os
from dotenv import load_dotenv
from pathlib import Path

# 1. Auto-load variables from .env
ENV_PATH = Path(__file__).parent / "config.py"
load_dotenv(dotenv_path=ENV_PATH, override=True)

def load_settings() -> dict:
    """
    Returns a dict of current settings,
    converting HEADLESS into a boolean.
    """
    return {
        "LOGIN_URL":  os.getenv("LOGIN_URL", ""),
        "USERNAME":   os.getenv("USERNAME", ""),
        "PASSWORD":   os.getenv("PASSWORD", ""),
        "BASE_URL":   os.getenv("BASE_URL", ""),
        "HEADLESS":   os.getenv("HEADLESS", "False").lower() in ("1", "True", "yes")
    }

def update_env(updates: dict):
    """
    Overwrites values in the config.py file
    """
    # 1. Read existing lines
    lines = ENV_PATH.read_text().splitlines()
    data = {}
    for line in lines:
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            data[key] = val

    # 2. Apply updates
    for k, v in updates.items():
        data[k] = str(v)

    # 3. Write back atomically
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for key, val in data.items():
            f.write(f"{key}={val}\n")
