import os
import subprocess
import sys

LOCAL_DIR = "./input"


def get_repo_url():
    url = input("Enter Git repository URL: ").strip()
    if not url:
        print("Git URL cannot be empty ❌")
        sys.exit(1)
    return url


def setup_repo(repo_url):
    if not os.path.exists(LOCAL_DIR) or not os.listdir(LOCAL_DIR):
        print("Cloning repo...")
        subprocess.run(["git", "clone", repo_url, LOCAL_DIR], check=True)
    else:
        print("Pulling latest changes...")
        subprocess.run(["git", "-C", LOCAL_DIR, "pull"], check=True)


def get_files():
    files = [
        f for f in os.listdir(LOCAL_DIR)
        if os.path.isfile(os.path.join(LOCAL_DIR, f))
    ]
    return files


def select_file(files):
    print("\nAvailable files:\n")

    for i, file in enumerate(files):
        print(f"{i+1}. {file}")

    while True:
        try:
            choice = int(input("\nSelect file number: "))
            if 1 <= choice <= len(files):
                return files[choice - 1]
            else:
                print("Invalid choice ❌")
        except ValueError:
            print("Enter a valid number ❌")


def main_git():
    try:
        repo_url = get_repo_url()
        setup_repo(repo_url)
    except Exception as e:
        print(f"Git error: {e}")
        sys.exit(1)

    files = get_files()

    if not files:
        print("No files found ❌")
        sys.exit(1)

    selected = select_file(files)

    # 👉 Only print filename for shell usage
    print(selected)


if __name__ == "__main_git__":
    main_git()