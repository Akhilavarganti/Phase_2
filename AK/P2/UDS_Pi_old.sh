#!/bin/bash
#echo "Enable SPI, I2C..."
#sudo raspi-config

#echo "Edit config.txt...."
#sudo nano /boot/firmware/config.txt

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
JSON_FILE="$PROJECT_DIR/git_credentials.json"
GIT_URL = $(jq -r '.git.repo_url' $JSON_FILE)

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
dest1="$PROJECT_DIR/dist/supportfiles"
cp "$SELECTED_FILE" "$dest1"

echo "File copied successfully"

echo ""
##########################################################
# ==========================================
# STEP 8: FIND JSON FILES
# ==========================================

echo ""
echo "[STEP 8] Searching json files..."

JSON_FILES=()

while IFS= read -r -d '' file
do
    JSON_FILES+=("$file")
done < <(find "$REPO_NAME" -type f \( \
-name "*.json" \
\) -print0)

if [ ${#JSON_FILES[@]} -eq 0 ]; then
    echo "[ERROR] No json files found inside:"
    echo "$REPO_NAME/input"
    exit 1
fi

# ==========================================
# STEP 9: DISPLAY JSON
# ==========================================

echo ""
echo "======================================="
echo " AVAILABLE JSON"
echo "======================================="

INDEX=1

for file in "${JSON_FILES[@]}"
do
    BASENAME=$(basename "$file")
    echo "$INDEX. $BASENAME"
    INDEX=$((INDEX+1))
done

# ==========================================
# STEP 10: USER SELECTS JSON
# ==========================================

echo ""
read -p "Select json file number: " CHOICE

if ! [[ "$CHOICE" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] Invalid input."
    exit 1
fi

if [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "${#JSON_FILES[@]}" ]; then
    echo "[ERROR] Invalid json selection."
    exit 1
fi

SELECTED_FILE="${JSON_FILES[$((CHOICE-1))]}"
SELECTED_BASENAME=$(basename "$SELECTED_FILE")

echo ""
echo "[INFO] Selected json: $SELECTED_BASENAME"


# ==========================================
# STEP 11: COPY SELECTED JSON FILE
# ==========================================
# Copy required file
dest2="$PROJECT_DIR/dist"
cp "$SELECTED_FILE" "$dest2"

echo "JSON File copied successfully"

echo ""

# ==========================================
# STEP 12: RUNNING APPLICATION
# ==========================================
echo "[STEP 12] Running EXE..."

if [ -f ./dist/uds_diagnostics ]; then
    chmod +x ./dist/uds_diagnostics
    sudo ./dist/uds_diagnostics
    
else
    echo "[WARNING] ./dist/uds_diagnostics not found."
fi

# ==========================================
# STEP 13: Copy and push output to GIT
# ==========================================
echo "[STEP 13] Copying output to GIT..."


mkdir -p "$REPO_NAME/output"

cp -r "$PROJECT_DIR/dist/output" "$REPO_NAME"
cd "$REPO_NAME"
git add output/
git commit -m "Output"
USERNAME=$(jq -r '.git.username' $JSON_FILE)
TOKEN=$(jq -r '.git.token' $JSON_FILE)

# Inject credentials into URL
AUTH_REPO_URL=$(echo "$REPO_URL" | sed "s#https://#https://$USERNAME:$TOKEN@#")

# Apply to git remote
git remote set-url origin "$AUTH_REPO_URL"

git push 

cd ..


echo ""
echo "======================================="
echo " PROCESS COMPLETED"
echo "======================================="
