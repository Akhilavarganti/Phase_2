import os
import sys
import json
import shutil
import subprocess

class GitManager:

    def __init__(self):

        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.repo_url = "git@bitbucket.org:mobase-rnd/dtp-can.git"
        #self.branch = "main"

        repo_name = os.path.basename(self.repo_url).replace(".git", "")

        self.repo_path = os.path.join(self.base_dir,repo_name)

        self.repo_path = os.path.join(self.base_dir, branch)
        branch = self.select_remote_branch()
        if branch: 
             self.git.checkout_branch(branch)
    def run_command(command, cwd=None):
        #"""Run a shell command and return its output."""
        result = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        text=True
        )
        #if result.returncode != 0:
        #raise Exception(result.stderr.strip())

        return result.stdout.strip()    

    def list_remote_branches(repo_path):
        print("Fetching latest branches...")

        # Fetch latest remote branches
        subprocess.run(
            ["git", "fetch", "--all"],
            cwd=repo_path,
            check=True
        )

        # Get remote branches
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )

        branch = []

        for line in result.stdout.splitlines():
            branch = line.strip()

            # Ignore HEAD pointer
            if "->" in branch:
                continue

            # Remove 'origin/' prefix
            if branch.startswith("origin/"):
                branch = branch.replace("origin/", "", 1)

            branch.append(branch)
        return sorted(set(branch))

    def select_remote_branch(self):
            branch = self.git.list_remote_branches()
            if not branch:
                self.oled.display_centered_text("No branches")
                time.sleep(2)
                return None
            selected_index = self.select_from_list("Branches", branch)
            
            return branch[selected_index] if selected_index is not None else None
            
    def get_testcases(self):
        
        self.repo_path = os.path.join(self.base_dir, branch_name)
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
                self.repo_path,
                "pull",
                "origin",
                self.branch
            ],
            check=True
        )
    
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
                self.repo_path,
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
                self.repo_path,
                "push",
                "origin",
                self.branch
            ],
            check=True
        )

        subprocess.run(
            [
                "git",
                "-C",
                self.repo_path,
                "push",
                "origin",
                self.branch
            ],
            check=True
        )
