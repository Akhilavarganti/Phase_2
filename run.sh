#!/bin/bash

cd ~/ecu_jobs

echo "Starting..."

selected_file=$(python3 git_file_selector.py | tail -n 1)

echo "Selected file: $selected_file"

# 👉 Pass to your logic
python3 ecu_runner.py "input/$selected_file"
