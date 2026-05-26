#import json

#def load_config(file_path):
#    with open(file_path, 'r') as file:
#        return json.load(file)

import os
import sys
import json

def get_base_path():
    """
    Returns executable location in EXE mode
    and script location in normal Python mode.
    """

    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_base_path()

CONFIG_PATH = os.path.join(BASE_PATH, "config.json")


def load_config():
    """
    Load config.json safely.
    """

    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"config.json not found at:\n{CONFIG_PATH}"
        )

    try:
        with open(CONFIG_PATH, "r") as file:
            config = json.load(file)

        return config

    except json.JSONDecodeError as e:
        raise Exception(
            f"Invalid JSON format in config.json\n{str(e)}"
        )

    except Exception as e:
        raise Exception(
            f"Failed to load config.json\n{str(e)}"
        )


if __name__ == "__main__":
    config = load_config()
    print(config)