import json
import os

JOBS_FILE = "ecu_repo/jobs/jobs.json"

def load_testcases():
    with open(JOBS_FILE, "r") as f:
        data = json.load(f)
    return data.get("testcases", [])

def show_menu(testcases):
    print("\nAvailable Testcases:\n")
    for i, tc in enumerate(testcases):
        print(f"{i+1}. {tc}")

    choice = int(input("\nSelect testcase: ")) - 1
    return testcases[choice]

def save_selection(selected):
    with open(JOBS_FILE, "r+") as f:
        data = json.load(f)
        data["selected_testcase"] = selected
        f.seek(0)
        json.dump(data, f, indent=4)
        f.truncate()

if __name__ == "__main__":
    testcases = load_testcases()
    selected = show_menu(testcases)
    save_selection(selected)
    print(f"\nSelected: {selected}")
