#!/usr/bin/env bash
# Build UDS Diagnostics on Raspberry Pi OS (Bookworm or newer).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="uds_diagnostics"
VENV_DIR="$PROJECT_DIR/venv"
OUTPUT_DIR="$PROJECT_DIR/dist"

echo ""
echo "=============================================="
echo "  UDS Diagnostics - Raspberry Pi Build Tool"
echo "=============================================="
echo ""

# RPi.GPIO is unmaintained and does not support current Python releases.  On
# Raspberry Pi OS, python3-rpi-lgpio is its supported, API-compatible
# replacement; it still provides `import RPi.GPIO as GPIO`.
echo "[1/6] Installing Raspberry Pi GPIO system package..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip python3-rpi-lgpio

echo "[2/6] Creating virtual environment..."
# Include the GPIO package installed by apt.  Do not pip-install RPi.GPIO or
# lgpio: pip may try to compile lgpio and fails on unsupported Python versions.
python3 -m venv --system-site-packages "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[3/6] Updating build tools..."
python -m pip install --upgrade pip setuptools wheel

echo "[4/6] Installing Python dependencies into the virtual environment..."
python -m pip install \
    pyinstaller \
    adafruit-circuitpython-ssd1306 \
    adafruit-blinka \
    Pillow \
    python-can \
    can-isotp \
    udsoncan

echo "[5/6] Verifying GPIO compatibility package..."
python -c "import RPi.GPIO as GPIO; print('GPIO backend:', GPIO.VERSION)"

echo "[6/6] Building executable with PyInstaller..."
cd "$PROJECT_DIR"

python -m PyInstaller \
    --onefile \
    --clean \
    --name "$APP_NAME" \
    --collect-all adafruit_platformdetect \
    --collect-all adafruit_blinka \
    --collect-all digitalio \
    --collect-all busio \
    --collect-all microcontroller \
    --collect-data microcontroller \
    --hidden-import board \
    --hidden-import RPi \
    --hidden-import RPi.GPIO \
    --hidden-import adafruit_blinka \
    --hidden-import adafruit_blinka.board \
    --hidden-import adafruit_platformdetect \
    --hidden-import adafruit_platformdetect.constants \
    --hidden-import busio \
    --hidden-import adafruit_ssd1306 \
    --hidden-import PIL \
    --hidden-import PIL.Image \
    --hidden-import PIL.ImageDraw \
    --hidden-import PIL.ImageFont \
    --hidden-import can \
    --hidden-import can.interfaces.socketcan \
    --hidden-import can.io.asc \
    --hidden-import isotp \
    --hidden-import udsoncan \
    --hidden-import udsoncan.client \
    --hidden-import udsoncan.connections \
    --hidden-import udsoncan.configs \
    --hidden-import udsoncan.services \
    --hidden-import drivers \
    --hidden-import drivers.config_loader \
    --hidden-import drivers.oled_display \
    --hidden-import drivers.button_input \
    --hidden-import drivers.uds_client \
    --hidden-import drivers.transfer_file \
    --hidden-import drivers.Parse_handler \
    --hidden-import drivers.can_logger \
    --hidden-import drivers.report_generator \
    --hidden-import drivers.git_manager \
    --hidden-import drivers.initialize_interfaces \
    --hidden-import drivers.ssh_setup \
    --hidden-import drivers.did_decoder \
    --hidden-import drivers.terminal_ui \
    --hidden-import drivers.install_service \
    main.py

if [[ -f "$OUTPUT_DIR/$APP_NAME" ]]; then
    echo "Build complete: $OUTPUT_DIR/$APP_NAME"
else
    echo "Build failed: executable not found at $OUTPUT_DIR/$APP_NAME" >&2
    exit 1
fi
