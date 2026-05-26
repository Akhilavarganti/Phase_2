#!/bin/bash
cho "Enable SPI, I2C..."
sudo raspi-config

echo "Edit config.txt...."
sudo nano /boot/firmware/config.txt
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


mkdir -p "$OUTPUT_DIR/output"
mkdir -p "$OUTPUT_DIR/supportfiles"


echo "======================================="
echo " ECU GIT DYNAMIC TESTCASE MANAGER"
echo "======================================="

# ==========================================
# STEP 0: INSTALL REQUIREMENTS
# ==========================================

echo ""
echo "[STEP 0] Checking Git installation..."

sudo apt update
sudo apt install -y git

echo "[DONE] Git ready."

# ==========================================
# STEP 1: GET GIT URL FROM USER
# ==========================================

echo ""
read -p "Enter Git Repository URL: " GIT_URL

if [ -z "$GIT_URL" ]; then
    echo "[ERROR] Git URL cannot be empty."
    exit 1
fi

# ==========================================
# STEP 2: EXTRACT REPO NAME
# ==========================================

REPO_NAME=$(basename "$GIT_URL" .git)

echo ""
echo "[INFO] Repository Name: $REPO_NAME"

# ==========================================
# STEP 3: CLONE OR UPDATE REPO
# ==========================================

if [ -d "$REPO_NAME/.git" ]; then
    echo ""
    echo "[STEP 3] Repository exists. Pulling latest changes..."

    cd "$REPO_NAME"

    git pull

    cd ..

else
    echo ""
    echo "[STEP 3] Cloning repository..."

    git clone "$GIT_URL"

fi

echo "[DONE] Repository ready."

# ==========================================
# STEP 4: FIND TESTCASE FILES
# ==========================================

echo ""
echo "[STEP 4] Searching testcase files..."

TESTCASE_FILES=()

while IFS= read -r -d '' file
do
    TESTCASE_FILES+=("$file")
done < <(find "$REPO_NAME" -type f \( \
-name "*.txt" \
\) -print0)

if [ ${#TESTCASE_FILES[@]} -eq 0 ]; then
    echo "[ERROR] No testcase files found inside:"
    echo "$REPO_NAME/input"
    exit 1
fi

# ==========================================
# STEP 5: DISPLAY TESTCASES
# ==========================================

echo ""
echo "======================================="
echo " AVAILABLE TESTCASES"
echo "======================================="

INDEX=1

for file in "${TESTCASE_FILES[@]}"
do
    BASENAME=$(basename "$file")
    echo "$INDEX. $BASENAME"
    INDEX=$((INDEX+1))
done

# ==========================================
# STEP 6: USER SELECTS TESTCASE
# ==========================================

echo ""
read -p "Select testcase number: " CHOICE

if ! [[ "$CHOICE" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] Invalid input."
    exit 1
fi

if [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "${#TESTCASE_FILES[@]}" ]; then
    echo "[ERROR] Invalid testcase selection."
    exit 1
fi

SELECTED_FILE="${TESTCASE_FILES[$((CHOICE-1))]}"
SELECTED_BASENAME=$(basename "$SELECTED_FILE")

echo ""
echo "[INFO] Selected testcase: $SELECTED_BASENAME"


# ==========================================
# STEP 7: COPY TESTCASE FILE
# ==========================================
# Copy required file
dest="$PROJECT_DIR/dist/supportfiles"
cp "$SELECTED_FILE" "$dest"

echo "File copied successfully"

echo ""

# ==========================================
# STEP 8: RUNNING APPLICATION
# ==========================================
echo "[STEP 8] Running application..."

if [ -f ./dist/uds_diagnostics ]; then
    chmod +x ./dist/uds_diagnostics
    sudo ./dist/uds_diagnostics
    
else
    echo "[WARNING] ./dist/uds_diagnostics not found."
fi

# ==========================================
# STEP 9: Copy and push output to GIT
# ==========================================
echo "[STEP 9] Copying output to GIT..."


mkdir -p "$REPO_NAME/output"

cp -r "$PROJECT_DIR/dist/output" "$REPO_NAME/output"
cd "$REPO_NAME"
git add output/
git commit -m "Output"
git push 

cd ..


echo ""
echo "======================================="
echo " PROCESS COMPLETED"
echo "======================================="
