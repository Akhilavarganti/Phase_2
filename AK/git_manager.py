import os

class GitManager:

    def __init__(self):
        self.repo_path = "/home/pi/Testhub"

    def get_testcases(self):
        files = []

        for root, dirs, filenames in os.walk(self.repo_path):
            for file in filenames:
                if file.endswith(".txt"):
                    files.append(
                        os.path.join(root, file)
                    )

        return sorted(files)

    def get_configs(self):
        files = []

        for root, dirs, filenames in os.walk(self.repo_path):
            for file in filenames:
                if file.endswith(".json"):
                    files.append(
                        os.path.join(root, file)
                    )

        return sorted(files)