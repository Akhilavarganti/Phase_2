#!/bin/bash

set -e

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
# STEP 4: CREATE REQUIRED STRUCTURE
# ==========================================

echo ""
echo "[STEP 4] Ensuring folder structure exists..."

mkdir -p "$REPO_NAME/input"
mkdir -p "$REPO_NAME/output"
mkdir -p "$REPO_NAME/jobs"

echo "[DONE] Structure verified."

# ==========================================
# STEP 5: FIND TESTCASE FILES
# ==========================================

echo ""
echo "[STEP 5] Searching testcase files..."

TESTCASE_FILES=()

while IFS= read -r -d '' file
do
    TESTCASE_FILES+=("$file")
done < <(find "$REPO_NAME/input" -type f \( \
-name "*.txt" -o \
-name "*.json" -o \
-name "*.yaml" -o \
-name "*.yml" \
\) -print0)

if [ ${#TESTCASE_FILES[@]} -eq 0 ]; then
    echo "[ERROR] No testcase files found inside:"
    echo "$REPO_NAME/input"
    exit 1
fi

# ==========================================
# STEP 6: DISPLAY TESTCASES
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
# STEP 7: USER SELECTS TESTCASE
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
# STEP 8: CREATE/UPDATE jobs.json
# ==========================================

echo ""
echo "[STEP 8] Updating jobs.json..."

cat > "$REPO_NAME/jobs/jobs.json" <<EOF
{
    "selected_testcase": "$SELECTED_BASENAME",
    "status": "pending"
}
EOF

echo "[DONE] jobs.json updated."

# ==========================================
# STEP 9: CREATE/UPDATE config.json
# ==========================================

echo ""
echo "[STEP 9] Updating config.json..."

cat > config.json <<EOF
{
    "git": {
        "enabled": true,
        "repo_path": "./$REPO_NAME",
        "branch": "main",
        "auto_pull": true,
        "auto_push": true
    }
}
EOF

echo "[DONE] config.json updated."

# ==========================================
# STEP 10: PUSH CHANGES TO GIT
# ==========================================

echo ""
echo "[STEP 10] Pushing updates to Git..."

cd "$REPO_NAME"

git add .

git commit -m "Updated selected testcase" || true

git push || true

cd ..

echo "[DONE] Git sync completed."

# ==========================================
# STEP 11: BUILD APPLICATION
# ==========================================

echo ""
echo "[STEP 11] Building application..."

if [ -f build_on_pi.sh ]; then
    chmod +x build_on_pi.sh
    ./build_on_pi.sh
    echo "[DONE] Build successful."
else
    echo "[WARNING] build_on_pi.sh not found. Skipping build."
fi

# ==========================================
# STEP 12: RUN APPLICATION
# ==========================================

echo ""
echo "[STEP 12] Running application..."

if [ -f ./dist/uds_disgnostics ]; then
    chmod +x ./dist/uds_disgnostics
    ./dist/uds_disgnostics
else
    echo "[WARNING] ./dist/uds_disgnostics not found."
fi

echo ""
echo "======================================="
echo " PROCESS COMPLETED"
echo "======================================="
