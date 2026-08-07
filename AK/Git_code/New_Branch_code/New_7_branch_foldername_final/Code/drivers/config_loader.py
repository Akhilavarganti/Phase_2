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


def load_config(config_path):
    """
    Load any JSON configuration file.
    """

    if not os.path.isabs(config_path):
        config_path = os.path.join(BASE_PATH, config_path)

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Configuration file not found:\n{config_path}"
        )

    try:
        with open(config_path, "r") as file:
            config = json.load(file)

        return config

    except json.JSONDecodeError as e:
        raise Exception(
            f"Invalid JSON format in:\n{config_path}\n\n{str(e)}"
        )

    except Exception as e:
        raise Exception(
            f"Failed to load configuration:\n{config_path}\n\n{str(e)}"
        )


if __name__ == "__main__":
    config = load_config("config.json")
    print(config)