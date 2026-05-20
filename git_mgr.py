#!/usr/bin/env python3

from git import Repo, GitCommandError
from pathlib import Path
import yaml
import json
import shutil
import re
import os

# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path.home() / "repositories"

ALLOWED_DOMAINS = [
    "github.com",
    "gitlab.com",
    "bitbucket.org"
]

SUPPORTED_EXTENSIONS = [
    ".json",
    ".yaml",
    ".yml",
    ".txt"
]

# ==========================================
# CREATE BASE DIRECTORY
# ==========================================

BASE_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# VALIDATE GIT URL
# ==========================================

def is_valid_git_url(url):
    pattern = r"^(https:\/\/|git@)"
    if not re.match(pattern, url):
        return False

    return any(domain in url for domain in ALLOWED_DOMAINS)

# ==========================================
# EXTRACT REPO NAME
# ==========================================

def get_repo_name(git_url):
    repo_name = git_url.split("/")[-1]
    repo_name = repo_name.replace(".git", "")
    return repo_name

# ==========================================
# CLONE OR UPDATE REPOSITORY
# ==========================================

def clone_or_update_repo(git_url):
    repo_name = get_repo_name(git_url)
    repo_path = BASE_DIR / repo_name

    try:
        if repo_path.exists():
            print(f"\n[INFO] Updating existing repository: {repo_name}")
            repo = Repo(repo_path)
            repo.remotes.origin.pull()
        else:
            print(f"\n[INFO] Cloning repository: {repo_name}")
            Repo.clone_from(git_url, repo_path)

        print("[SUCCESS] Repository ready.")
        return repo_path

    except GitCommandError as e:
        print(f"[ERROR] Git operation failed:\n{e}")
        return None

# ==========================================
# FIND TESTCASE FILES
# ==========================================

def find_testcases(repo_path):
    testcase_files = []

    for ext in SUPPORTED_EXTENSIONS:
        testcase_files.extend(repo_path.rglob(f"*{ext}"))

    return testcase_files

# ==========================================
# DISPLAY TESTCASE LIST
# ==========================================

def display_testcases(testcases):
    print("\nAvailable Testcases:\n")

    for idx, file in enumerate(testcases, start=1):
        print(f"{idx}. {file.relative_to(file.parents[1])}")

# ==========================================
# READ TESTCASE CONTENT
# ==========================================

def read_testcase(file_path):
    ext = file_path.suffix.lower()

    try:
        if ext == ".json":
            with open(file_path, "r") as f:
                return json.load(f)

        elif ext in [".yaml", ".yml"]:
            with open(file_path, "r") as f:
                return yaml.safe_load(f)

        else:
            with open(file_path, "r") as f:
                return f.read()

    except Exception as e:
        return f"[ERROR] Failed to read testcase:\n{e}"

# ==========================================
# MAIN PROGRAM
# ==========================================

def main_git():

    print("\n==== Dynamic Git Testcase Manager ====\n")

    git_url = input("Enter Git Repository URL:\n> ").strip()

    # Validate URL
    if not is_valid_git_url(git_url):
        print("\n[ERROR] Invalid or unsupported Git URL.")
        return

    # Clone or update repo
    repo_path = clone_or_update_repo(git_url)

    if not repo_path:
        return

    # Find testcase files
    testcases = find_testcases(repo_path)

    if not testcases:
        print("\n[INFO] No testcase files found.")
        return

    # Display testcases
    display_testcases(testcases)

    # Select testcase
    try:
        choice = int(input("\nSelect testcase number:\n> "))

        if choice < 1 or choice > len(testcases):
            print("[ERROR] Invalid selection.")
            return

    except ValueError:
        print("[ERROR] Please enter a valid number.")
        return

    selected_file = testcases[choice - 1]

    print(f"\n[INFO] Selected testcase:\n{selected_file}")

    # Read testcase
    content = read_testcase(selected_file)

    print("\n==== TESTCASE CONTENT ====\n")
    print(content)

# ==========================================
# RUN
# ==========================================

if __name__ == "__main_git__":
    main_git()
