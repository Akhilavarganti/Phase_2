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
from drivers.did_decoder import decode_special_did_value
from udsoncan.services import WriteDataByIdentifier

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#os.makedirs(os.path.join(BASE_DIR, "output", "can_logs"), exist_ok=True)

#os.makedirs(os.path.join(BASE_DIR, "output", "html_reports"), exist_ok=True)

os.makedirs(os.path.join(BASE_DIR, "output", "logs"), exist_ok=True)

os.makedirs(os.path.join(BASE_DIR, "supportfiles"), exist_ok=True)


class SafeAsciiCodec(AsciiCodec):
    def decode(self, data):
        try:
            return data.decode("ascii")
        except UnicodeDecodeError:
            return data.hex()


class UDSClient:
    @staticmethod
    def _hex_field_to_bytes(value):
        cleaned = (
            str(value or "")
            .replace("0x", "")
            .replace("0X", "")
            .replace(",", " ")
            .strip()
        )
        if not cleaned:
            return b""

        compact = "".join(cleaned.split())
        if len(compact) % 2 != 0:
            compact = "0" + compact

        if not all(c in "0123456789abcdefABCDEF" for c in compact):
            raise ValueError(f"Invalid hex value: {value}")

        return bytes.fromhex(compact)

    def __init__(self, config, config_path=None, repo_path=None):
        self.config = config
        self.config_path = config_path
        self.repo_path = repo_path
        can_cfg = config["uds"]["can"]
        isotp_cfg = config["uds"]["isotp"]
        timing_cfg = config["uds"]["timing"]
        self.uds_config = config["uds"]
        self.isotp_config = isotp_cfg
        self.can_cfg = can_cfg
        
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

        self.addr_modes_cfg = self.uds_config["addressing_modes"]
        self.physical_conn = self._create_connection(
            self.addr_modes_cfg.get("physical"), can_cfg, isotp_cfg, "physical"
        )
        self.functional_conn = None

        self.active_conn = self.physical_conn
        self.active_mode = "physical"

        self.allowed_ids = list(
            {
                int(self.addr_modes_cfg.get("physical", {}).get("tx_id", "0"), 16),
                int(self.addr_modes_cfg.get("physical", {}).get("rx_id", "0"), 16),
                int(self.addr_modes_cfg.get("functional", {}).get("tx_id", "0"), 16),
                int(self.addr_modes_cfg.get("functional", {}).get("rx_id", "0"), 16),
            }
        )

        self.allowed_tx_ids = [
            int(self.addr_modes_cfg.get("physical", {}).get("tx_id", "0"), 16),
            int(self.addr_modes_cfg.get("functional", {}).get("tx_id", "0"), 16),
        ]

        self.allowed_rx_ids = [
            int(self.addr_modes_cfg.get("physical", {}).get("rx_id", "0"), 16),
            int(self.addr_modes_cfg.get("functional", {}).get("rx_id", "0"), 16),
        ]
        
        if self.repo_path:
            self.project_root = self.repo_path
            logging.info("CAN logs project root: %s", self.project_root)
        else:
            if getattr(sys, "frozen", False):
                self.project_root = os.path.dirname(sys.executable)
            else:
                self.project_root = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..")
                )
                
        
        filters = self.get_can_filters()
        os.makedirs(os.path.join(BASE_DIR, "output", "can_logs"), exist_ok=True)
        os.makedirs(os.path.join(BASE_DIR, "output", "html_reports"), exist_ok=True)
        log_dir = os.path.join(self.project_root, "output", "can_logs")
        self.can_logger = CANLogger(
            channel=can_cfg["channel"],
            interface=can_cfg["interface"],
            can_fd=can_cfg.get("can_fd", True),
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
    def oled_show(self, oled, message, delay=1.5):
        if oled:
            oled.display_centered_text(message)
        print(message)
        time.sleep(delay)
            
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
        sniffer_bus = can.interface.Bus(
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
            "bus": bus,
            "sniffer_bus": sniffer_bus,
            "addr_cfg": addr_cfg,
            "tx_id": tx_id,
            "rx_id": rx_id,
            "is_extended": is_extended,
            "client_config": self.client_config,
            "mode_name": mode_name,
        }

    def _close_connection(self, conn_entry):
        if not conn_entry:
            return
        try:
            conn_entry["conn"].close()
        except Exception:
            pass
        try:
            conn_entry["bus"].shutdown()
        except Exception:
            pass
        try:
            conn_entry["sniffer_bus"].shutdown()
        except Exception:
            pass

    def _drain_sniffer_bus(self, conn_entry):
        if not conn_entry:
            return
        while True:
            msg = conn_entry["sniffer_bus"].recv(timeout=0.0)
            if msg is None:
                break

    def _send_flow_control_frame(self, conn_entry):
        tx_len = int(self.isotp_config.get("tx_data_length", 8))
        padding = int(self.isotp_config.get("tx_padding", 0))
        blocksize = int(self.isotp_config.get("blocksize", 8))
        stmin = self.isotp_config.get("stmin", 0)
        if isinstance(stmin, str):
            stmin = int(stmin, 0)

        payload = [0x30, blocksize & 0xFF, stmin & 0xFF]
        payload.extend([padding] * max(0, tx_len - len(payload)))

        msg = can.Message(
            arbitration_id=conn_entry["tx_id"],
            is_extended_id=conn_entry["is_extended"],
            is_fd=self.can_cfg.get("can_fd", True),
            bitrate_switch=self.isotp_config.get("bitrate_switch", True),
            data=payload[:tx_len],
        )
        conn_entry["sniffer_bus"].send(msg)

    def _wait_for_raw_response(self, conn_entry, tc_id, step_desc):
        active_config = conn_entry["client_config"]
        p2_timeout = float(
            active_config.get("p2_timeout", self.client_config.get("p2_timeout", 2.0))
        )
        p2_star_timeout = float(
            active_config.get(
                "p2_star_timeout",
                self.client_config.get("p2_star_timeout", 5.0),
            )
        )
        cf_timeout = self._get_cf_timeout(active_config)
        max_pending_responses = int(
            self.uds_config.get("timing", {}).get("max_pending_responses", 20)
        )

        pending_count = 0
        timeout = p2_timeout

        while True:
            msg = conn_entry["sniffer_bus"].recv(timeout=timeout)
            if msg is None:
                return None

            data = bytes(msg.data)
            if not data:
                continue

            frame_type = (data[0] >> 4) & 0x0F

            # Ignore ISO-TP flow-control frames from the ECU. These are not
            # diagnostic responses; they only acknowledge an outgoing
            # multi-frame request such as SecurityAccess key send (0x27 0x12).
            if frame_type == 0x3:
                continue

            if frame_type == 0x0:
                payload_len = data[0] & 0x0F
                payload = data[1:1 + payload_len]
                if len(payload) >= 3 and payload[0] == 0x7F and payload[2] == 0x78:
                    pending_count += 1
                    if pending_count > max_pending_responses:
                        return payload
                    timeout = p2_star_timeout
                    continue
                return payload

            if frame_type == 0x1:
                total_len = ((data[0] & 0x0F) << 8) | data[1]
                payload = bytearray(data[2:])
                self._send_flow_control_frame(conn_entry)
                expected_sn = 1

                while len(payload) < total_len:
                    cf_msg = conn_entry["sniffer_bus"].recv(timeout=cf_timeout)
                    if cf_msg is None:
                        logging.warning(
                            f"{tc_id} {step_desc} -> Raw CAN reassembly timeout "
                            f"({len(payload)}/{total_len})"
                        )
                        return bytes(payload[:total_len])

                    cf_data = bytes(cf_msg.data)
                    if not cf_data:
                        continue

                    cf_type = (cf_data[0] >> 4) & 0x0F
                    if cf_type != 0x2:
                        continue

                    sequence_number = cf_data[0] & 0x0F
                    if sequence_number != (expected_sn & 0x0F):
                        logging.warning(
                            f"{tc_id} {step_desc} -> Raw CAN CF SN mismatch. "
                            f"Expected {expected_sn & 0x0F}, got {sequence_number}"
                        )
                    payload.extend(cf_data[1:])
                    expected_sn += 1

                return bytes(payload[:total_len])

            # Already payload-form response from another transport layer; accept as-is.
            return data

    def switch_mode(self, mode):
        mode = mode.lower()
        if mode not in ("physical", "functional"):
            raise ValueError(f"Unsupported or unconfigured addressing mode: {mode}")

        if self.active_mode == mode and self.active_conn is not None:
            return

        if self.active_mode == "physical" and self.physical_conn is not None:
            self._close_connection(self.physical_conn)
            self.physical_conn = None
        elif self.active_mode == "functional" and self.functional_conn is not None:
            self._close_connection(self.functional_conn)
            self.functional_conn = None

        target_cfg = self.addr_modes_cfg.get(mode)
        new_conn = self._create_connection(
            target_cfg, self.can_cfg, self.isotp_config, mode
        )
        if new_conn is None:
            raise ValueError(f"Unsupported or unconfigured addressing mode: {mode}")

        if mode == "physical":
            self.physical_conn = new_conn
        else:
            self.functional_conn = new_conn

        self.active_conn = new_conn
        self.active_mode = mode

    def _reset_connections(self):
        self._close_connection(self.physical_conn)
        self._close_connection(self.functional_conn)
        self.physical_conn = self._create_connection(
            self.addr_modes_cfg.get("physical"),
            self.can_cfg,
            self.isotp_config,
            "physical",
        )
        self.functional_conn = None
        self.active_conn = self.physical_conn
        self.active_mode = "physical"

    def _prepare_ecu_before_logged_run(self):
        logging.info("Preparing ECU and CAN/ISO-TP connections before logged run")
        self._reset_connections()
        self._prepare_execution_start()

        default_session = int(self.uds_config.get("default_session", "0x01"), 16)
        try:
            with Client(
                self.active_conn["conn"],
                request_timeout=2,
                config=self.active_conn["client_config"],
            ) as client:
                response = self._send_request_and_wait(
                    client,
                    bytes([0x10, default_session]),
                    "PRE_RUN",
                    "Start default session before logged execution",
                    post_wait=0.2,
                )
                logging.info(
                    "Pre-run default session response: "
                    f"{response.hex().upper() if response else 'No response'}"
                )
        except Exception as exc:
            logging.warning(f"Pre-run default session preparation failed: {exc}")

        self._reset_connections()
        self._prepare_execution_start()

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

    def _prepare_execution_start(self):
        startup_settle_ms = int(
            self.uds_config.get("timing", {}).get("startup_settle_ms", 250)
        )
        settle_seconds = max(0.0, startup_settle_ms / 1000.0)

        if settle_seconds > 0:
            logging.info(
                f"Execution startup settle delay: {settle_seconds:.3f}s before first testcase"
            )
            time.sleep(settle_seconds)

        for conn_name, conn_entry in (
            ("physical", self.physical_conn),
            ("functional", self.functional_conn),
            ("active", self.active_conn),
        ):
            if not conn_entry:
                continue
            try:
                self._drain_sniffer_bus(conn_entry)
                logging.info(f"Drained stale CAN frames on {conn_name} sniffer bus")
            except Exception as exc:
                logging.warning(
                    f"Failed to drain {conn_name} sniffer bus before execution: {exc}"
                )

    def get_testcase_file_path(self):
         support_dir = os.path.join(BASE_DIR, "supportfiles")
         selected_testcase_path = os.path.join(BASE_DIR, "selected_testcase.txt")

         if not os.path.exists(support_dir):
              raise FileNotFoundError(f"Testcase folder not found: {support_dir}")

         if os.path.exists(selected_testcase_path):
              with open(selected_testcase_path, "r", encoding="utf-8") as f:
                   selected_name = f.read().strip()

              if selected_name:
                   selected_file = os.path.join(support_dir, selected_name)
                   if os.path.isfile(selected_file):
                        return selected_file

         txt_files = sorted(
              file for file in os.listdir(support_dir)
              if file.lower().endswith(".txt")
         )
         if txt_files:
              return os.path.join(support_dir, txt_files[0])

         raise FileNotFoundError(f"Testcase file not found in: {support_dir}")
            

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
            def normalize_payload(payload):
                data = [int(b) for b in (payload or [])]
                if not data:
                    return []
                pci = data[0]
                frame_type = (pci >> 4) & 0x0F
                if frame_type == 0x0:
                    declared_len = pci & 0x0F
                    return data[1:1 + declared_len]
                if frame_type == 0x1 and len(data) >= 2:
                    total_len = ((pci & 0x0F) << 8) | data[1]
                    return data[2:2 + total_len]
                while data and data[-1] in (0x00, 0xAA, 0x20):
                    data.pop()
                return data

            def compare_variants(payload):
                raw = [int(b) for b in (payload or [])]
                normalized = normalize_payload(raw)
                variants = []
                for candidate in (raw, normalized):
                    trimmed = list(candidate)
                    while trimmed and trimmed[-1] in (0x00, 0xAA, 0x20):
                        trimmed.pop()
                    for value in (candidate, trimmed):
                        if value and value not in variants:
                            variants.append(value)
                if len(normalized) >= 2 and normalized[0] == 0x67:
                    security_prefix = normalized[:2]
                    if security_prefix not in variants:
                        variants.append(security_prefix)
                return variants

            actual_variants = compare_variants(raw_payload)
            expected_variants = compare_variants(expected_bytes)
            if any(actual == expected for actual in actual_variants for expected in expected_variants):
                status = "Pass"
                logging.info(
                    f"-----------------------------------------------{tc_id} {step_desc} -> PASS-----------------------------------------------"
                )
                return status, failure_reason

            actual_payload = normalize_payload(raw_payload)
            expected_payload = normalize_payload(expected_bytes)
            if not actual_payload:
                failure_reason = "No response received"
                logging.warning(
                    f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                )
                return status, failure_reason

            expected_first_byte = expected_payload[0] if expected_payload else expected_bytes[0]
            actual_first_byte = actual_payload[0]

            # --- Negative response expected ---
            if expected_first_byte == 0x7F:
                if actual_first_byte == 0x7F:
                    nrc_code = actual_payload[2] if len(actual_payload) >= 3 else None

                    if len(expected_payload) == 1:
                        # User gave only 0x7F → accept any NRC
                        status = "Pass"
                        logging.info(
                            f"{tc_id} {step_desc} -> PASS (any NRC accepted because only 0x7F given)"
                        )
                    elif len(expected_payload) == 3:
                        # User gave full expected negative response → check
                        if nrc_code == expected_payload[-1]:
                            status = "Pass"
                            logging.info(
                                f"-----------------------------------------------{tc_id} {step_desc} -> PASS-----------------------------------------------"
                            )
                        else:
                            failure_reason = f"Expected NRC {hex(expected_payload[-1])}, got {hex(nrc_code) if nrc_code is not None else 'Unknown'}"
                            logging.warning(
                                f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                            )
                    else:
                        failure_reason = f"Malformed expected bytes for negative response: {expected_payload}"
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
                    if actual_payload[: len(expected_payload)] == expected_payload:
                        status = "Pass"
                        logging.info(
                            f"----------------------------------{tc_id} {step_desc} -> PASS-----------------------------------------------"
                        )

                    else:
                        failure_reason = f"Expected {expected_payload}, got {actual_payload[:len(expected_payload)]}"
                        logging.warning(
                            f"-----------------------------------------------{tc_id} {step_desc} -> FAIL - {failure_reason}-----------------------------------------------"
                        )
                else:
                    nrc_code = actual_payload[2] if len(actual_payload) >= 3 else None
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

    def _stmin_to_seconds(self, stmin_value):
        if isinstance(stmin_value, str):
            stmin_value = int(stmin_value, 0)
        if 0 <= stmin_value <= 0x7F:
            return stmin_value / 1000.0
        if 0xF1 <= stmin_value <= 0xF9:
            return (stmin_value - 0xF0) / 10000.0
        return 0.0

    def _get_cf_timeout(self, active_config=None):
        active_config = active_config or self.active_conn.get("client_config", {})
        p2_star_timeout = float(
            active_config.get(
                "p2_star_timeout",
                self.client_config.get("p2_star_timeout", 5.0),
            )
        )
        configured_cf_timeout = float(
            self.uds_config.get("timing", {}).get("cf_wait_timeout", 0.25)
        )
        stmin_seconds = self._stmin_to_seconds(self.isotp_config.get("stmin", 0))

        # CANoe-style traces here show CF spacing around 100 ms. Give enough margin
        # for STmin plus Linux/Raspberry Pi scheduling jitter.
        stmin_guard = (stmin_seconds * 3) + 0.2 if stmin_seconds > 0 else 0.0
        return max(p2_star_timeout, configured_cf_timeout, stmin_guard, 1.0)

    def _trim_expected_bytes(self, expected_bytes):
        trimmed = list(expected_bytes or [])
        while trimmed and trimmed[-1] in (0x00, 0xAA):
            trimmed.pop()
        return trimmed

    def _expected_payload_length(self, expected_bytes):
        trimmed = self._trim_expected_bytes(expected_bytes)
        if not trimmed:
            return None

        first = trimmed[0]
        frame_type = (first >> 4) & 0x0F
        if frame_type == 0x1 and len(trimmed) >= 2:
            declared_len = ((first & 0x0F) << 8) | trimmed[1]
            available_len = max(0, len(trimmed) - 2)
            return min(declared_len, available_len) if available_len else declared_len
        if frame_type == 0x0:
            declared_len = first & 0x0F
            available_len = max(0, len(trimmed) - 1)
            return min(declared_len, available_len) if available_len else declared_len
        return None

    def _extract_payload_view(self, response):
        if not response:
            return bytearray(), None

        if len(response) >= 2 and ((response[0] >> 4) & 0x0F) == 0x1:
            total_len = ((response[0] & 0x0F) << 8) | response[1]
            return bytearray(response[2:]), total_len

        if len(response) >= 1 and ((response[0] >> 4) & 0x0F) == 0x0:
            total_len = response[0] & 0x0F
            return bytearray(response[1:1 + total_len]), total_len

        return bytearray(response), None

    def _extend_response_to_expected(
        self, response, expected_bytes, client, tc_id, step_desc
    ):
        expected_len = self._expected_payload_length(expected_bytes)
        if not response or not expected_len:
            return response

        payload, detected_len = self._extract_payload_view(response)
        if detected_len is None:
            return response

        target_len = detected_len or expected_len
        if len(payload) >= target_len:
            return response

        cf_timeout = self._get_cf_timeout()
        logging.info(
            f"{tc_id} {step_desc} -> Response shorter than expected "
            f"({len(payload)}/{target_len}). Waiting for remaining payload."
        )

        while len(payload) < target_len:
            next_frame = client.conn.wait_frame(timeout=cf_timeout)
            if not next_frame:
                logging.warning(
                    f"{tc_id} {step_desc} -> Timed out while extending response "
                    f"({len(payload)}/{target_len})"
                )
                break

            if len(next_frame) >= 1:
                frame_type = (next_frame[0] >> 4) & 0x0F
                if frame_type == 0x3:
                    continue
                if frame_type == 0x2:
                    payload.extend(next_frame[1:])
                    continue

            # Fallback for transports that already strip PCI and only expose payload bytes.
            payload.extend(next_frame)

        return bytes(payload[:target_len])

    def _reassemble_isotp_response(
        self, first_frame, client, tc_id, step_desc, cf_timeout=None
    ):
        if not first_frame or len(first_frame) < 2:
            return first_frame

        pci = first_frame[0]
        frame_type = (pci >> 4) & 0x0F
        if frame_type != 0x1:
            return first_frame

        total_len = ((pci & 0x0F) << 8) | first_frame[1]
        payload = bytearray(first_frame[2:])
        expected_sn = 1
        cf_timeout = self._get_cf_timeout() if cf_timeout is None else cf_timeout

        logging.info(
            f"{tc_id} {step_desc} -> Reassembling ISO-TP multi-frame response, "
            f"total payload {total_len} bytes, CF timeout {cf_timeout:.3f}s"
        )

        while len(payload) < total_len:
            next_frame = client.conn.wait_frame(timeout=cf_timeout)
            if not next_frame:
                logging.warning(
                    f"{tc_id} {step_desc} -> Timed out waiting for consecutive "
                    f"frame {expected_sn} after collecting {len(payload)}/{total_len} bytes"
                )
                return bytes([first_frame[0], first_frame[1]]) + bytes(payload)

            next_pci = next_frame[0]
            next_type = (next_pci >> 4) & 0x0F

            if next_type == 0x3:
                continue

            if next_type != 0x2:
                logging.warning(
                    f"{tc_id} {step_desc} -> Unexpected frame during reassembly: "
                    f"{next_frame.hex().upper()}"
                )
                return bytes([first_frame[0], first_frame[1]]) + bytes(payload)

            sequence_number = next_pci & 0x0F
            if sequence_number != (expected_sn & 0x0F):
                logging.warning(
                    f"{tc_id} {step_desc} -> Consecutive frame SN mismatch. "
                    f"Expected {expected_sn & 0x0F}, got {sequence_number}"
                )

            payload.extend(next_frame[1:])
            expected_sn += 1

        return bytes([first_frame[0], first_frame[1]]) + bytes(payload[:total_len])

    def _wait_for_final_response(self, client, tc_id, step_desc):
        active_config = self.active_conn["client_config"]
        p2_timeout = active_config.get(
            "p2_timeout",
            self.client_config.get("p2_timeout", 2.0),
        )
        p2_star_timeout = active_config.get(
            "p2_star_timeout",
            self.client_config.get("p2_star_timeout", 5.0),
        )
        max_pending_responses = int(
            self.uds_config.get("timing", {}).get("max_pending_responses", 20)
        )

        logging.info(
            f"{tc_id} {step_desc} -> Waiting for response "
            f"(P2={p2_timeout}s, P2*={p2_star_timeout}s)"
        )
        response = client.conn.wait_frame(timeout=p2_timeout)
        pending_count = 0

        while response and len(response) >= 3 and response[0] == 0x7F and response[2] == 0x78:
            pending_count += 1
            logging.info(
                f"{tc_id} {step_desc} -> 0x78 Response Pending ({pending_count}), "
                "waiting with P2*..."
            )
            if pending_count > max_pending_responses:
                logging.warning(
                    f"{tc_id} {step_desc} -> Exceeded max pending responses "
                    f"({max_pending_responses})"
                )
                return response

            response = client.conn.wait_frame(timeout=p2_star_timeout)

        response = self._reassemble_isotp_response(
            response,
            client,
            tc_id,
            step_desc,
            self._get_cf_timeout(active_config),
        )

        if response:
            tx_data_length = int(self.isotp_config.get("tx_data_length", 8))
            first_frame_payload = max(tx_data_length - 2, 1)
            consecutive_frame_payload = max(tx_data_length - 1, 1)
            response_len = len(response)
            stmin_seconds = self._stmin_to_seconds(self.isotp_config.get("stmin", 0))
            configured_guard_ms = self.uds_config.get("timing", {}).get(
                "inter_request_guard_ms",
                0,
            )

            guard_time = 0.05
            if response_len > first_frame_payload and stmin_seconds > 0:
                extra_frames = max(
                    1,
                    (response_len - first_frame_payload + consecutive_frame_payload - 1)
                    // consecutive_frame_payload,
                )
                guard_time = max(guard_time, (extra_frames + 1) * stmin_seconds)

            if configured_guard_ms:
                guard_time = max(guard_time, configured_guard_ms / 1000.0)

            logging.info(f"{tc_id} {step_desc} -> Inter-request guard {guard_time:.3f}s")
            time.sleep(guard_time)
        else:
            time.sleep(0.05)

        return response

    def _send_request_and_wait(
        self,
        client,
        raw_request,
        tc_id,
        step_desc,
        post_wait=0.0,
        expected_bytes=None,
    ):
        logging.info(f"{tc_id} - {step_desc}: Sending request {raw_request.hex().upper()}")
        self._drain_sniffer_bus(self.active_conn)
        self.last_request = raw_request
        client.conn.send(raw_request)
        response = self._wait_for_raw_response(self.active_conn, tc_id, step_desc)
        if response is None:
            response = self._wait_for_final_response(client, tc_id, step_desc)
        if expected_bytes:
            response = self._extend_response_to_expected(
                response, expected_bytes, client, tc_id, step_desc
            )
        self.last_response = response
        if post_wait > 0:
            time.sleep(post_wait)
        return response

    def _is_empty_read_did_response(self, response):
        if not response or len(response) < 3 or response[0] != 0x62:
            return False
        data_bytes = list(response[3:])
        while data_bytes and data_bytes[-1] in (0x00, 0xAA):
            data_bytes.pop()
        return len(data_bytes) == 0

    def _send_read_did_with_retry(
        self,
        client,
        raw_request,
        tc_id,
        step_desc,
        expected_bytes=None,
        post_wait=0.05,
    ):
        retry_cfg = self.uds_config.get("timing", {})
        max_attempts = int(retry_cfg.get("ecu_info_read_retries", 3))
        retry_delay = float(retry_cfg.get("ecu_info_retry_delay_ms", 250)) / 1000.0
        max_attempts = max(1, max_attempts)

        response = None
        for attempt in range(1, max_attempts + 1):
            response = self._send_request_and_wait(
                client,
                raw_request,
                tc_id,
                step_desc,
                post_wait=post_wait,
                expected_bytes=expected_bytes,
            )

            if response and not self._is_empty_read_did_response(response):
                return response

            if attempt < max_attempts:
                reason = "empty DID data" if response else "no response"
                logging.warning(
                    f"{tc_id} - {step_desc}: {reason}; retrying ReadDID "
                    f"attempt {attempt + 1}/{max_attempts}"
                )
                time.sleep(retry_delay)

        return response

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

                        expected_bytes = [int(b, 16) for b in expected.strip().split()]
                        response = self._send_request_and_wait(
                            client,
                            raw_request,
                            tc_id,
                            step_desc,
                            expected_bytes=expected_bytes,
                        )
                        if not response:
                            raise Exception("No response received")

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

                        special_value = decode_special_did_value(step_desc, raw_data)
                        if special_value is not None:
                            display_value = special_value
                        else:
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
                        ecu_info[step_desc] = "ECU No response"

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

    def run_testcase(self, oled, tester_name="N/A"):
        def stmin_to_seconds(stmin_value):
            return self._stmin_to_seconds(stmin_value)

        def reassemble_isotp_response(first_frame, client, tc_id, step_desc, cf_timeout):
            return self._reassemble_isotp_response(
                first_frame, client, tc_id, step_desc, cf_timeout
            )

        def wait_for_final_response(client, tc_id, step_desc):
            return self._wait_for_final_response(client, tc_id, step_desc)

        def send_request_and_wait(
            client, raw_request, tc_id, step_desc, post_wait=0.0, expected_bytes=None
        ):
            return self._send_request_and_wait(
                client, raw_request, tc_id, step_desc, post_wait, expected_bytes
            )

        if not self.check_memory(oled):
            return

        # The ECU_INFO_* rows are already part of the testcase TXT and will be
        # captured in the main logged execution. Avoid a redundant pre-pass,
        # which doubles those requests and slows the overall run noticeably.
        ecu_info_data = {}
        testcase_file_path = self.get_testcase_file_path()
        base_name = os.path.splitext(os.path.basename(testcase_file_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._prepare_ecu_before_logged_run()
        #self.start_logging(filename=f"{base_name}.asc")
        self.start_logging(filename=f"{base_name}_{timestamp}.asc")
        self._prepare_execution_start()

        grouped_cases = load_testcases(testcase_file_path)
        self.context = {}
        immediate_mode = self.config["uds"].get("immediate_mode", False)
        first_request_pending = True
        for tc_id, steps in grouped_cases.items():

            print("\n")
            logging.info(f"Running Test Case: {tc_id}")
            for step in steps:
                if step[0] == "WAIT":
                    wait_ms = step[1]
                    wait_sec = wait_ms / 1000
                    logging.info(f"WAIT {wait_ms} ms")
                    if wait_sec >= 1:
                        remaining = int(wait_sec)
                        while remaining > 0:
                            message = (
                                f"Waiting...\n"
                                f"{remaining} sec"
                            )
                            oled.display_centered_text(message)
                            print(message)
                            time.sleep(1)
                            remaining -= 1
                    else:
                        message = f"Waiting...\n{wait_ms} ms"
                        oled.display_centered_text(message)
                        print(message)
                        time.sleep(wait_sec)
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
                    if first_request_pending:
                        try:
                            self._drain_sniffer_bus(self.active_conn)
                            logging.info(
                                f"Final CAN drain completed before first testcase {tc_id}"
                            )
                        except Exception as exc:
                            logging.warning(
                                f"Failed final drain before first testcase {tc_id}: {exc}"
                            )
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
                        self.oled_show(oled, f"{tc_id}\n{step_desc}", 0)
                        response = None
                        first_request_pending = False

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
                                    self.oled_show(oled, f"{tc_id}\nSending", 0)

                                # --- Send and receive
                                response = send_request_and_wait(
                                    client, raw_request, tc_id, step_desc
                                )

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
                                    self.oled_show(oled, f"{tc_id}\nHex Error", 2)
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
                                    response = send_request_and_wait(
                                        client, raw_request, tc_id, step_desc
                                    )
                                    time.sleep(1)
                                else:
                                    response = send_request_and_wait(
                                        client, raw_request, tc_id, step_desc
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
                                time.sleep(0.05)
                                response = send_request_and_wait(
                                    client, raw_request, tc_id, step_desc
                                )
                                
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
                                    response = send_request_and_wait(
                                        client, raw_request, tc_id, step_desc
                                    )

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
                                    response = send_request_and_wait(
                                        client, raw_request, tc_id, step_desc
                                    )

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
                                if tc_id.startswith("ECU_INFO"):
                                    response = self._send_read_did_with_retry(
                                        client,
                                        raw_request,
                                        tc_id,
                                        step_desc,
                                        expected_bytes=expected_bytes,
                                        post_wait=0.05,
                                    )
                                else:
                                    response = send_request_and_wait(
                                        client,
                                        raw_request,
                                        tc_id,
                                        step_desc,
                                        post_wait=0.05,
                                        expected_bytes=expected_bytes,
                                    )

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
                                self.oled_show(oled, f"{tc_id}\nHex Error", 2)
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
                            

                            response = send_request_and_wait(
                                client, raw_request, tc_id, step_desc
                            )

                        elif service_int == 0x19:
                            subfunc_bytes = self._hex_field_to_bytes(subfunc)
                            status_mask_bytes = self._hex_field_to_bytes(status_mask)
                            write_data_bytes = self._hex_field_to_bytes(write_data)
                            raw_request = (
                                bytes([0x19])
                                + subfunc_bytes
                                + status_mask_bytes
                                + write_data_bytes
                            )
                            logging.info(
                                f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                            )
                            response_data = send_request_and_wait(
                                client,
                                raw_request,
                                tc_id,
                                step_desc,
                                expected_bytes=expected_bytes,
                            )
                            if response_data:
                                self.verify_response(
                                    list(response_data),
                                    expected_bytes,
                                    tc_id,
                                    step_desc,
                                )
                            else:
                                logging.warning(f"{tc_id} - No response received")

                        # ClearDiagnosticInformation
                        elif service_int == 0x14:
                            if subfunc != "":
                                subfunc_clean = (
                                    subfunc.strip()
                                    .replace("0x", "")
                                    .replace("0X", "")
                                    .replace(",", " ")
                                    .replace("  ", " ")
                                    .replace(" ", "")
                                )
                                if not all(
                                    c in "0123456789abcdefABCDEF"
                                    for c in subfunc_clean
                                ):
                                    raise ValueError(
                                        f"Invalid hex in subfunction: {subfunc}"
                                    )

                                if len(subfunc_clean) % 2 != 0:
                                    subfunc_clean = "0" + subfunc_clean

                                subfunc_bytes = bytes.fromhex(subfunc_clean)
                                raw_request = bytes([0x14]) + subfunc_bytes
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                                )
                                response_data = send_request_and_wait(
                                    client,
                                    raw_request,
                                    tc_id,
                                    step_desc,
                                    expected_bytes=expected_bytes,
                                )
                                if response_data:
                                    self.verify_response(
                                        list(response_data),
                                        expected_bytes,
                                        tc_id,
                                        step_desc,
                                    )
                                else:
                                    logging.warning(f"{tc_id} - No response received")
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
                                response_data = send_request_and_wait(
                                    client,
                                    raw_request,
                                    tc_id,
                                    step_desc,
                                    expected_bytes=expected_bytes,
                                )
                                if response_data:
                                    logging.info(
                                        f"{tc_id} - Received: {response_data.hex().upper()}"
                                    )
                                    self.verify_response(
                                        list(response_data),
                                        expected_bytes,
                                        tc_id,
                                        step_desc,
                                    )
                                else:
                                    logging.warning(f"{tc_id} - No response received")

                        elif service_int == 0x3E:  # TesterPresent
                            if subfunc != "":

                                subfunc_int = int(subfunc, 16)
                                raw_request = bytes([0x3E, subfunc_int])
                                response_data = send_request_and_wait(
                                    client, raw_request, tc_id, step_desc
                                )
                        elif service_int == 0x85:  # ControlDTCSetting
                            try:
                                subfunc_bytes = self._hex_field_to_bytes(subfunc)
                                write_data_bytes = self._hex_field_to_bytes(write_data)
                                raw_request = (
                                    bytes([0x85])
                                    + subfunc_bytes
                                    + write_data_bytes
                                )
                                logging.info(
                                    f"{tc_id} - {step_desc}: Sending {raw_request.hex().upper()}"
                                )
                                response_data = send_request_and_wait(
                                    client, raw_request, tc_id, step_desc, post_wait=0.05
                                )

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
                                    f"{tc_id} - Invalid hex in 0x85 request fields: {ve}"
                                )
                            except Exception as e:
                                logging.error(
                                    f"{tc_id} - Exception: {type(e).__name__} - {str(e)}"
                                )

                        elif subfunc == "":

                            subfunc_clean = subfunc.strip()
                            subfunc_bytes = (
                                bytes.fromhex(subfunc_clean) if subfunc_clean else b""
                            )
                            expected_bytes = [
                                int(b, 16) for b in expected.strip().split()
                            ]
                            raw_request = bytearray([service_int]) + subfunc_bytes
                            response_data = send_request_and_wait(
                                client, raw_request, tc_id, step_desc
                            )

                        elif service_int == 0x27:
                            subfunc_bytes = self._hex_field_to_bytes(subfunc)
                            if subfunc == "":
                                raw_request = bytearray([service_int]) + subfunc_bytes
                                response_data = send_request_and_wait(
                                    client, raw_request, tc_id, step_desc
                                )
                            elif len(subfunc_bytes) != 1:
                                raw_request = bytes([0x27]) + subfunc_bytes
                                response = send_request_and_wait(
                                    client, raw_request, tc_id, step_desc
                                )
                            else:
                                subfunc_int = subfunc_bytes[0]
                                if subfunc_int % 2 == 1:  # requestSeed
                                    raw_request = bytes([0x27, subfunc_int])
                                    response = send_request_and_wait(
                                        client,
                                        raw_request,
                                        tc_id,
                                        step_desc,
                                        expected_bytes=expected_bytes,
                                    )
                                    raw_payload = list(response)
                                    logging.debug(
                                        f"{tc_id} {step_desc} -> Received payload: {raw_payload}"
                                    )
                                    status, failure_reason = self.verify_response(
                                        raw_payload,
                                        expected_bytes,
                                        tc_id,
                                        step_desc,
                                    )
                                    if status != "Pass" and raw_payload and raw_payload[0] == 0x7F:
                                        logging.warning(
                                            f"{tc_id} {step_desc} -> FAIL - {failure_reason}"
                                        )
                                        raise Exception(failure_reason)
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
                                    response = send_request_and_wait(
                                        client,
                                        raw_request,
                                        tc_id,
                                        step_desc,
                                        expected_bytes=expected_bytes,
                                    )

                                    raw_payload = list(response)
                                    logging.debug(
                                        f"{tc_id} {step_desc} -> Received payload: {raw_payload}"
                                    )
                                    status, failure_reason = self.verify_response(
                                        raw_payload,
                                        expected_bytes,
                                        tc_id,
                                        step_desc,
                                    )
                                    if status == "Pass":
                                        continue

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
                                    subfunc_bytes = self._hex_field_to_bytes(subfunc)
                                    communication_type_bytes = self._hex_field_to_bytes(
                                        communication_type
                                    )
                                    write_data_bytes = self._hex_field_to_bytes(write_data)

                                    if not communication_type_bytes and subfunc_bytes:
                                        # Normal 0x28 requests need communicationType after controlType.
                                        communication_type_bytes = subfunc_bytes[-1:]

                                    raw_request = (
                                        bytes([0x28])
                                        + subfunc_bytes
                                        + communication_type_bytes
                                        + write_data_bytes
                                    )
                                    logging.info(
                                        f"{tc_id} - {step_desc}: Sending raw request {raw_request.hex().upper()}"
                                    )
                                    response = send_request_and_wait(
                                        client, raw_request, tc_id, step_desc
                                    )

                                except ValueError as exc:
                                    logging.error(
                                        f"{tc_id} - Invalid 0x28 request fields: {exc}"
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
                                response_data = send_request_and_wait(
                                    client, raw_request, tc_id, step_desc
                                )

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
        test_start_time = self.can_logger.get_log_start_time()
        test_end_time = self.can_logger.get_log_end_time()
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

        report_dir = os.path.join(self.repo_path, "output", "html_reports")
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
            ecu_info_field_map=self.info_dids,
            tester_name=tester_name,
            input_json_file=self.config_path,
            test_start_time=test_start_time,
            test_end_time=test_end_time,
        )

        oled.display_centered_text("Report Generated")
        logging.info(
            "----------------------------------Report Generated----------------------------------"
        )

        time.sleep(2)
