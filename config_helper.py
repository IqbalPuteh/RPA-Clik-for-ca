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
    # Ensure we have the latest values from the file
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    
    # Get the raw value from environment (without quotes)
    headless_raw = os.getenv("HEADLESS", "False")
    
    # Strip quotes if present (just in case they were added manually or by error)
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
    Overwrites values in the config.py file.
    Ensures strings are quoted and booleans (HEADLESS) are unquoted.
    PRESERVES existing values that are not in the updates dict.
    """
    # 1. Read existing configuration to preserve comments and layout if possible,
    # or at least preserve values not being updated.
    # However, for simplicity and robustness against the fragile parsing, 
    # we will read the current ENV vars as the source of truth for partial updates (if needed),
    # but the requirement implies we might want to just re-write the specific keys.
    
    # Because the file is a python file, we construct the content carefully.
    # We will read the file line by line to build a map of existing keys to preserve their order/existence if we wanted to be fancy,
    # but the original implementation just overwrote 'data' dict from the file.
    # Let's stick to the previous logic but improve writing.
    
    # Read existing lines to capture keys that might be there but not in 'updates' (though we likely update all relevant ones)
    current_lines = ENV_PATH.read_text().splitlines()
    data = {}
    
    for line in current_lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            # Store raw value for now
            data[key] = val

    # 2. Apply updates
    for k, v in updates.items():
        if k == "HEADLESS":
            # Boolean/String logic for HEADLESS
            # We want it to be True or False (boolean literal in python)
            if isinstance(v, bool):
                val_str = "True" if v else "False"
            else:
                # If it comes as string "True"/"False"
                val_str = "True" if str(v).lower() == "true" else "False"
            data[k] = val_str
        else:
            # All other known keys are strings and must be quoted
            # We assume 'v' is the raw string value (e.g. user input)
            # escape double quotes if necessary? simplistic approach for now:
            # The previous code didn't escape, so we'll just wrap in double quotes.
            # Avoid double quoting if already quoted (though updates usually come raw)
            
            # The input 'v' from the API is likely raw string.
            val_str = f'"{v}"'
            data[k] = val_str

    # 3. Write back
    # We write completely new content to ensure clean formatting
    output_lines = []
    for key, val in data.items():
        output_lines.append(f"{key}={val}")
        
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
        f.write("\n") # trailing newline