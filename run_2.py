import os

TESTCASE_DIR = "ecu_repo/input"

if not os.path.exists(TESTCASE_DIR):
    print("❌ Folder not found:", TESTCASE_DIR)
    exit()

# 👇 Change here (.txt instead of .json)
files = [f for f in os.listdir(TESTCASE_DIR) if f.endswith(".txt")]

if not files:
    print("❌ No .txt testcases found")
    exit()

print("\nAvailable Testcases:\n")

for i, file in enumerate(files, 1):
    print(f"{i}. {file}")

try:
    choice = int(input("\nEnter testcase number: "))
    selected = files[choice - 1]
except:
    print("❌ Invalid selection")
    exit()

print(f"\nSelected: {selected}")

with open("selected_testcase.txt", "w") as f:
    f.write(selected)
