import sys
import os
import time
import logging
import subprocess
import shutil
import threading
import RPi.GPIO as GPIO
from drivers import git_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from drivers import oled_display, button_input, config_loader, uds_client, transfer_file, initialize_interfaces

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "uds_debug.log")

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler()
    ]
)

class UDSApp:
    def __init__(self):
        self.config = None
        self.oled = None
        self.buttons = None
        self.uds = None
        self.usb = None
        self.initialized_once=False
        self.btn_map = {}
        self.menu_combos = {}
        self.current_ssid = None
        self.wifi_connected = False
        self.stop_wifi_monitor = False
        self.wifi_monitor_thread = None
        self.last_wifi_status = True
        self.file_transfer_combos = {}
        self.initialize_dependencies()
        
    
    def git_setup(self):
        self.oled.display_centered_text("Checking\nRepository...")
        try:
            self.git.clone_repository()
            self.git.pull_repository()
            self.oled.display_centered_text("Repository\nUpdated")
            time.sleep(2)
        except Exception as e:
            logging.error(str(e))
            self.oled.display_centered_text("Git Error")
            time.sleep(2)
            raise
        testcase = self.select_testcase()
        config = self.select_config()
        self.copy_git_files(testcase)
        self.selected_testcase = testcase
        self.selected_config = config
        self.config = config_loader.load_config(config)
        
    def select_testcase(self):
        files = self.git.get_testcases()
        if not files:
            self.oled.display_centered_text("No Testcases")
            time.sleep(2)
            return None
        index = 0
        while True:
            filename = os.path.basename(files[index])
            self.oled.display_centered_text(f"Testcase\n\n{filename}")
            button = self.buttons.wait_for_press()
            if button == 0:
                index = (index - 1) % len(files)
            elif button == 1:
                index = (index + 1) % len(files)
            elif button == 2:
                return files[index]
            
    def select_config(self):
        files = self.git.get_configs()
        if not files:
            self.oled.display_centered_text("No Config Files")
            time.sleep(2)
            return None
        index = 0
        while True:
            filename = os.path.basename(files[index])
            self.oled.display_centered_text(f"Config\n\n{filename}")
            button = self.buttons.wait_for_press()
            if button == 0:
                index = (index - 1) % len(files)
            elif button == 1:
                index = (index + 1) % len(files)
            elif button == 2:
                return files[index]
    
    
    def copy_git_files(self, testcase):
        support_dir = os.path.join(BASE_DIR, "supportfiles")
        os.makedirs(support_dir, exist_ok=True)
        for file in os.listdir(support_dir):
            if file.endswith(".txt"):
                os.remove(os.path.join(support_dir, file))
        filename = os.path.basename(testcase)
        shutil.copy(
            testcase,
            os.path.join(support_dir, filename)
        )
        with open(os.path.join(BASE_DIR, "selected_testcase.txt"), "w") as f:
            f.write(filename)
    
        
    def check_can0_present(self):
        result = subprocess.run("ip link show can0", shell=True, stdout=subprocess.PIPE)
        return "can0" in result.stdout.decode()
        
    
    def bringup_can_interface(self):
        try:
            logging.info("Bringing up CAN interface can0...")
            subprocess.run(["sudo", "ip", "link", "set", "can0", "down"], check=True)
            subprocess.run(["sudo", "ip", "link", "set", "can0", "up","type", "can","bitrate", str(self.bitrate),"dbitrate", str(self.dbitrate),"restart-ms", str(self.restart_ms),"berr-reporting", "on","fd", "on"], check=True)
            subprocess.run(["sudo", "ifconfig", "can0", "up"], check=True)
            logging.info("CAN interface can0 successfully brought up.")
            
        except subprocess.CalledProcessError as e:
            logging.error(f"CAN bringup failed: {e}")
            if self.oled:
                self.oled.display_centered_text("CAN init failed")
            time.sleep(2)

    def initialize_dependencies(self):
        GPIO.cleanup()
        self.interface = initialize_interfaces.interface()
        self.interface.initialize()
        display_config = {
            "width": 128,
            "height": 64,
            "address": "0x3C"
        }
        self.oled = oled_display.OLEDDisplay(display_config)
        self.btn_map = {
            "first": 12,
            "second": 16,
            "enter": 20,
            "power": 21
        }
        self.buttons = button_input.ButtonInput(list(self.btn_map.values()))
        self.wifi_setup()
        self.start_wifi_monitor()
        self.git = git_manager.GitManager()
        self.git_setup()
        # -------------------------------------------------
        # Create UDS object so UDP server can be checked
        # -------------------------------------------------
        self.uds = uds_client.UDSClient(self.config)
        max_retries = 3
        udp_connected = False
        for retry in range(1, max_retries + 1):
            try:
                self.oled.display_centered_text(f"Checking\nUDP Server...\n\n{retry}/{max_retries}")
                logging.info(f"----------------------------------Checking UDP Server ({retry}/{max_retries})----------------------------------")
                if self.uds.check_udp_server():
                    udp_connected = True
                    self.oled.display_centered_text("UDP Server\nConnected")
                    logging.info("----------------------------------UDP Server Connected----------------------------------")
                    time.sleep(2)
                    break
                logging.warning(f"----------------------------------UDP Server Not Found ({retry}/{max_retries})----------------------------------")
            except Exception as e:
                logging.error(f"UDP Server check failed: {e}")
            if retry < max_retries:
                self.oled.display_centered_text(f"UDP Server\nNot Found\n\nRetry {retry}/{max_retries}")
                time.sleep(2)
        if not udp_connected:
            logging.warning("----------------------------------UDP Server Unavailable - Continuing Startup----------------------------------")
            self.oled.display_centered_text("UDP Server\nUnavailable\n\nContinuing...")
            time.sleep(3)
        self.uds.udp_server_available = udp_connected
        can_config = self.config.get("uds", {}).get("can", {})
        self.bitrate = can_config.get("bitrate", 500000)
        self.dbitrate = can_config.get("dbitrate", 2000000)
        self.restart_ms = can_config.get("restart_ms", 1000)
        if not self.initialized_once:
            logging.info("----------------------------------Welcome to Diagnostics-----------------------------------------------")
            
            time.sleep(2)
            self.initialized_once=True
            
        logging.info("----------------------------------Initializing-----------------------------------------------")
        
        
        self.btn_map = self.config["gpio"]["buttons"]
        self.BTN_FIRST = self.btn_map.get("first")
        self.BTN_SECOND = self.btn_map.get("second")
        self.BTN_ENTER = self.btn_map.get("enter")
        self.BTN_POWER = self.btn_map.get("power")
        
        self.menu_combos = self.config["menu_combinations"]
        self.file_transfer_combos = self.config["file_transfer_submenu_combinations"]
        

        time.sleep(1.5)
        logging.info("----------------------------------Waiting for CAN-----------------------------------------------")
        
        timeout_seconds = 60
        start_time = time.time()
        
        if can_config.get("bringup_on_startup", False):
            while time.time() - start_time < timeout_seconds:
                if not self.check_can0_present():
                    logging.warning("CAN0 not detected. Retrying...")
                    logging.info("----------------------------------Waiting for CAN0-----------------------------------------------")
                    time.sleep(1)
                    continue
        
                self.bringup_can_interface()
                time.sleep(1)
        
                try:
                    logging.info("Creating temporary UDS client...")
                    temp_uds = uds_client.UDSClient(self.config)
                    logging.info("Trying basic communication with ECU...")
                    success = temp_uds.try_basic_communication()
                    if success:
                        logging.info("UDS communication successful.")
                        logging.info("----------------------------------ECU Ready-----------------------------------------------")
                        break
                    else:
                        logging.warning("No response from ECU.")
                        logging.info("----------------------------------Waiting for ECU-----------------------------------------------")
                        self.oled.display_centered_text("Waiting for ECU...")
                except Exception as e:
                    logging.error("Exception during UDS handshake", exc_info=True)
                    self.oled.display_centered_text("ECU Comm Fail")
        
                time.sleep(2)
            else:
                logging.error("CAN or ECU did not respond within timeout.")
                
                self.oled.display_centered_text("CAN/ECU Timeout\nCheck Setup")
                logging.info("----------------------------------CAN/ECU Timeout Check SetupUp-----------------------------------------------")
                time.sleep(5)
                raise SystemExit("Initialization failed: CAN or ECU not responding.")
        else:
            logging.info("CAN bring-up skipped (bringup_on_startup = false)")
        
        #self.uds = uds_client.UDSClient(self.config)
        #self.usb = transfer_file.USBTransfer(self.oled)
        self.usb = transfer_file.USBTransfer(self.oled)
        

    def show_text(self, text):
        self.oled.clear()
        self.oled.display_text(text)

    def scan_wifi(self):
        try:
            result = subprocess.check_output(["nmcli", "-t", "-f", "SSID", "dev", "wifi"],text=True)
            networks = []
            for ssid in result.splitlines():
                ssid = ssid.strip()
                if ssid and ssid not in networks:
                    networks.append(ssid)
            return networks
        except Exception as e:
            logging.error(f"WiFi Scan Error: {e}")
            return []
    def connect_wifi(self, ssid, password):
        self.oled.display_centered_text(f"Connecting\n{ssid}")
        result = subprocess.run(
            [
                "nmcli",
                "--wait",
                "15",
                "device",
                "wifi",
                "connect",
                ssid,
                "password",
                password
            ],
            capture_output=True,
            text=True
        )

        logging.info(result.stdout)
        logging.error(result.stderr)

        return result.returncode == 0
    
    def enter_password_oled(self):
        chars = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
            "0123456789"
            "@._-!#$%&*+=<>"
        )

        password = ""
        index = 0

        while True:
            current_char = chars[index]

            self.oled.display_centered_text(
            f"Password:\n{password[-8:]}\n\n[{current_char}]"
            )

            button = self.buttons.wait_for_press()
            if button == 0:
                index = (index + 1) % len(chars)
            elif button == 1:
                index = (index - 1) % len(chars)
            elif button == 2:
                if current_char == "<":
                    password = password[:-1]
                elif current_char == ">":
                    return password
                else:
                    password += current_char
            elif button == 3:
                return password
    
    def wifi_setup(self):
        logging.info("------------- Wifi Setup -------------")
        wifi_connected = False
        self.oled.display_centered_text("Scanning\nWiFi...")
        networks = self.scan_wifi()
        if not networks:
            self.oled.display_centered_text("No WiFi\nFound")
            time.sleep(2)
            return False
        index = 0
        while True:
            ssid = networks[index]
            self.oled.display_centered_text(f"WiFi\n\n{ssid}")
            button = self.buttons.wait_for_press()
            # FIRST BUTTON -> Previous SSID
            if button == 0:
                index = (index - 1) % len(networks)
# SECOND BUTTON -> Next SSID
            elif button == 1:
                index = (index + 1) % len(networks)
# ENTER BUTTON
            elif button == 2:
                result = subprocess.run(
                    [
                        "nmcli",
                        "-t",
                        "-f",
                        "NAME",
                        "connection",
                        "show"
                    ],
                    capture_output=True,
                    text=True
                )

                saved_connections = result.stdout.splitlines()

                # ---------------------------------------------------
                # Saved connection
                # ---------------------------------------------------
                if ssid in saved_connections:
                    # Already connected
                    if self.is_connected(ssid):
                        self.current_ssid = ssid
                        self.wifi_connected = True
                        self.oled.set_wifi_status("W+")
                        self.oled.display_centered_text(f"Using\n{ssid}")
                        time.sleep(1)
                        return True
                    # Try saved password
                    success = self.try_saved_connection(ssid)
                    if success:
                        self.current_ssid = ssid
                        self.wifi_connected = True
                        self.oled.set_wifi_status("W+")
                        self.oled.display_centered_text(f"Connected\n{ssid}")
                        time.sleep(2)
                        return True
                    # Saved password failed
                    subprocess.run(
                        [
                            "nmcli",
                            "connection",
                            "delete",
                            ssid
                        ],
                        capture_output=True,
                        text=True
                    )
                    while True:
                        password = self.enter_password_oled()
                        success = self.connect_wifi(
                            ssid,
                            password
                        )
                        if success:
                            break
                        self.oled.display_centered_text("Wrong Password\nTry Again")
                        time.sleep(2)
                # ---------------------------------------------------
                # New WiFi
                #    ---------------------------------------------------
                else:
                    while True:
                        password = self.enter_password_oled()
                        success = self.connect_wifi(ssid,password)
                        if success:
                            break
                        self.oled.display_centered_text("Wrong Password\nTry Again")
                        time.sleep(2)
                if success:
                    wifi_connected = True
                    self.wifi_connected = True
                    self.current_ssid = ssid
                    self.oled.set_wifi_status("W+")
                    self.oled.display_centered_text(f"Connected\n{ssid}")
                    time.sleep(2)
                    return True
                # POWER BUTTON
            elif button == 3:
                if wifi_connected:
                    return True
                self.oled.display_centered_text("No WiFi\nConnected")
                time.sleep(2)
                    
    def is_connected(self, ssid):
        result = subprocess.run(
            [
                "nmcli",
                "-t",
                "-f",
                "ACTIVE,SSID",
                "device",
                "wifi"
            ],
            capture_output=True,
            text=True
        )
        for line in result.stdout.splitlines():
            if line == f"yes:{ssid}":
                return True
        return False
        
    def try_saved_connection(self, ssid):
        result = subprocess.run(
            [
                "nmcli",
                "connection",
                "up",
                ssid
            ],
            capture_output=True,
            text=True
        )

        return result.returncode == 0
    
    def start_wifi_monitor(self):
        self.stop_wifi_monitor = False
        self.wifi_monitor_thread = threading.Thread(
            target=self.monitor_wifi,
            daemon=True
        )
        self.wifi_monitor_thread.start()
        
    def reconnect_wifi(self):
        if not self.current_ssid:
            return False
        logging.info("Trying WiFi reconnect...")
        success = self.try_saved_connection(
            self.current_ssid
        )
        self.wifi_connected = success
        return success
    
    def monitor_wifi(self):
        while not self.stop_wifi_monitor:
            connected = False
            if self.current_ssid:
                connected = self.is_connected(self.current_ssid)
            if connected:
                self.oled.set_wifi_status("W+")
                if not self.last_wifi_status:
                    logging.info("WiFi Reconnected")
                    self.oled.display_centered_text("WiFi\nConnected")
                    time.sleep(2)
                self.last_wifi_status = True
            else:
                if self.last_wifi_status:
                    logging.warning("WiFi Lost")
                    self.oled.set_wifi_status("W~")
                    self.oled.display_centered_text("WiFi Lost\n\nReconnecting...")
                self.last_wifi_status = False
                success = self.reconnect_wifi()
                if success:
                    self.oled.set_wifi_status("W+")
                    self.oled.display_centered_text("WiFi\nConnected")
                    self.last_wifi_status = True
                    time.sleep(2)
                else:
                    self.oled.set_wifi_status("W-")

            time.sleep(10)

    def main_menu(self):
        while True:
            print("\nSelect an option:")
            print("1. Read ECU Info")
            print("2. Run Test Cases")
            print("3. Shut Down")
            print("4. Push to Bitbucket")

            self.oled.display_centered_text(
                "1 ECU info\n2 Run TestCases\n3 ShutDown\n4 Push to Bitbucket"
            )
            button = self.buttons.wait_for_press()
            if button == 0:
                selected_key = "1"
            elif button == 1:
                selected_key = "2"
            elif button == 2:
                selected_key = "3"
            elif button == 3:
                selected_key = "4"

            if selected_key == "1":
                selected_option = "ECU Information"
            elif selected_key == "2":
                selected_option = "Testcase Execution"
            elif selected_key == "3":
                selected_option = "ShutDown"  
            elif selected_key == "4":
                selected_option = "Push to Bitbucket"
            else:
                print("Invalid input. Try again.")
                continue

            if selected_option == "ECU Information":
                self.oled.display_centered_text("Run Test cases")
                logging.info("----------------------------------Read ECU Info-----------------------------------------------")
                time.sleep(1)
                self.uds.get_ecu_information(self.oled)
                logging.info("----------------------------------Done-----------------------------------------------")
                self.oled.display_centered_text("Done")
                time.sleep(2)
            elif selected_option == "Testcase Execution":
                logging.info("----------------------------------Run Test Cases-----------------------------------------------")
                self.uds.run_testcase(self.oled)	
                logging.info("----------------------------------Done-----------------------------------------------")
            elif selected_option == "ShutDown":
                logging.info("----------------------------------Shutting Down...-----------------------------------------------")
                os.system("sudo poweroff")	
            elif selected_option == "Push to Bitbucket":
                logging.info("Uploading...")
                self.oled.display_centered_text("Uploading\nReports to Bitbucket...")
                try:
                    self.git.copy_reports()
                    self.git.git_add()
                    self.git.git_commit()
                    self.git.git_push()
                    self.oled.display_centered_text("Upload\nComplete")
                except Exception as e:
                    logging.error(str(e))
                    self.oled.display_centered_text("Bitbucket Push\nFailed")
                time.sleep(2)
                #os._exit(0)
                    
                
    def file_transfer_menu(self):
        submenu_done = False

        while not submenu_done:
            self.show_text("- Copy  from USB\n- Transfer to USB")
            selected_sequence = []
            variable = 0

            while True:
                if GPIO.input(self.BTN_FIRST) == GPIO.LOW:
                    selected_sequence.append(self.BTN_FIRST)
                    variable = (variable * 10) + 1
                    self.show_text(str(variable))
                    time.sleep(0.3)

                if GPIO.input(self.BTN_SECOND) == GPIO.LOW:
                    selected_sequence.append(self.BTN_SECOND)
                    variable = (variable * 10) + 2
                    self.show_text(str(variable))
                    time.sleep(0.3)

                if GPIO.input(self.BTN_ENTER) == GPIO.LOW:
                    selected_sequence.append(self.BTN_ENTER)
                    key = str(tuple(selected_sequence))
                    logging.info(f"Captured submenu sequence: {selected_sequence}")
                    selected_option = self.file_transfer_combos.get(key, "Invalid Input")
                    time.sleep(0.5)

                    if selected_option == "Output -> USB":
                        self.oled.display_centered_text("Transferring to USB...")
                        time.sleep(1)
                        self.usb.transfer_files_to_usb()
                        self.oled.display_centered_text("Done")
                        time.sleep(2)
                        submenu_done = True
                        break

                    elif selected_option == "USB -> Raspberry Pi":
                        self.oled.display_centered_text("Copying from USB...")
                        time.sleep(1)
                        usb_found=self.usb.fetch_testcase_and_config_from_usb()
                        
                        if not usb_found:
                            submenu_done = True
                            break
                            

                        self.oled.display_centered_text("Done")  
                        time.sleep(2) 
                        self.initialize_dependencies()
                        time.sleep(2)
                        submenu_done = True
                        break

                    else:
                        self.oled.display_centered_text("Invalid Input")
                        time.sleep(1)
                        break

def main():
    app = UDSApp()
    app.main_menu()

if __name__ == "__main__":
    main()
