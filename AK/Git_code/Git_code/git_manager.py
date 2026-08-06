import os
import sys
import json
import shutil
import subprocess
import logging
from tkinter import Tk, filedialog
class GitManager:

    def __init__(self, UDSApp):
        self.UDSApp = UDSApp
        self.repo_path = None
        
        #self.select_remote_branch()
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.repo_url = "git@bitbucket.org:mobase-rnd/dtp-can.git"
        #self.branch = "main"

        repo_name = os.path.basename(self.repo_url).replace(".git", "")

        #self.repo_path = os.path.join(self.base_dir,repo_name) 
        
        self.branch = self.select_remote_branch()
        self.repo_path = os.path.join(self.base_dir,"dtp-can")
        logging.info(f"Repo Path:  {self.repo_path}")
        logging.info(f"Branch: {self.branch}")
        logging.info(f"Branch:  {self.repo_url}")
        
        
    
    def list_remote_branches(self):
        print("Fetching latest branches...")

        # Fetch latest remote branches
        logging.info(f"Repo Path:  {self.repo_path}")
        subprocess.run(
            ["git", "fetch", "--all"],
            cwd=self.repo_url,
            check=True
        )

        # Get remote branches
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=self.repo_url,
            capture_output=True,
            text=True,
            check=True
        )

        branches = []

        for branch in result.stdout.splitlines():
            branch = branch.strip()

            # Ignore HEAD pointer
            if "->" in branch:
                continue

            # Remove 'origin/' prefix
            if branch.startswith("origin/"):
                branch = branch.replace("origin/", "", 1)

            branches.append(branch)
        return sorted(set(branches))

    def select_remote_branch(self):
            branches = self.list_remote_branches()
            if not branches:
                self.oled.display_centered_text("No branches")
                time.sleep(2)
                return None
            selected_index = self.UDSApp.select_from_list("Branches", branches)
            
            return branches[selected_index] if selected_index is not None else None
            
    def get_testcases(self):
        
        self.repo_path = os.path.join(self.base_dir, self.branch)
        files = []

        for root, dirs, filenames in os.walk(self.repo_path):
            for file in filenames:
                if file.endswith(".txt"):
                    files.append(os.path.join(root, file))
        return sorted(files)

    def get_configs(self):

        files = []

        for root, dirs, filenames in os.walk(self.repo_path):
            for file in filenames:
                if file.endswith(".json"):
                    files.append(os.path.join(root, file))

        return sorted(files)
    
        
    def clone_repository(self):
        if os.path.exists(self.repo_path):
            return
        subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                self.branch,
                self.repo_url,
                self.repo_path
            ],
            check=True
        )
        
    def pull_repository(self):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo_url,
                "pull",
                "origin",
                self.branch
            ],
            check=True
        )
        
    def checkout_branch(self, branch):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo_path,
                "checkout",
                "-B",
                self.branch,
                f"origin/{self.branch}"
            ],
            check=True
        )

        self.branch = branch    
    
    def copy_reports(self):
        source = os.path.join(self.base_dir,"output")
        destination = os.path.join(self.repo_path,"output")
        shutil.copytree(source,destination,dirs_exist_ok=True)
        
    def git_add(self):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo_path,
                "add",
                "."
            ],
            check=True
        )
    
    def git_commit(self):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo_url,
                "commit",
                "-m",
                "Updated Reports"
            ],
            check=False
        )
        
    
    def git_push(self):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo_url,
                "push",
                "origin",
                self.branch
            ],
            check=True
        )
