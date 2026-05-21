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

# Ask user for Git URL
read -p "Enter Git Repository URL: " repo_url

# Ask for destination folder
read -p "Enter local folder name: " folder_name

# Clone repo
git clone "$repo_url" "$folder_name"

# Check result
if [ $? -eq 0 ]; then
    echo "Repository cloned successfully into $folder_name"
else
    echo "Failed to clone repository"
fi
