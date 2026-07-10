import can
import socket
import shutil
import os
import sys
import isotp
import time
import logging
from datetime import datetime
from udsoncan.client import Client
from udsoncan.connections import PythonIsoTpConnection
from udsoncan.configs import default_client_config
from drivers.Parse_handler import load_testcases
from drivers.can_logger import CANLogger
from udsoncan import AsciiCodec
from drivers.report_generator import generate_report
from udsoncan.services import WriteDataByIdentifier

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(os.path.join(BASE_DIR, "output", "can_logs"), exist_ok=True)

os.makedirs(os.path.join(BASE_DIR, "output", "html_reports"), exist_ok=True)

os.makedirs(os.path.join(BASE_DIR, "output", "logs"), exist_ok=True)

os.makedirs(os.path.join(BASE_DIR, "supportfiles"), exist_ok=True)


class SafeAsciiCodec(AsciiCodec):
    def decode(self, data):
        try:
            return data.decode("ascii")
        except UnicodeDecodeError:
            return data.hex()


class UDSClient:
    def __init__(self, config):
        self.config = config
        can_cfg = config["uds"]["can"]
        isotp_cfg = config["uds"]["isotp"]
        timing_cfg = config["uds"]["timing"]
        self.uds_config = config["uds"]
        
        self.target_ecu = config["uds"].get("target_ecu", "Unknown ECU")
        self.context = {}
        self.last_response = None
        self.last_request = None
        
        self.udp_ip_ = config["uds"]["udp_server"]["ip"]
        self.udp_port_ = config["uds"]["udp_server"]["port"]
        self.expected_key_length_ = config["uds"]["udp_server"]["expected_key_length"]
        self.udp_server_available = True

        self.info_dids = self.uds_config.get("ecu_information_dids", {})
        self.decode_dids = self.uds_config.get("decoding_dids", {})
        self.write_data_dict = self.uds_config.get("write_data", {})
        self.step_delays = self.uds_config.get("delays", {})
        self.default_delay = self.step_delays.get("default", 0.5)

        self.client_config = default_client_config.copy()
        self.client_config["p2_timeout"] = timing_cfg["p2_client"] / 1000.0
        self.client_config["p2_star_timeout"] = (
            timing_cfg["p2_extended_client"] / 1000.0
        )
        self.client_config["s3_client_timeout"] = timing_cfg["s3_client"] / 1000.0
        self.client_config["exception_on_negative_response"] = False
        self.client_config["exception_on_unexpected_response"] = False
        self.client_config["exception_on_invalid_response"] = False
        self.client_config["use_server_timing"] = False

        self.client_config["data_identifiers"] = {
            int(did_str, 16): SafeAsciiCodec(length)
            for did_str, length in self.decode_dids.items()
        }
        self.client_config["write_data"] = {
            int(did_str, 16): data_str
            for did_str, data_str in self.write_data_dict.items()
        }

        addr_modes_cfg = self.uds_config["addressing_modes"]
        self.physical_conn = self._create_connection(
            addr_modes_cfg.get("physical"), can_cfg, isotp_cfg, "physical"
        )
        self.functional_conn = self._create_connection(
            addr_modes_cfg.get("functional"), can_cfg, isotp_cfg, "functional"
        )

        self.active_conn = self.physical_conn
        self.active_mode = "physical"

        self.allowed_ids = list(
            {
                int(addr_modes_cfg.get("physical", {}).get("tx_id", "0"), 16),
                int(addr_modes_cfg.get("physical", {}).get("rx_id", "0"), 16),
                int(addr_modes_cfg.get("functional", {}).get("tx_id", "0"), 16),
                int(addr_modes_cfg.get("functional", {}).get("rx_id", "0"), 16),
            }
        )

        self.allowed_tx_ids = [
            int(addr_modes_cfg.get("physical", {}).get("tx_id", "0"), 16),
            int(addr_modes_cfg.get("functional", {}).get("tx_id", "0"), 16),
        ]

        self.allowed_rx_ids = [
            int(addr_modes_cfg.get("physical", {}).get("rx_id", "0"), 16),
            int(addr_modes_cfg.get("functional", {}).get("rx_id", "0"), 16),
        ]

        if getattr(sys, "frozen", False):
            self.project_root = os.path.dirname(sys.executable)
        else:
            self.project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..")
            )
        filters = self.get_can_filters()
        log_dir = os.path.join(self.project_root, "output", "can_logs")
        self.can_logger = CANLogger(
            channel=can_cfg["channel"],
            interface=can_cfg["interface"],
            log_dir=log_dir,
            filters=filters,
        )
    def check_udp_server(self):
        test_seed = "01020304"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        try:
            logging.info("Checking UDP Seed-Key server...")
            sock.sendto(
                test_seed.encode(),
                (self.udp_ip_, self.udp_port_)
            )
            key, _ = sock.recvfrom(1024)
            if key:
                logging.info(f"UDP Server Connected. Key received: {key.hex() if isinstance(key, bytes) else key}")
                return True
            logging.warning("UDP Server returned empty response.")
            return False
        except socket.timeout:
            logging.error("UDP Server Timeout")
            return False
        except Exception as e:
            logging.error(f"UDP Server Error: {e}")
            return False
        finally:
            sock.close()

    def get_can_filters(self):
        filters_enabled = self.uds_config.get("logging", {}).get("filters", False)

        if not filters_enabled:
            logging.info("CANLogger: Logging ALL CAN messages (no filters)")
            return None

        addr_modes_cfg = self.uds_config["addressing_modes"]
        tx_id_phys = int(addr_modes_cfg.get("physical", {}).get("tx_id", "0"), 16)
        rx_id_phys = int(addr_modes_cfg.get("physical", {}).get("rx_id", "0"), 16)

        tx_id_func = int(addr_modes_cfg.get("functional", {}).get("tx_id", "0"), 16)
        rx_id_func = int(addr_modes_cfg.get("functional", {}).get("rx_id", "0"), 16)

        logging.info("CANLogger: Logging only UDS traffic (tx/rx physical+functional)")
        return [
            {"can_id": tx_id_phys, "can_mask": 0x7FF, "extended": False},
            {"can_id": rx_id_phys, "can_mask": 0x7FF, "extended": False},
            {"can_id": tx_id_func, "can_mask": 0x7FF, "extended": False},
            {"can_id": rx_id_func, "can_mask": 0x7FF, "extended": False},
        ]

    def _create_connection(self, addr_cfg, can_cfg, isotp_cfg, mode_name):
        if not addr_cfg:
            print(f"No config found for {mode_name} addressing, skipping.")
            return None

        tx_id = int(addr_cfg["tx_id"], 16)
        rx_id = int(addr_cfg["rx_id"], 16)
        is_extended = addr_cfg.get("is_extended", False)

        address = isotp.Address(
            addressing_mode=(
                isotp.AddressingMode.Normal_29bits
                if is_extended
                else isotp.AddressingMode.Normal_11bits
            ),
            txid=tx_id,
            rxid=rx_id,
        )

        rx_mask = 0x1FFFFFFF if is_extended else 0x7FF
        bus = can.interface.Bus(
            channel=can_cfg["channel"],
            bustype=can_cfg["interface"],
            fd=can_cfg.get("can_fd", True),
            can_filters=[
                {"can_id": rx_id, "can_mask": rx_mask, "extended": is_extended}
            ],
        )

        stack = isotp.CanStack(bus=bus, address=address, params=isotp_cfg)
        conn = PythonIsoTpConnection(stack)

        return {
            "conn": conn,
            "client_config": self.client_config,
            "mode_name": mode_name,
        }

    def switch_mode(self, mode):
        mode = mode.lower()
        if mode == "physical" and self.physical_conn is not None:
            self.active_conn = self.physical_conn
            self.active_mode = "physical"
        elif mode == "functional" and self.functional_conn is not None:
            self.active_conn = self.functional_conn
            self.active_mode = "functional"
        else:
            raise ValueError(f"Unsupported or unconfigured addressing mode: {mode}")

    def check_disk_space(self, min_required_mb=50):
        total, used, free = shutil.disk_usage("/")
        free_mb = free // (1024 * 1024)  # Convert to MB
        return (free_mb >= min_required_mb, free_mb)

    #def start_logging(self, log_name_suffix=""):
    #   timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #    filename = f"CANLog_{log_name_suffix}_{timestamp}.asc"
    #    self.can_logger.start(filename=filename)
    def start_logging(self, filename):
        self.can_logger.start(filename=filename)

    def stop_logging(self):
        self.can_logger.stop()

    def get_testcase_file_path(self):
         file_path = os.path.join(BASE_DIR,'supportfiles')
         
         for file in os.listdir(file_path):
             if file.endswith('.txt'):
                 return os.path.join(file_path, file)
         if not os.path.exists(file_path):
              raise FileNotFoundError(f"Testcase file not found: {file_path}")
         return file_path
            

    def check_memory(self, oled):
        min_required = 50
        enough_space, free_mb = self.check_disk_space(min_required_mb=min_required)
        if not enough_space:
            warning_msg = (
                f"Low Storage!\nOnly {free_mb}MB left.\nNeed {min_required}MB."
            )
            oled.display_centered_text(warning_msg)
            logging.warning(warning_msg)
            time.sleep(4)
            return False

        # oled.display_centered_text(f"Storage OK\nFree: {free_mb} MB")
        logging.info(
            f"----------------------------------Storage OK Free: {free_mb} MB-----------------------------------------------"
        )
        time.sleep(2)
        return True

    def try_basic_communication(self):
        try:
            with Client(
                self.active_conn["conn"], request_timeout=2, config=self.client_config
            ) as client:
                response = client.tester_present()
                return response.positive
        except Exception as e:
            logging.warning(f"Tester Present failed: {e}")
            return False

    def verify_response(self, raw_payload, expected_bytes, tc_id, step_desc):
        # sourcery skip: low-code-quality, merge-else-if-into-elif, swap-if-else-branches
        status = "Fail"
        failure_reason = "-"

        try:
            expected_first_byte = expected_bytes[0]
            actual_first_byte = raw_payload[0]

            # --- Negative response expected ---
            if expected_first_byte == 0x7F:
                if actual_first_byte == 0x7F:
                    nrc_code = raw_payload[2] if len(raw_payload) >= 3 else None

                    if len(expected_bytes) == 1:
                        # User gave only 0x7F → accept any NRC
                        status = "Pass"
                        logging.info(
                            f"{tc_id} {step_desc} -> PASS (any NRC accepted because only 0x7F given)"
                        )
                    elif len(expected_bytes) == 3:
                        # User gave full expected negative response → check
                        if nrc_code == expected_bytes[-1]:
                            status = "Pass"
                            logging.info(
                                f"-----------------------------------------------{tc_id} {step_desc} -> PASS-----------------------------------------------"
                            )
                        else:
                            failure_reason = f"Expected NRC {hex(expected_bytes[-1])}, got {hex(nrc_code) if nrc_code is not None else 'Unknown'}"
                            logging.warning(
                                f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                            )
                    else:
                        failure_reason = f"Malformed expected bytes for negative response: {expected_bytes}"
                        logging.error(
                            f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                        )
                else:
                    failure_reason = f"Expected Negative Response (0x7F), but got Positive Response: {raw_payload}"
                    logging.warning(
                        f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                    )

            # --- Positive response expected ---
            else:
                if actual_first_byte != 0x7F:
                    # check first N bytes
                    if raw_payload[: len(expected_bytes)] == expected_bytes:
                        status = "Pass"
                        logging.info(
                            f"----------------------------------{tc_id} {step_desc} -> PASS-----------------------------------------------"
                        )

                    else:
                        failure_reason = f"Expected {expected_bytes}, got {raw_payload[:len(expected_bytes)]}"
                        logging.warning(
                            f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                        )
                else:
                    nrc_code = raw_payload[2] if len(raw_payload) >= 3 else None
                    failure_reason = f"Expected Positive Response, but got NRC: {hex(nrc_code) if nrc_code is not None else 'Unknown'}"
                    logging.warning(
                        f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                    )

        except Exception as e:
            failure_reason = str(e)
            logging.error(
                f"-----------------------------------------------{tc_id} {step_desc} -> EXCEPTION - {failure_reason}-----------------------------------------------"
            )

        return status, failure_reason

    def get_ecu_information(self, oled=None, logging_enable=True):
        # sourcery skip: do-not-use-bare-except
        testcase_file_path = self.get_testcase_file_path()
        base_name = os.path.splitext(
            os.path.basename(testcase_file_path)
        )[0]
        

        ecu_info = {}
        session_default = int(self.uds_config["default_session"], 16)
        session_extended = int(self.uds_config["extended_session"], 16)

        grouped_cases = load_testcases(testcase_file_path)
        time.sleep(0.5)

        def normalize_hex_string(val):
            return val.lower().replace("0x", "").strip()

        with Client(
            self.active_conn["conn"], request_timeout=2, config=self.client_config
        ) as client:
            try:
                client.change_session(session_default)
                time.sleep(0.2)
                client.change_session(session_extended)
                time.sleep(0.2)

            except Exception as e:
                if oled:
                    oled.display_centered_text(f"Session Error:\n{str(e)}")
                logging.error(f"Session change failed: {e}")
                return

            for tc_id, steps in grouped_cases.items():
                if not tc_id.startswith("ECU_INFO"):
                    continue

                logging.info(f"[ECU Info] Processing {tc_id}")

                for step in steps:
                    logging.debug(f"[ECU Info] Step={step}")

                    try:
                        tc_id, step_desc, service, subfunc, expected, *rest = step

                        service_clean = normalize_hex_string(service)
                        subfunc_clean = normalize_hex_string(subfunc)

                        try:
                            service_int = int(service_clean, 16)
                            did = int(subfunc_clean, 16)
                        except ValueError as ve:
                            logging.error(
                                f"[ECU Info] Invalid service or subfunc '{subfunc}' in {tc_id} step '{step_desc}': {ve}"
                            )
                            continue

                        # RAW request
                        if service_int == 0x22:  # ReadDataByIdentifier
                            did_hi = (did >> 8) & 0xFF
                            did_lo = did & 0xFF
                            raw_request = bytes([0x22, did_hi, did_lo])
                        else:
                            raw_request = bytes([service_int, did])

                        logging.info(
                            f"[ECU Info] Sending raw request: {raw_request.hex()}"
                        )
                        
                        self.last_request = raw_request
                        client.conn.send(raw_request)
                        response = client.conn.wait_frame(timeout=2)

                        raw_payload = list(response)
                        logging.debug(f"[ECU Info] Received raw payload: {raw_payload}")

                        # Validate response
                        if service_int == 0x22:
                            if raw_payload[0] != 0x62:
                                raise Exception(f"Unexpected response: {raw_payload}")
                            if raw_payload[1] != did_hi or raw_payload[2] != did_lo:
                                raise Exception(f"DID mismatch: {raw_payload}")

                            raw_data = raw_payload[3:]
                        else:
                            raw_data = raw_payload[1:]

                        # Build HEX string
                        hex_str = " ".join(f"{b:02X}" for b in raw_data)

                        # Try ASCII conversion if printable
                        try:
                            ascii_str = bytes(raw_data).decode("ascii").strip()
                            if all(32 <= ord(c) <= 126 for c in ascii_str):
                                display_value = ascii_str
                            else:
                                display_value = hex_str
                        except:
                            display_value = hex_str

                        # Store value
                        ecu_info[step_desc] = display_value

                        if oled:
                            oled.display_centered_text(f"{step_desc}\n{display_value}")
                            time.sleep(2)

                        logging.info(
                            f"----------------------------------[ECU Info] {step_desc} ({subfunc}) = {display_value}-----------------------------------------------"
                        )

                    except Exception as e:
                        error_msg = str(e)[:40]
                        ecu_info[step_desc] = f"Error: {error_msg}"

                        if oled:
                            oled.display_centered_text(
                                f"{step_desc}\nError: {error_msg}"
                            )

                        logging.error(
                            f"----------------------------------[ECU Info] {step_desc} - Exception: {e}----------------------------------"
                        )

                    time.sleep(0.1)

        if logging_enable:
            self.stop_logging()
        return ecu_info

    def run_testcase(
        self, oled
    ):  
        def wait_for_final_response(client, tc_id, step_desc, timeout_total=3.0):
            response = client.conn.wait_frame(timeout=2)
            time.sleep(0.05)
            start_time = time.time()
            while (
                response and response[0] == 0x7F and response[2] == 0x78
            ):  # time.sleep(1)
                logging.info(
                    f"{tc_id} {step_desc} -> 0x78 Response Pending, waiting for final response..."
                )
                response = client.conn.wait_frame(timeout=2)
                time.sleep(1)
                max_wait = 5
                if time.time() - start_time > max_wait:
                    logging.warning(
                        f"{tc_id} {step_desc} -> Timed out waiting after 0x78"
                    )
                    break
            return response

        if not self.check_memory(oled):
            return

        ecu_info_data = self.get_ecu_information(oled=None, logging_enable=False)
        testcase_file_path = self.get_testcase_file_path()
        base_name = os.path.splitext(os.path.basename(testcase_file_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #self.start_logging(filename=f"{base_name}.asc")
        self.start_logging(filename=f"{base_name}_{timestamp}.asc")

        grouped_cases = load_testcases(testcase_file_path)
        self.context = {}
        immediate_mode = self.config["uds"].get("immediate_mode", False)
        for tc_id, steps in grouped_cases.items():

            print("\n")
            logging.info(f"Running Test Case: {tc_id}")
            for step in steps:
                if step[0] == "WAIT":
                    wait_ms = step[1]
                    logging.info(f"WAIT {wait_ms} ms")
                    oled.display_centered_text(f"WAIT\n{wait_ms/1000:.1f}s")
                    time.sleep(wait_ms / 1000)
                    continue
                if len(step) == 11:
                    (
                        tc_id,
                        step_desc,
                        service,
                        subfunc,
                        expected,
                        write_data,
                        addressing,
                        format_type,
                        status_mask,
                        communication_type,
                        controltype,
                    ) = step
                    
                try:
                    self.switch_mode(addressing)
                    status = "Pass"
                    failure_reason = "-"

                    with Client(
                        self.active_conn["conn"],
                        request_timeout=2,
                        config=self.active_conn["client_config"],
                    ) as client:

                        logging.info(
                            f"Switched to {addressing} mode for TC: {tc_id} Step: {step_desc}"
                        )
                        service_int = int(service, 16)
                        expected_bytes = [int(b, 16) for b in expected.strip().split()]
                        data_to_write = (
                            [int(b, 16) for b in write_data.strip().split()]
                            if write_data
                            else []
                        )

                        logging.info(
                            f"{tc_id} - {step_desc}: SID={service}, Sub={subfunc}, Expected={expected_bytes}"
                        )

                        response = None

                        # Send UDS request
                        if service_int == 0x10:
                            try:
                                # --- Clean and validate subfunction (may be empty or multi-byte)
                                subfunc_clean = (
                                    subfunc.strip()
                                    .replace("0x", "")
                                    .replace(",", " ")
                                    .replace("  ", " ")
                                    .replace(" ", "")
                                )
                                if subfunc_clean:
                                    if not all(
                                        c in "0123456789abcdefABCDEF"
                                        for c in subfunc_clean
                                    ):
                                        raise ValueError(
                                            f"Invalid hex in subfunction: {subfunc_clean}"
                                        )
                                    subfunc_bytes = bytes.fromhex(subfunc_clean)
                                else:
                                    subfunc_bytes = b""  # for missing subfunction test

                                # --- Build raw UDS request
                                raw_request = bytearray([0x10]) + subfunc_bytes
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                                )
                                if oled:
                                    oled.display_centered_text(f"{tc_id}\nSending")
                                time.sleep(0.05)

                                # --- Send and receive
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response = client.conn.wait_frame(timeout=2)
                                self.last_response = response

                                if response:
                                    response_hex = response.hex().upper()
                                    logging.info(f"{tc_id} - Received: {response_hex}")

                                    # --- Process expected response
                                    if expected:
                                        expected_clean = expected.strip().replace(
                                            " ", ""
                                        )
                                        expected_bytes = bytes.fromhex(expected_clean)

                                        if response.startswith(
                                            expected_bytes[: len(response)]
                                        ):
                                            logging.info(
                                                f"{tc_id} - {step_desc} -> PASS"
                                            )
                                        else:
                                            logging.warning(
                                                f"{tc_id} - {step_desc} -> FAIL - Unexpected response"
                                            )
                                    else:
                                        logging.info(
                                            f"{tc_id} - {step_desc} -> PASS (No expected to compare)"
                                        )

                                else:
                                    logging.warning(f"{tc_id} - No response received")
                                    if oled:
                                        oled.display_centered_text(
                                            f"{tc_id}\nNo Response"
                                        )

                            except ValueError as ve:
                                logging.error(f"{tc_id} - Hex Error: {str(ve)}")
                                if oled:
                                    oled.display_centered_text(f"{tc_id}\nHex Error")
                            except Exception as e:
                                logging.error(
                                    f"{tc_id} - Exception: {type(e).__name__} - {str(e)}"
                                )
                                if oled:
                                    oled.display_centered_text(
                                        f"{tc_id}\nError: {str(e)[:16]}"
                                    )

                        elif service_int == 0x11:
                            if subfunc != "":
                                subfunc_int = int(subfunc, 16)
                                raw_request = bytes([0x11, subfunc_int])
                                time.sleep(0.05)
                                if subfunc_int == 0x01:
                                    self.last_request = raw_request
                                    client.conn.send(raw_request)
                                    response = client.conn.wait_frame(timeout=5)
                                    self.last_response = response
                                    time.sleep(1)
                                else:
                                    self.last_request = raw_request
                                    client.conn.send(raw_request)
                                    response = client.conn.wait_frame(timeout=5)
                                    self.last_response = response
                                    
                            elif subfunc == "":
                                subfunc_clean = subfunc.strip()
                                subfunc_bytes = (
                                    bytes.fromhex(subfunc_clean)
                                    if subfunc_clean
                                    else b""
                                )
                                expected_bytes = [
                                    int(b, 16) for b in expected.strip().split()
                                ]
                                raw_request = bytearray([service_int]) + subfunc_bytes
                                time.sleep(0.05)
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response = client.conn.wait_frame(timeout=2)
                                self.last_response = response
                                
                        elif service_int == 0x2F:
                            try:
                                # DID from subfunc
                                if subfunc:
                                    did_int = int(subfunc, 16)
                                    did_hi = (did_int >> 8) & 0xFF
                                    did_lo = did_int & 0xFF

                                    # Get control type from new column in step tuple
                                    control_type_val = controltype.strip()
                                    control_type = (
                                        int(control_type_val, 16)
                                        if control_type_val
                                        else 0x00
                                    )

                                    # Build raw request
                                    raw_request = bytes(
                                        [0x2F, did_hi, did_lo, control_type]
                                    )

                                    # Append write_data if present
                                    if write_data:
                                        raw_request += bytes.fromhex(write_data.strip())

                                    logging.info(
                                        f"{tc_id} - {step_desc}: Sending raw request {raw_request.hex().upper()}"
                                    )
                                    self.last_request = raw_request
                                    client.conn.send(raw_request)
                                    response = wait_for_final_response(
                                        client, tc_id, step_desc
                                    )
                                    self.last_response = response

                                else:  # If subfunc empty
                                    subfunc_clean = subfunc.strip()
                                    subfunc_bytes = (
                                        bytes.fromhex(subfunc_clean)
                                        if subfunc_clean
                                        else b""
                                    )
                                    expected_bytes = [
                                        int(b, 16) for b in expected.strip().split()
                                    ]
                                    raw_request = (
                                        bytearray([service_int]) + subfunc_bytes
                                    )
                                    self.last_request = raw_request
                                    client.conn.send(raw_request)
                                    response = wait_for_final_response(
                                        client, tc_id, step_desc
                                    )
                                    self.last_response = response

                            except Exception as e:
                                logging.error(f"{tc_id} - Error handling 0x2F: {e}")

                        elif service_int == 0x22:  # ReadDataByIdentifier
                            try:
                                raw_request = bytearray(
                                    [service_int]
                                )  # Start with the service byte

                                if subfunc.strip():
                                    # Clean subfunction: remove '0x' and spaces
                                    subfunc_clean = (
                                        subfunc.replace("0x", "")
                                        .replace(" ", "")
                                        .strip()
                                    )

                                    # Check for non-hex characters
                                    if not all(
                                        c in "0123456789abcdefABCDEF"
                                        for c in subfunc_clean
                                    ):
                                        raise ValueError(
                                            f"Invalid hex characters in subfunction: '{subfunc}'"
                                        )

                                    # Pad if odd length
                                    if len(subfunc_clean) % 2 != 0:
                                        subfunc_clean = "0" + subfunc_clean

                                    # Convert to bytes and append
                                    subfunc_bytes = bytes.fromhex(subfunc_clean)
                                    raw_request += subfunc_bytes
                                else:
                                    # Subfunction is empty, only send the service byte
                                    logging.warning(
                                        f"{tc_id} - Subfunction empty: Sending only service byte"
                                    )

                                # Send the request
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending request {raw_request.hex().upper()}"
                                )
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                time.sleep(0.05)

                                # Wait for full response (single or multi-frame)
                                response = wait_for_final_response(
                                    client, tc_id, step_desc
                                )
                                self.last_response = response

                                if response:
                                    response_hex = response.hex().upper()
                                    logging.info(f"{tc_id} - Received: {response_hex}")

                                    # Validate response if expected is provided
                                    if expected:
                                        expected_bytes = [
                                            int(b, 16) for b in expected.strip().split()
                                        ]
                                        if response.startswith(bytes(expected_bytes)):
                                            logging.info(
                                                f"{tc_id} - {step_desc} -> ✅ PASS"
                                            )
                                        else:
                                            logging.warning(
                                                f"{tc_id} - {step_desc} -> ❌ FAIL - Expected {bytes(expected_bytes).hex().upper()}"
                                            )
                                    else:
                                        logging.info(
                                            f"{tc_id} - No expected response provided"
                                        )
                                else:
                                    logging.warning(f"{tc_id} - No response received")

                            except ValueError as ve:
                                logging.error(f"{tc_id} - Subfunction hex error: {ve}")
                                oled.display_centered_text(f"{tc_id}\nHex Error")
                            except Exception as e:
                                logging.error(
                                    f"{tc_id} - Unexpected Error: {type(e).__name__} - {str(e)}"
                                )
                                oled.display_centered_text(
                                    f"{tc_id}\nError: {str(e)[:16]}"
                                )

                        elif service_int == 0x2E:
                            subfunc_int = int(subfunc, 16)
                            if not data_to_write:
                                raise ValueError(
                                    f"No write data provided in testcase for DID {hex(subfunc_int)}"
                                )

                            did_hi = (subfunc_int >> 8) & 0xFF
                            did_lo = subfunc_int & 0xFF
                            raw_request = bytes([0x2E, did_hi, did_lo] + data_to_write)
                            

                            self.last_request = raw_request
                            client.conn.send(raw_request)
                            response = client.conn.wait_frame(timeout=2)
                            self.last_response = response

                        elif service_int == 0x19:

                            if subfunc != "":
                                subfunc_int = int(subfunc, 16)
                                status_mask_int = int(status_mask, 16)
                                raw_request = bytes(
                                    [0x19, subfunc_int, status_mask_int]
                                )
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                                )
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response_data = client.conn.wait_frame(timeout=5)
                                self.last_response = response_data

                            elif subfunc == "":
                                subfunc_clean = subfunc.strip()
                                subfunc_bytes = (
                                    bytes.fromhex(subfunc_clean)
                                    if subfunc_clean
                                    else b""
                                )
                                expected_bytes = [
                                    int(b, 16) for b in expected.strip().split()
                                ]
                                # Append status mask to the request
                                raw_request = (
                                    bytearray([service_int])
                                    + subfunc_bytes
                                    + bytes([status_mask])
                                )
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                                )
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response_data = client.conn.wait_frame(timeout=2)
                                self.last_response = response_data

                        # ClearDiagnosticInformation
                        elif service_int == 0x14:
                            if subfunc != "":
                                subfunc_int = int(subfunc, 16)
                                dtc_group_bytes = [
                                    (subfunc_int >> shift) & 0xFF
                                    for shift in (16, 8, 0)
                                ]
                                raw_request = bytes([0x14] + dtc_group_bytes)
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response_data = client.conn.wait_frame(timeout=2)
                                self.last_response = response_data
                            elif subfunc == "":
                                subfunc_clean = subfunc.strip()
                                subfunc_bytes = (
                                    bytes.fromhex(subfunc_clean)
                                    if subfunc_clean
                                    else b""
                                )
                                expected_bytes = [
                                    int(b, 16) for b in expected.strip().split()
                                ]
                                raw_request = bytearray([service_int]) + subfunc_bytes
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                                )
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response_data = client.conn.wait_frame(timeout=2)
                                self.last_response = response_data
                                logging.info(
                                    f"{tc_id} - Received: {response_data.hex().upper()}"
                                )

                        elif service_int == 0x3E:  # TesterPresent
                            if subfunc != "":

                                subfunc_int = int(subfunc, 16)
                                raw_request = bytes([0x3E, subfunc_int])
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response_data = client.conn.wait_frame(timeout=2)
                                self.last_response = response_data
                        elif subfunc == "":

                            subfunc_clean = subfunc.strip()
                            subfunc_bytes = (
                                bytes.fromhex(subfunc_clean) if subfunc_clean else b""
                            )
                            expected_bytes = [
                                int(b, 16) for b in expected.strip().split()
                            ]
                            raw_request = bytearray([service_int]) + subfunc_bytes
                            self.last_request = raw_request
                            client.conn.send(raw_request)
                            response_data = client.conn.wait_frame(timeout=2)
                            self.last_response = response_data

                        elif service_int == 0x85:  # ControlDTCSetting
                            try:
                                subfunc_clean = subfunc.strip().replace(" ", "")

                                if subfunc_clean:
                                    # Validate and convert subfunction to bytes
                                    if len(subfunc_clean) % 2 != 0:
                                        subfunc_clean = (
                                            "0" + subfunc_clean
                                        )  # pad if needed

                                    subfunc_bytes = bytes.fromhex(subfunc_clean)
                                else:
                                    subfunc_bytes = b""  # No subfunction, test "incorrect message length"

                                # Build the full request
                                raw_request = bytearray([service_int]) + subfunc_bytes
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                                )
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                time.sleep(0.05)
                                response_data = client.conn.wait_frame(timeout=2)
                                self.last_response = response_data

                                if response_data:
                                    logging.info(
                                        f"{tc_id} - Received: {response_data.hex().upper()}"
                                    )

                                    # Validate response if expected data is provided
                                    if expected:
                                        expected_bytes = [
                                            int(b, 16) for b in expected.strip().split()
                                        ]
                                        if response_data[
                                            : len(expected_bytes)
                                        ] == bytes(expected_bytes):
                                            logging.info(
                                                f"{tc_id} - {step_desc} -> PASS"
                                            )
                                        else:
                                            logging.warning(
                                                f"{tc_id} - {step_desc} -> FAIL - Response mismatch"
                                            )
                                    else:
                                        logging.info(
                                            f"{tc_id} - No expected response to validate"
                                        )
                                else:
                                    logging.warning(f"{tc_id} - No response received")

                            except ValueError as ve:
                                logging.error(
                                    f"{tc_id} - Invalid hex in subfunction: {ve}"
                                )
                            except Exception as e:
                                logging.error(
                                    f"{tc_id} - Exception: {type(e).__name__} - {str(e)}"
                                )

                        elif service_int == 0x27:
                            if subfunc == "":

                                subfunc_clean = subfunc.strip()
                                subfunc_bytes = (
                                    bytes.fromhex(subfunc_clean)
                                    if subfunc_clean
                                    else b""
                                )
                                expected_bytes = [
                                    int(b, 16) for b in expected.strip().split()
                                ]
                                raw_request = bytearray([service_int]) + subfunc_bytes
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response_data = client.conn.wait_frame(timeout=2)
                                self.last_response = response_data
                            else:
                                subfunc_int = int(subfunc, 16)
                                if subfunc_int % 2 == 1:  # requestSeed
                                    raw_request = bytes([0x27, subfunc_int])
                                    self.last_request = raw_request
                                    client.conn.send(raw_request)
                                    response = wait_for_final_response(
                                        client, tc_id, step_desc
                                    )
                                    self.last_response = response
                                    raw_payload = list(response)
                                    logging.debug(
                                        f"{tc_id} {step_desc} -> Received payload: {raw_payload}"
                                    )
                                    if (
                                        raw_payload[0] != 0x67
                                        or raw_payload[1] != subfunc_int
                                    ):
                                        failure_reason = f"NRC (key): {raw_payload}"
                                        logging.warning(
                                            f"{tc_id} {step_desc} -> FAIL - {failure_reason}"
                                        )
                                        raise Exception(failure_reason)
                                    seed = bytes(raw_payload[2:])
                                    self.context[f"seed_{subfunc_int}"] = seed
                                    logging.info(
                                        f"Received Seed (subfunc {hex(subfunc_int)}): {seed.hex()}"
                                    )
                                    time.sleep(0.5)
                                    # Send seed to PC and get key
                                    # ----------------------------------------------------
                                    # # Check whether UDP server is available.
                                    # # If not, try to reconnect once.
                                    # # ----------------------------------------------------
                                    if not self.udp_server_available:
                                        logging.warning("UDP server unavailable. Rechecking...")
                                        if self.check_udp_server():
                                            logging.info("UDP server reconnected.")
                                            self.udp_server_available = True
                                        else:
                                            logging.error("UDP server still unavailable.")
                                            if oled:
                                                oled.display_centered_text("UDP Server\nUnavailable")
                                                time.sleep(2)
                                            raise Exception("UDP Server not available")
                                    udp_ip = self.udp_ip_
                                    udp_port = self.udp_port_
                                    max_retries = 3
                                    retry_delay = 1.0
                                    expected_key_length = self.expected_key_length_

                                    sock = socket.socket(
                                        socket.AF_INET, socket.SOCK_DGRAM
                                    )
                                    sock.settimeout(5)
                                    try:
                                        for attempt in range(1, max_retries + 1):
                                            try:
                                                logging.info(
                                                    f"Attempt {attempt}: Sending seed to PC..."
                                                )
                                                sock.sendto(
                                                    seed.hex().encode(),
                                                    (udp_ip, udp_port),
                                                )
                                                key, _ = sock.recvfrom(1024)
                                                key = key.strip()
                                                if not key:
                                                    raise Exception("Empty key received from UDP server")
                                                if len(key) != expected_key_length:
                                                    raise Exception(f"Invalid key length. Expected {expected_key_length}, got {len(key)}")
                                                self.context[f"key_{subfunc_int + 1}"] = key
                                                logging.info(f"Received Key (for subfunc {hex(subfunc_int + 1)}): {key}")
                                                self.udp_server_available = True
                                                break

                                            except socket.timeout:
                                                logging.warning(
                                                    f"Attempt {attempt} - Timeout waiting for key."
                                                )
                                                if attempt < max_retries:
                                                    time.sleep(retry_delay)
                                                else:
                                                    self.udp_server_available = False
                                                    raise Exception(f"Timeout after {max_retries} retries waiting for key from PC")
                                            except Exception as e:
                                                self.udp_server_available = False
                                                logging.exception(
                                                    f"Attempt {attempt} - Error occurred:"
                                                )
                                                raise
                                    finally:
                                        sock.close()
                                elif subfunc_int % 2 == 0:
                                    key = self.context.get(f"key_{subfunc_int}")
                                    if key:
                                        raw_request = bytes([0x27, subfunc_int]) + key
                                    if not key:
                                        logging.info(
                                            f"No key available for subfunction {hex(subfunc_int)}. Ensure seed request precedes key send. aaaaaaa"
                                        )
                                        raw_request = bytes([0x27, subfunc_int])
                                    self.last_request = raw_request
                                    client.conn.send(raw_request)
                                    response = wait_for_final_response(
                                        client, tc_id, step_desc
                                    )
                                    self.last_response = response

                                    raw_payload = list(response)
                                    logging.debug(
                                        f"{tc_id} {step_desc} -> Received payload: {raw_payload}"
                                    )

                                    if (
                                        raw_payload[0] != 0x67
                                        or raw_payload[1] != subfunc_int
                                    ):
                                        failure_reason = f"NRC (key): {raw_payload}"
                                        logging.warning(
                                            f"{tc_id} {step_desc} -> FAIL - {failure_reason}"
                                        )
                                        raise Exception(failure_reason)

                                else:
                                    raise ValueError(
                                        f"Unsupported subfunction for service 0x27: {hex(subfunc_int)}"
                                    )

                        elif service_int == 0x28:
                            if subfunc != "":
                                try:
                                    subfunc_clean = subfunc.strip()
                                    control_type = int(subfunc_clean, 16)

                                    # Use communication_type from .txt if provided
                                    if communication_type:
                                        try:
                                            communication_type_int = int(
                                                communication_type, 16
                                            )
                                        except ValueError:
                                            logging.warning(
                                                f"{tc_id} - Invalid communication_type '{communication_type}', defaulting to control_type"
                                            )
                                            communication_type_int = control_type
                                    else:
                                        communication_type_int = (
                                            control_type  # Fallback
                                        )

                                    raw_request = bytes(
                                        [0x28, control_type, communication_type_int]
                                    )
                                    logging.info(
                                        f"{tc_id} - {step_desc}: Sending raw request {raw_request.hex().upper()}"
                                    )
                                    self.last_request = raw_request
                                    client.conn.send(raw_request)
                                    response = wait_for_final_response(
                                        client, tc_id, step_desc
                                    )
                                    self.last_response = response

                                except ValueError:
                                    logging.error(
                                        f"{tc_id} - Invalid subfunction format: '{subfunc}'"
                                    )
                                except Exception as e:
                                    logging.error(
                                        f"{tc_id} - Error sending CommunicationControl raw request: {e}"
                                    )

                            elif subfunc == "":
                                subfunc_clean = subfunc.strip()
                                subfunc_bytes = (
                                    bytes.fromhex(subfunc_clean)
                                    if subfunc_clean
                                    else b""
                                )
                                expected_bytes = [
                                    int(b, 16) for b in expected.strip().split()
                                ]
                                raw_request = bytearray([service_int]) + subfunc_bytes
                                self.last_request = raw_request
                                client.conn.send(raw_request)
                                response_data = client.conn.wait_frame(timeout=2)
                                self.last_response = response_data

                except Exception as e:
                    status = "Fail"
                    failure_reason = str(e)
                    logging.error(
                        f"----------------------------------{tc_id} {step_desc} -> EXCEPTION - {failure_reason}----------------------------------"
                    )
                try:
                    # oled.display_centered_text(f"{tc_id}\n{step_desc[:20]}\n{status}")
                    if not immediate_mode:
                        delay_key = service.upper()
                        delay = float(
                            self.step_delays.get(delay_key, self.default_delay)
                        )
                        oled.display_centered_text(
                            f"{tc_id}\n{step_desc[:20]}\n{status}"
                        )
                        time.sleep(delay)
                except Exception as e:
                    logging.error(
                        f"----------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}----------------------------------"
                    )

        self.stop_logging()
        time.sleep(1.5)

        full_log_path = self.can_logger.get_log_path() or "N/A"
        can_log_file = os.path.basename(full_log_path)

        # Confirm log file presence
        if not os.path.isfile(full_log_path):
            logging.error(f"File not found after logging stopped: {full_log_path}")
            oled.display_centered_text("Log Error!\nFile Missing.")
            return
        else:

            logging.info(
                "----------------------------------Log Generated!----------------------------------"
            )
            time.sleep(2)

        report_dir = os.path.join(self.project_root, "output", "html_reports")
        os.makedirs(report_dir, exist_ok=True)
        report_filename = (f"{base_name}_{timestamp}.html")
        report_path = os.path.join(report_dir,report_filename)
        # Wait for log file to appear (max 3 seconds)
        for _ in range(6):
            if os.path.exists(full_log_path):
                print(f"Log file found: {full_log_path}")
                break
            else:
                print(f" Waiting for log file to appear: {full_log_path}")
                time.sleep(0.5)
        else:
            print(f"File not found: {can_log_file}")

        generate_report(
            asc_file_path=full_log_path,
            txt_file_path=testcase_file_path,
            output_html_file=report_path,
            allowed_tx_ids=self.allowed_tx_ids,
            allowed_rx_ids=self.allowed_rx_ids,
            ecu_info_data=ecu_info_data,
            target_ecu=self.target_ecu,
        )

        oled.display_centered_text("Report Generated")
        logging.info(
            "----------------------------------Report Generated----------------------------------"
        )

        time.sleep(2)
