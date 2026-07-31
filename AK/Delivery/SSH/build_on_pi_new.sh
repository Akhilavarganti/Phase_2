
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="uds_diagnostics"
OUTPUT_DIR="$PROJECT_DIR/dist"
DATA_DIR="$PROJECT_DIR/venv/lib/python3.13/site-packages"

echo ""
echo "=============================================="
echo "  UDS Diagnostics - Raspberry Pi Build Tool"
echo "=============================================="
echo ""

echo "configure hardware interfaces"
echo "Enable SPI, I2C..."
sudo raspi-config

echo "Edit config.txt...."
sudo nano /boot/firmware/config.txt

# ---Step 1 : Create Virtual env ---
echo "[1/8] Creating Virtual env..."

# Python 3.13 has no Raspberry Pi wheel for lgpio on PyPI.  Use the
# Raspberry Pi OS package and expose it to this venv, so pip does not try
# to compile lgpio from source during the Blinka installation.
sudo apt-get update
sudo apt-get install -y python3-lgpio

python3 -m venv --system-site-packages venv
echo "Activating  venv..."
source venv/bin/activate
echo "Changing directory to virtual env..."
cd $PROJECT_DIR/venv

# --- Step 2: Check Python version ---
echo "[2/8] Checking Python..."
python3 --version || { echo "ERROR: python3 not found. Install it with: sudo apt install python3"; exit 1; }

# --- Step 3: Install pip if missing ---
echo "[3/8] Checking pip..."
python3 -m pip --version 2>/dev/null || {
    echo "pip not found, installing..."
    sudo apt-get install -y python3-pip
}

# --- Step 4 : Install pyinstaller if missing ---
echo "[4/8] checking pyinstaller..."
python3 -m PyInstaller --version 2>/dev/null || {
    echo "pyinstaller not found, installing..."
    python3 -m pip install pyinstaller
}

# --- Step 5: Install all required Python dependencies ---
echo "[5/8] Installing Python dependencies..."
python3 -c "import lgpio" || {
    echo "ERROR: python3-lgpio is not available to the virtual environment."
    exit 1
}
python3 -m pip install \
    pyinstaller \
    RPi.GPIO \
    adafruit-circuitpython-ssd1306 \
    adafruit-blinka \
    Pillow \
    python-can \
    can-isotp \
    udsoncan

echo ""
echo "[6/8] Setting up project structure..."
cd "$PROJECT_DIR"

# Make sure drivers folder has __init__.py
touch drivers/__init__.py

# --- Step 7: Run PyInstaller ---
echo "[7/8] Building executable with PyInstaller..."
echo "      This may take a few minutes..."
echo ""

pyinstaller \
    --onefile \
    --clean \
    --name "$APP_NAME" \
     --collect-all adafruit_platformdetect \
     --collect-all adafruit_blinka \
    --collect-all lgpio \
    --collect-all digitalio \
    --collect-all busio \
    --collect-all microcontroller \
    --collect-data microcontroller \
    --add-data "$DATA_DIR/board_imports.json:." \
    --add-data "$DATA_DIR/microcontroller_imports.json:." \
    --hidden-import board \
    --hidden-import RPi \
    --hidden-import RPi.GPIO \
    --hidden-import board \
    --hidden-import adafruit_blinka \
    --hidden-import adafruit_blinka.board \
    --hidden-import lgpio \
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



mkdir -p "$OUTPUT_DIR/output"
mkdir -p "$OUTPUT_DIR/supportfiles"

# --- Step 8: Done ---
echo ""
echo "[8/8] Build complete!"
echo ""

if [ -f "$OUTPUT_DIR/$APP_NAME" ]; then
    echo "  Executable created:"
    echo "     $OUTPUT_DIR/$APP_NAME"
    echo ""
    echo "  File size: $(du -sh "$OUTPUT_DIR/$APP_NAME" | cut -f1)"
    echo ""
    echo "  To run:"
    echo "     sudo $OUTPUT_DIR/$APP_NAME"
    echo ""
else
    echo "  Build failed - executable not found in dist/"
    echo "     Check the build output above for errors."
    exit 1
fi
