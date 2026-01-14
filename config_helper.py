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
    # Get the raw value from environment (without quotes)
    headless_raw = os.getenv("HEADLESS", "False")
    
    # Strip quotes if present
    if headless_raw.startswith('"') and headless_raw.endswith('"'):
        headless_raw = headless_raw[1:-1]
    elif headless_raw.startswith("'") and headless_raw.endswith("'"):
        headless_raw = headless_raw[1:-1]
    
    return {
        "LOGIN_URL":  os.getenv("LOGIN_URL", ""),
        "USERNAME":   os.getenv("USERNAME", ""),
        "PASSWORD":   os.getenv("PASSWORD", ""),
        "BASE_URL":   os.getenv("BASE_URL", ""),
        "HEADLESS":   headless_raw.lower() in ("1", "true", "yes")
    }

def update_env(updates: dict):
    """
    Overwrites values in the config.py file
    HEADLESS is saved without quotes, other values with quotes
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
        if k == "HEADLESS":
            # Convert boolean to string without quotes
            if isinstance(v, bool):
                v = "True" if v else "False"
            # HEADLESS is saved without quotes
            data[k] = v
        else:
            # Add quotes around other string values
            data[k] = f'"{v}"'

    # 3. Write back atomically
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for key, val in data.items():
            f.write(f"{key}={val}\n")