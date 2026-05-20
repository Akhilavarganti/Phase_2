#!/bin/bash

CLONE_DIR="ecu_repo"

echo "Enter Git Repo URL:"
read REPO_URL

# Step 1: Clone or Pull
if [ -d "$CLONE_DIR" ]; then
    echo "Repo already exists. Pulling latest changes..."
    cd $CLONE_DIR
    git pull
    cd ..
else
    echo "Cloning repository..."
    git clone $REPO_URL $CLONE_DIR
fi

# Step 2: Show testcases
python3 select_testcase.py

# Step 3: Run your project
echo "Running project..."
python3 main.py
