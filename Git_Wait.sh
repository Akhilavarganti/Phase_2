echo ""
echo "[STEP 12] Running application..."

APP_PATH="./dist/uds_disgnostics"
WAIT_TIME=10   # total wait time in seconds
INTERVAL=2     # check every 2 seconds

ELAPSED=0

while [ $ELAPSED -lt $WAIT_TIME ]; do
    if [ -f "$APP_PATH" ]; then
        echo "[INFO] Application found. Executing..."

        chmod +x "$APP_PATH"
        "$APP_PATH"
        break
    fi

    echo "[INFO] Waiting for application... ($ELAPSED/$WAIT_TIME)"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

# If still not found after waiting
if [ ! -f "$APP_PATH" ]; then
    echo "[WARNING] Application not found after waiting $WAIT_TIME seconds."
fi













#!/bin/bash

read -p "Enter Git URL: " repo_url
read -p "Enter file path inside repo: " file_path
read -p "Enter destination folder: " dest

# Clone temporarily
git clone "$repo_url" temp_repo

# Copy required file
cp "temp_repo/$file_path" "$dest"

# Cleanup
rm -rf temp_repo

echo "File copied successfully"
