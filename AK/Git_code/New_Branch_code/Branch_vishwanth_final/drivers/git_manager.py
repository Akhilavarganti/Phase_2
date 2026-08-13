import os
import sys
import json
import shutil
import subprocess
import logging
from tkinter import Tk, filedialog
class GitManager:

    def __init__(self, UDSApp, base_dir):
        self.UDSApp = UDSApp
        self.base_dir = base_dir
        self.repo_path = None
        self.branch = None
        self.current_run_reports = []
        self.output_snapshot = set()
        self.repo_url = "git@bitbucket.org:mobase-rnd/dtp-can.git"
        logging.info(f"Application Base Directory: {self.base_dir}")
        '''if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))'''
        #self.branch = "main"

        #repo_name = os.path.basename(self.repo_url).replace(".git", "")

        #self.repo_path = os.path.join(self.base_dir,repo_name) 
        self.branch = None
        self.repo_path = None
        logging.info(f"Repo Path:  {self.repo_path}")
        logging.info(f"Branch:  {self.repo_url}")
        
        
    
    def list_remote_branches(self):
        print("Fetching latest branches...")

        """# Fetch latest remote branches
        logging.info(f"Repo Path:  {self.repo_path}")
        subprocess.run(
            ["git", "fetch", "--all"],
            cwd=self.repo_path,
            check=True
        )"""

        # Get remote branches
        #fetch list without cloning
        result = subprocess.run(
            ["git", "ls-remote", "--heads",
            self.repo_url],
            capture_output=True,
            text=True,
            check=True
        )

        branches = []

        for line in result.stdout.splitlines():
            if not line.strip():
                continue
                
            ref = line.split("\t")[1]
            branch = ref.replace("refs/heads/", "")
            branches.append(branch)
            
        return sorted(set(branches))
    def get_employee_ids(self):
        branches = self.list_remote_branches()
        employees = []
        for branch in branches:
            parts = branch.split("/")
            if len(parts) < 5:
                continue
            employee = parts[0]
            if employee not in employees:
                employees.append(employee)
        return sorted(employees)
    
    def get_variants(self, employee):
        branches = self.list_remote_branches()
        variants = []
        for branch in branches:
            parts = branch.split("/")
            if len(parts) < 5:
                continue
            if parts[0] == employee:
                variant = parts[1]
                if variant not in variants:
                    variants.append(variant)
        return sorted(variants)
    
    def get_types(self, employee, variant):
        branches = self.list_remote_branches()
        types = []
        for branch in branches:
            parts = branch.split("/")
            if len(parts) < 5:
                continue
            if (
                parts[0] == employee
                and parts[1] == variant
            ):
                test_type = parts[2]
                if test_type not in types:
                    types.append(test_type)
        return sorted(types)
    
    def get_stages(self, employee, variant, test_type):
        branches = self.list_remote_branches()
        stages = []
        for branch in branches:
            parts = branch.split("/")
            if len(parts) < 5:
                continue
            if (
                parts[0] == employee
                and parts[1] == variant
                and parts[2] == test_type
            ):
                stage = parts[3]
                if stage not in stages:
                    stages.append(stage)
        return sorted(stages)
    
    def get_matching_branch(
        self,
        employee,
        variant,
        test_type,
        stage,
        date):
        branches = self.list_remote_branches()
        for branch in branches:
            parts = branch.split("/")
            if len(parts) < 5:
                continue
            if (
                parts[0] == employee
                and parts[1] == variant
                and parts[2] == test_type
                and parts[3] == stage
                and parts[4] == date
            ):
                logging.info(f"Matched Branch: {branch}")
                return branch
        raise Exception("Matching branch not found")

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
    
        
    def clone_repository(self, branch):
        self.branch = branch
        safe_branch_name = branch.replace("/", "_")
        self.repo_path = os.path.join(
            self.base_dir,
            safe_branch_name
        )
        logging.info(f"Selected Branch: {self.branch}")
        logging.info(f"Repository Path: {self.repo_path}")
        if os.path.exists(self.repo_path):
            logging.info("Repository already exists.")
            return
        subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                branch,
                self.repo_url,
                self.repo_path
            ],
            check=True
        )
        logging.info(f"Repository cloned successfully: {branch}")
        
    def pull_repository(self):
        if self.branch is None:
            raise Exception("Branch not selected")
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
        
    '''def checkout_branch(self, new_branch):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo_path,
                "checkout",
                new_branch,
                f"origin/{self.branch}"
            ],
            check=True
        )
        self.branch = new_branch'''   
    
    def copy_reports(self):

        source_root = os.path.join(self.base_dir,"output")
        destination_root = os.path.join(self.repo_path,"output")
        if not self.current_run_reports:
            raise Exception("No new reports generated in current run")
        os.makedirs(destination_root,exist_ok=True)
        copied_count = 0
        for relative_path in self.current_run_reports:
            source_file = os.path.join(source_root,relative_path)
            destination_file = os.path.join(destination_root,relative_path)
            if not os.path.exists(source_file):
                logging.warning(f"Report file missing: {source_file}")
                continue
            destination_dir = os.path.dirname(destination_file)
            os.makedirs(destination_dir,exist_ok=True)
            shutil.copy2(source_file,destination_file)
            logging.info(f"Copied report: {relative_path}")
            copied_count += 1
        if copied_count == 0:
            raise Exception("No report files were copied")
        logging.info(f"{copied_count} current-run report files copied.")
        
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
                "-u",
                "origin",
                self.branch
            ],
            check=True
        )
    
    def get_testcases_and_configs(self):

        testcases = []
        configs = []
        for root, dirs, files in os.walk(self.repo_path):
            if ".git" in dirs:
                dirs.remove(".git")
            for file in files:
                full_path = os.path.join(root,file)
                if file.lower().endswith(".txt"):
                    testcases.append(full_path)
                elif (file.lower().endswith(".json") and file.lower() != "git_credentials.json"):
                    configs.append(full_path)
        testcases = sorted(testcases)
        configs = sorted(configs)
        if not testcases:
            raise Exception("No testcase files found")
        if not configs:
            raise Exception("No config files found")
        logging.info("Testcases found: %s",testcases)
        logging.info("Configs found: %s",configs)
        return testcases, configs
        
    
    def get_dates(self, employee, variant, test_type, stage):
        branches = self.list_remote_branches()
        dates = []
        for branch in branches:
            parts = branch.split("/")
            if len(parts) < 5:
                continue
            if (
                parts[0] == employee
                and parts[1] == variant
                and parts[2] == test_type
                and parts[3] == stage
            ):
                date = parts[4]
                if date not in dates:
                    dates.append(date)
        return sorted(dates)
    
    
    
    
    def start_report_tracking(self):
        output_dir = os.path.join(
            self.base_dir,
            "output"
        )
        os.makedirs(
            output_dir,
            exist_ok=True
        )
        self.output_snapshot = set()
        for root, dirs, files in os.walk(output_dir):
            for filename in files:
                full_path = os.path.join(
                    root,
                    filename
                )
                relative_path = os.path.relpath(
                    full_path,
                    output_dir
                )
                self.output_snapshot.add(
                    relative_path
                )
        self.current_run_reports = []
        logging.info(
            f"Report tracking started. "
            f"Existing files: {len(self.output_snapshot)}"
        )
        
        
    def finish_report_tracking(self):
        output_dir = os.path.join(
            self.base_dir,
            "output"
        )
        current_files = set()
        for root, dirs, files in os.walk(output_dir):
            for filename in files:
                full_path = os.path.join(
                    root,
                    filename
                )
                relative_path = os.path.relpath(
                    full_path,
                    output_dir
                )
                current_files.add(
                    relative_path
                )
        new_files = (
            current_files
            - self.output_snapshot
        )
        self.current_run_reports = sorted(
            new_files
        )
        logging.info(
            "Current run reports: %s",
            self.current_run_reports
        )
        return self.current_run_reports