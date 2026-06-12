import sys
import os
import time
import logging
import subprocess
import RPi.GPIO as GPIO

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from drivers import oled_display, button_input, config_loader, uds_client, transfer_file

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
        self.file_transfer_combos = {}
        self.initialize_dependencies()

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

    #def show_status(self, text):
    #    logging.info(f"----------------------------------{text}-----------------------------------------------")
    #    if self.oled:
    #        self.oled.display_centered_text(text)
    
    def initialize_dependencies(self):
        GPIO.cleanup()
        self.config = config_loader.load_config()
        can_config = self.config.get("uds", {}).get("can", {})
        
        self.bitrate = can_config.get("bitrate", 500000)
        self.dbitrate = can_config.get("dbitrate", 2000000)
        self.restart_ms = can_config.get("restart_ms", 1000)
        self.oled = oled_display.OLEDDisplay(self.config["display"])
        
        if not self.initialized_once:
            
            #self.show_status("Welcome to\nDiagnostics")
            logging.info("----------------------------------Welcome to Diagnostics-----------------------------------------------")
            
            time.sleep(2)
            self.initialized_once=True
            
        #self.show_status("Initializing")
        logging.info("----------------------------------Initializing-----------------------------------------------")
        
        self.btn_map = self.config["gpio"]["buttons"]
        self.BTN_FIRST = self.btn_map.get("first")
        self.BTN_SECOND = self.btn_map.get("second")
        self.BTN_ENTER = self.btn_map.get("enter")
        self.BTN_POWER = self.btn_map.get("power")
        
        self.menu_combos = self.config["menu_combinations"]
        self.file_transfer_combos = self.config["file_transfer_submenu_combinations"]
        
        self.buttons = button_input.ButtonInput(list(self.btn_map.values()))
        self.wifi_setup()
        time.sleep(1.5)
        self.show_status("Waiting for CAN")
        logging.info("----------------------------------Waiting for CAN-----------------------------------------------")
        
        timeout_seconds = 60
        start_time = time.time()
        
        if can_config.get("bringup_on_startup", False):
            while time.time() - start_time < timeout_seconds:
                if not self.check_can0_present():
                    logging.warning("CAN0 not detected. Retrying...")
                    #self.show_status("Waiting for can0")
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
                        #self.show_status("ECU ready")
                        logging.info("----------------------------------ECU Ready-----------------------------------------------")
                        break
                    else:
                        logging.warning("No response from ECU.")
                        #self.show_status("Waitng for ECU")
                        logging.info("----------------------------------Waiting for ECU-----------------------------------------------")
                        self.oled.display_centered_text("Waiting for ECU...")
                except Exception as e:
                    logging.error("Exception during UDS handshake", exc_info=True)
                    self.oled.display_centered_text("ECU Comm Fail")
                    self.show_status("ECU comm failed")

        
                time.sleep(2)
            else:
                logging.error("CAN or ECU did not respond within timeout.")
                
                self.oled.display_centered_text("CAN/ECU Timeout\nCheck Setup")
                logging.info("----------------------------------CAN/ECU Timeout Check SetupUp-----------------------------------------------")
                time.sleep(5)
                raise SystemExit("Initialization failed: CAN or ECU not responding.")
        else:
            logging.info("CAN bring-up skipped (bringup_on_startup = false)")
        
        self.uds = uds_client.UDSClient(self.config)
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
        try:
            self.oled.display_centered_text(f"Connecting...\n{ssid}")
            result = subprocess.run(
                [
                    "nmcli",
                    "dev",
                    "wifi",
                    "connect",
                    ssid,
                    "password",
                    password
                ],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            logging.error(f"WiFi Connection Error: {e}")
            return False
    
    def enter_password_oled(self):
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@._-!"
        password = ""
        index = 0
        while True:
            current_char = chars[index]
            self.oled.display_centered_text(
                f"Pass:\n{password[-8:]}\n[{current_char}]"
            )
            button = self.buttons.wait_for_press()
            # Button 1 = Previous Character
            if button == 0:
                index = (index - 1) % len(chars)
                # Button 2 = Next Character
            elif button == 1:
                index = (index + 1) % len(chars)
                # Button 3 = Add Character
            elif button == 2:
                password += current_char
                #Button 4 = Finish Password Entry
            elif button == 3:
                return password
    
    def wifi_setup(self):
        logging.info("-------------Wifi Setup------------")
        wifi_connected = False
        self.oled.display_centered_text("Scanning\nWiFi...")
        networks = self.scan_wifi()
        if not networks:
            self.oled.display_centered_text("No WiFi\nFound")
            time.sleep(2)
            return True
        index = 0
        while True:
            ssid = networks[index]
            self.oled.display_centered_text(f"WiFi\n\n{ssid}")
            button = self.buttons.wait_for_press()
            # FIRST button (GPIO12) -> UP
            if button == 0:
                index -= 1
                if index < 0:
                    index = len(networks) - 1
            # SECOND button (GPIO16) -> DOWN
            elif button == 1:
                index += 1
                if index >= len(networks):
                    index = 0
            # ENTER button (GPIO20)
            elif button == 2:
                result = subprocess.run(
                    ["nmcli","-t","-f","NAME","connection","show"],
                    capture_output=True,
                    text=True
                )
                saved_connections = result.stdout.splitlines()
                if ssid in saved_connections:
                    self.oled.display_centered_text(
                        f"connecting\n{ssid}"
                    )
                    connect_result = subprocess.run(
                        ["nmcli","connection","up",ssid],
                        capture_output=True,
                        text=True
                    )
                    success = connect_result.returncode == 0
                    if success:
                        wifi_connected = True
                        self.oled.display_centered_text(
                            f"Connected\n{ssid}\nPress OK"
                        )
                        time.sleep(2)
                else:
                    self.oled.display_centered_text(
                        "1=Keyboard\n2=OLED"
                    )
                    print("Keyboard 1 = Keyboard Entry")
                    print("Keyboard 2 = OLED entry")
                    print("Button 1 = Keyboard entry")
                    print("Button 2 = OLED entry")
                    while True : 
                        button = self.buttons.wait_for_press()
                        if button == 0:
                            method = "1"
                            break
                        
                        elif button == 1:
                            method = "2"
                            break
                    
                    if method == "1":
                        password = input(
                            f"Enter Password for {ssid} : "
                        )
                    else:
                        password = self.enter_password_oled()
                    success = self.connect_wifi(
                        ssid,
                        password
                    ) 
                    if success:
                        wifi_connected = True
                        self.oled.display_centered_text(
                            f"Connected\n{ssid}\nPress OK"
                        )
                        time.sleep(2)
                    else:
                        self.oled.display_centered_text(
                            "Connection\nFailed"
                        )
                        time.sleep(2)
                # POWER button (GPIO21)
            elif button == 3:
                if wifi_connected:
                    self.oled.display_centered_text(
                        f"Using\n{ssid}"
                    )
                    time.sleep(1)
                    return True
                else:
                    self.oled.display_centered_text(
                        "No Wifi\nConnected"
                    )
                    time.sleep(2)
                    


    def main_menu(self):
        while True:
            print("\nSelect an option:")
            print("1. Read ECU Info")
            print("2. Run Test Cases")
            print("3. Shut Down")
            print("4. Exit app")
            self.oled.display_centered_text(
            "1 ECU info\n2 Run TestCases\n3 ShutDown\n4 Exit"
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
            else:
                selected_key = input("Enter your choice : ").strip()

            if selected_key == "1":
                selected_option = "ECU Information"
            elif selected_key == "2":
                selected_option = "Testcase Execution"
            elif selected_key == "3":
                selected_option = "ShutDown"  
            elif selected_key == "4":
                selected_option = "Return to script"
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
            elif selected_option == "Return to script":
                logging.info("----------------------------------Return to script...-----------------------------------------------")
                os._exit(0)	
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