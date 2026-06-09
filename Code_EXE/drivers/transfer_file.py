import os
import sys
import shutil
import time
import logging
from datetime import datetime

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class USBTransfer:
    def __init__(self, oled):
        self.oled = oled
        self.outputs_folder = os.path.join(BASE_DIR, "output")
        self.usb_root = "/media"
        logging.info("USBTransfer initialized")

    def show_progress_animation(self, base_msg, duration=3, interval=0.5):
        steps = int(duration / interval)
        for i in range(steps):
            dots = '.' * ((i % 3) + 1)
            self.oled.display_centered_text(f"{base_msg}{dots}")
            time.sleep(interval)

    def get_usb_mount_path(self):
        logging.info(f"Looking for USB under: {self.usb_root}")
        try:
            for user in os.listdir(self.usb_root):
                user_path = os.path.join(self.usb_root, user)
                if os.path.isdir(user_path):
                    for device in os.listdir(user_path):
                        mount_path = os.path.join(user_path, device)
                        if os.path.ismount(mount_path):
                            logging.info(f"USB mount found at: {mount_path}")
                            return mount_path
        except Exception as e:
            logging.error(f"Error while scanning USB: {e}")
        return None


    def fetch_testcase_and_config_from_usb(self):
        self.oled.display_centered_text("Searching for USB...")
        time.sleep(1)
        logging.info("Checking USB mount path...")
        
        usb_mount_path = self.get_usb_mount_path()
        if not usb_mount_path:
            self.oled.display_centered_text("No USB device found.")
            time.sleep(2)
            logging.warning("No USB mount path found.")
            return False
        
        try:
            logging.info(f"Scanning USB at: {usb_mount_path}")
            self.oled.display_centered_text("USB found.\nSearching files...")
            time.sleep(1)
        
            
            is_testcase_copied=False
            is_json_copied=False
            for root, dirs, files in os.walk(usb_mount_path):
                if "testcase.txt" in files:
                    testcase_src = os.path.join(root, "testcase.txt")
                    testcase_dst = os.path.join(BASE_DIR, "supportfiles", "testcase.txt")
                    shutil.copy(testcase_src, testcase_dst)
                    logging.info(f"Copied testcase.txt from {testcase_src}")
                    self.show_progress_animation("Copying testcase.txt", duration=3)
                    self.oled.display_centered_text(f"Copied testcase.txt")
                    time.sleep(2)
                    is_testcase_copied = True
        
                if "config.json" in files:
                    config_src = os.path.join(root, "config.json")
                    config_dst = os.path.join(BASE_DIR, "config.json")
                    shutil.copy(config_src, config_dst)
                    logging.info(f"Copied config.json from {config_src}")
                    self.show_progress_animation("Copying config.json", duration=3)
                    self.oled.display_centered_text(f"Copied config.json")
                    time.sleep(2)
                    is_json_copied = True
        
            if is_testcase_copied and is_json_copied :
                self.oled.display_centered_text("Files updated\nfrom USB.")
                time.sleep(2)
                return True
            else:
                self.oled.display_centered_text("Files not found\non USB.")
                time.sleep(2)
                return False
        
        except Exception as e:
            logging.exception("Error copying files from USB")
                    
                
            
    def transfer_files_to_usb(self):
        try:
            self.oled.display_centered_text("Searching for USB...")
            logging.info("Starting transfer...")
            time.sleep(1)

            usb_path = self.get_usb_mount_path()
            if not usb_path:
                self.oled.display_centered_text("No USB device found.")
                logging.warning("No USB device mounted")
                time.sleep(2)
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_folder = os.path.join(usb_path, f"UDS_Backup_{timestamp}")
            os.makedirs(backup_folder, exist_ok=True)
            logging.info(f"Backup folder created on USB: {backup_folder}")

            self.oled.display_centered_text("USB Found.\nCopying Data...")
            time.sleep(2)
            self.show_progress_animation("Transferring...", duration=3)

            destination = os.path.join(backup_folder, "Outputs")
            shutil.copytree(self.outputs_folder, destination)

            file_count = sum(len(files) for _, _, files in os.walk(destination))
            self.oled.display_centered_text(f"Transfer Done\n{file_count} files")
            logging.info(f"Transfer complete. Files copied: {file_count}")
            time.sleep(2)

        except Exception as e:
            self.oled.display_centered_text(f"Error")
            logging.error(f"Error during USB transfer: {e}")
            time.sleep(3)
