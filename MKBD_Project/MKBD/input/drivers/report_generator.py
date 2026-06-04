import os
import re
import datetime
from collections import defaultdict
from html import escape

ALLOWED_IDS={"716","71E","7DF"}

def load_description_map(txt_file_path):
    desc_map = {}
    with open(txt_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.lower().startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 8:
                continue
            tc_id = parts[0].strip()
            description = parts[1].strip()
            sid = parts[2].strip().replace("0x", "").upper()
            sub = parts[3].strip().replace("0x", "").upper()
            expected_response_data = parts[4].strip()
            # Convert expected response data (e.g., "0x10 0x0B 0x62") to byte list
            expected_bytes = [b.replace("0x", "").upper() for b in expected_response_data.split() if b]
            format_type = parts[7].strip().capitalize() if len(parts) > 7 else "Hex"
            key = (sid, sub)
            value = (description, tc_id, expected_bytes, format_type)
            if key not in desc_map:
                desc_map[key] = []
            desc_map[key].append(value)
    return desc_map


def parse_data_bytes(line):
    try:
        parts = line.strip().split()
        # Find the first occurrence of 8-byte payload: starts after the second '8'
        index = [i for i, x in enumerate(parts) if x == '8']
        if len(index) >= 2:
            start = index[1] + 1
            return parts[start:start+8]
    except:
        pass
    return []




def get_description(data_bytes):
    if not data_bytes or len(data_bytes) < 1:
        return "", "", "", ""
    
    # Known UDS SIDs — extend as needed
    known_sids = {"10", "11", "22", "2E", "19", "27", "28", "3E", "31", "14", "85"}
    sid_index = -1
    sid = ""
    for i, byte in enumerate(data_bytes):
        if byte.upper() in known_sids:
            sid_index = i
            sid = byte.upper()
            break

    if sid_index == -1:
        return "", "", "", ""

    # Try matching with subfunction (3, 2, or 1 bytes)
# Try all possible subfunction/DID lengths
    for length in (3, 2, 1, 0):  # Added 0 to handle cases with only SID
        if sid_index + length < len(data_bytes):
            sub = ''.join(data_bytes[sid_index + 1: sid_index + 1 + length]).upper() if length > 0 else ""
            key = (sid, sub)
            if key in DESCRIPTION_MAP:
                used = getattr(get_description, "used_tc_ids", set())
                for desc, tc_id, expected_resp, fmt in DESCRIPTION_MAP[key]:
                    if tc_id not in used:
                        used.add(tc_id)
                        setattr(get_description, "used_tc_ids", used)
                        return desc, tc_id, expected_resp, fmt
                return DESCRIPTION_MAP[key][0]

    # Try fallback: SID only
    key = (sid, "")
    if key in DESCRIPTION_MAP:
        used = getattr(get_description, "used_tc_ids", set())
        for desc, tc_id, expected_resp in DESCRIPTION_MAP[key]:
            if tc_id not in used:
                used.add(tc_id)
                setattr(get_description, "used_tc_ids", used)
                return desc, tc_id, expected_resp
        return DESCRIPTION_MAP[key][0]

    return "", "", "", ""





def get_failure_reason(nrc):
    reasons = {
        "10" : "generalReject",
        "11" : "serviceNotSupported",
        "12" : "subFunctionNotSupported",
        "13" : "incorrectMessageLengthOrInvalidFormat",
        "14" : "responseTooLong",
        "21" : "busyRepeatReques",
        "22" : "conditionsNotCorrect",
        "23" : "ISOSAEReserved",
        "24" : "requestSequenceError",
        "31" : "requestOutOfRange",
        "32" : "ISOSAEReserved",
        "33" : "securityAccessDenied",
        "34" : "ISOSAEReserved",
        "35" : "invalidKey",
        "36" : "exceedNumberOfAttempts",
        "37" : "requiredTimeDelayNotExpired",
        "70" : "uploadDownloadNotAccepted",
        "71" : "transferDataSuspended",
        "72" : "generalProgrammingFailure",
        "73" : "wrongBlockSequenceCounter",
        "78" : "requestCorrectlyReceived-ResponsePending",
        "7E" : "subFunctionNotSupportedInActiveSession",
        "7F" : "serviceNotSupportedInActiveSession",
        "80" : "ISOSAEReserved",
        "81" : "rpmTooHigh",
        "82" : "rpmTooLow",
        "83" : "engineIsRunning",
        "84" : "engineIsNotRunning",
        "85" : "engineRunTimeTooLow",
        "86" : "temperatureTooHigh",
        "87" : "temperatureTooLow",
        "88" : "vehicleSpeedTooHigh",
        "89" : "vehicleSpeedTooLow",
        "8A" : "throttle/PedalTooHigh",
        "8B" : "throttle/PedalTooLow",
        "8C" : "transmissionRangeNotInNeutral",
        "8D" : "transmissionRangeNotInGear",
        "8E" : "ISOSAEReserved",
        "8F" : "brakeSwitch(es)NotClosed (Brake Pedal not pressed or not applied)",
        "90" : "shifterLeverNotInPark",
        "91" : "torqueConverterClutchLocked",
        "92" : "voltageTooHigh",
        "93" : "voltageTooLow",
        "FF" : "ISOSAEReserved",
    }
    return reasons.get(nrc.upper(), f"Unknown NRC: {nrc}")

def get_status(actual_data, expected_response_data):
    """
    Determines Pass/Fail by comparing full actual vs expected response.
    Handles negative responses with NRCs too.
    """
    if not actual_data:
        return "Fail", "No response received"
    if not expected_response_data:
        return "Fail", "Expected response not specified"

    actual_data = [b.strip().upper() for b in actual_data if isinstance(b, str)]
    expected_data = [b.strip().upper() for b in expected_response_data if isinstance(b, str)]

    # ✅ Match full byte-by-byte
    if actual_data == expected_data:
        return "Pass", ""

    # 🟥 Negative Response Handling
    if len(actual_data) >= 4 and actual_data[1] == "7F":
        nrc = actual_data[3]
        return "Fail", f"Negative Response (0x{nrc}: {get_failure_reason(nrc)})"

    return "Fail", "Response mismatch"





def parse_line(line):
    line = line.strip()
    if not line or "CANFD" not in line:
        return None

    parts = line.split()
    try:
        timestamp = float(parts[0])
    except:
        return None

    direction = parts[3]
    if direction not in ("Tx", "Rx"):
        direction = "Tx" if "Tx" in line else "Rx" if "Rx" in line else direction

    return {
        "timestamp": timestamp,
        "can_id": parts[4].upper(),
        "direction": direction,
        "data_bytes": parse_data_bytes(line),
        "raw": line
    }



def parse_asc_file(asc_file_path, allowed_tx_ids, allowed_rx_ids):
    messages_by_tc = defaultdict(list)
    current_request = None
    pending_first_frame = None
    assembling_request = False
    request_buffer = []
    total_req_len = 0

    awaiting_response = False
    response_buffer = []
    total_resp_len = 0
    collected_len = 0
    pending_flag = False

    start_ts, end_ts = None, None
    skip_next_fc = False
    pending_flag = False
    rx_multi_response_pending = False
    rx_multi_response_first = None
    base_datetime = None

    allowed_tx_ids = set(f"{id:X}" for id in allowed_tx_ids)
    allowed_rx_ids = set(f"{id:X}" for id in allowed_rx_ids)

    with open(asc_file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # Extract base datetime from "Begin Triggerblock ..."
    for line in lines:
        if line.startswith("Begin Triggerblock"):
            try:
                date_str = line.strip().replace("Begin Triggerblock ", "")
                base_datetime = datetime.datetime.strptime(date_str, "%a %b %d %I:%M:%S.%f %p %Y")
            except ValueError:
                base_datetime = None
            break

    for line in lines:
        line = line.strip()
        if not line or not re.match(r"^\d+\.\d+", line):
            continue

        msg = parse_line(line)
        if not msg:
            print(f"[❌] Failed to parse line:\n{line}")
            continue  # Skip to the next line

        #print(f"[DEBUG] Parsed Msg → ID: {msg['can_id']} Dir: {msg['direction']} Data: {msg['data_bytes']}")

        if not msg:
            #print(f"❌ Failed to parse line: {line}")
            continue

        if msg["can_id"] not in ALLOWED_IDS:
            continue

        can_id = msg["can_id"]
        direction = msg["direction"]
        data = msg["data_bytes"]

        if not data:
            #print(f"⚠️ No data in line: {line}")
            continue

        pci_type = data[0].upper()

        # ▶️ Tx: Handle Request
        if direction == "Tx" and can_id in {"716", "7DF"}:
            #print(f"✅ Parsed line: ID={can_id}, dir={direction}, data={data}")
            if pci_type == "10":  # First Frame
                assembling_request = True
                total_req_len = int(data[1], 16)
                request_buffer = data[2:]
                pending_first_frame = msg
                continue

            elif assembling_request and pci_type.startswith("2"):  # Consecutive Frame
                request_buffer += data[1:]
                if len(request_buffer) >= total_req_len:
                    trimmed_data = request_buffer[:total_req_len]
                    desc, tc_id, expected_resp, fmt = get_description(trimmed_data)
                    if desc and tc_id:
                        current_request = {
                            "timestamp": pending_first_frame["timestamp"],
                            "can_id": pending_first_frame["can_id"],
                            "direction": "Tx",
                            "data_bytes": trimmed_data,
                            "desc": desc,
                            "tc_id": tc_id,
                            "format": fmt,
                            "expected_resp": expected_resp,
                            "status": "Pending"
                        }
                        #print(f"📦 Multi-frame Request TC={tc_id} matched")
                    assembling_request = False
                    request_buffer = []
                    pending_first_frame = None
                continue

            else:  # Single Frame
                desc, tc_id, expected_resp, fmt = get_description(data)
                if desc and tc_id:
                    current_request = {
                        "timestamp": msg["timestamp"],
                        "can_id": can_id,
                        "direction": direction,
                        "data_bytes": data,
                        "desc": desc,
                        "tc_id": tc_id,
                        "format": fmt,
                        "expected_resp": expected_resp,
                        "status": "Pending"
                    }
                    #print(f"✅ Single-frame Request TC={tc_id} matched")

        # ◀️ Rx: Handle Response
        elif direction == "Rx" and can_id == "71E" and current_request:

            if pci_type == "30":  # Flow control
                #print("⚙️ Skipping flow control frame")
                continue

            # Skip 0x7F xx 78 (Response Pending)
            if len(data) >= 4 and data[1].upper() == "7F" and data[3].upper() == "78":
                #print("⏳ Skipping pending response (7F xx 78)")
                continue

            if pci_type == "10":  # First frame of multi-frame response
                total_resp_len = int(data[1], 16)
                response_buffer = data[:]
                collected_len = len(data) - 2
                awaiting_response = True
                continue

            elif pci_type.startswith("2") and awaiting_response:
                response_buffer += data[1:]
                collected_len += len(data) - 1
                if collected_len >= total_resp_len:
                    full_resp = response_buffer
                    awaiting_response = False
                else:
                    continue
            else:
                if awaiting_response:
                    response_buffer += data[1:]
                    full_resp = response_buffer
                    awaiting_response = False
                else:
                    full_resp = data

            # ✅ Evaluate response
            status, reason = get_status(full_resp, current_request["expected_resp"])
            current_request.update({
                "response": msg,
                "response_data_bytes": full_resp,
                "status": status,
                "failure_reason": reason
            })

            messages_by_tc[current_request["tc_id"]].append(current_request)

            # Update timestamps
            start_ts = min(start_ts or msg["timestamp"], current_request["timestamp"])
            end_ts = max(end_ts or msg["timestamp"], msg["timestamp"])

            current_request = None
            response_buffer = []

    return messages_by_tc, start_ts or 0, end_ts or 0, base_datetime
















import datetime
from html import escape

def flatten_bytes(data):
    flat = []
    for item in data:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat

def remove_trailing_padding(data_list, pad_byte):
    # Remove only trailing occurrences of pad_byte (like "00" or "AA")
    i = len(data_list)
    while i > 0 and data_list[i - 1].upper() == pad_byte.upper():
        i -= 1
    return data_list[:i]

def get_valid_request_data(data_bytes):
    """
    Extracts the actual data from a UDS request.
    Assumes the first byte is the PCI, which tells us how many bytes follow.
    """
    
    if not data_bytes:
        return data_bytes
    try:
        pci = int(data_bytes[0], 16)
        if pci <= 0x07:
            # Single-frame: first byte is length of remaining data
            total_len = pci + 1  # include PCI itself
            return data_bytes[:total_len]
    except:
        pass
    return data_bytes





def generate_html_report(messages_by_tc, output_path, asc_filename, start_ts, end_ts, ecu_info_data=None, target_ecu=None, base_datetime=None):
    def remove_padding(data_list, pad_byte):
        return [byte for byte in data_list if byte.upper() != pad_byte.upper()]

    total = len(messages_by_tc)
    passed = sum(1 for tc in messages_by_tc.values() if all(msg["status"] == "Pass" for msg in tc))
    failed = total - passed
    duration = end_ts - start_ts
    generated_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format Start_Timestamp and End_Timestamp
    if base_datetime:
        start_dt = base_datetime + datetime.timedelta(seconds=start_ts)
        end_dt = base_datetime + datetime.timedelta(seconds=end_ts)
        Start_Timestamp = start_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        End_Timestamp = end_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    else:
        Start_Timestamp = f"{start_ts:.3f} seconds"
        End_Timestamp = f"{end_ts:.3f} seconds"

    html = f"""<!DOCTYPE html>
<html>
<head><title>UDS Diagnostic Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: Arial; margin: 20px; }}
  .pass {{ color: green; font-weight: bold; }}
  .fail {{ color: red; font-weight: bold; }}
  .wrapper {{
    display: flex;
    justify-content: center;
    align-items: flex-start;
    gap: 50px;
    margin-top: 20px;
  }}
  .summary-block {{ text-align: left; min-width: 250px; }}
  #chart-container {{ width: 300px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
  th, td {{ border: 1px solid #ccc; padding: 8px; }}
  th {{ background: #f0f0f0; }}
  summary {{ font-weight: bold; cursor: pointer; }}
</style>
</head>
<body>

<h1 style="text-align: center;">UDS Diagnostic Report</h1>

<div style="display: flex; justify-content: flex-start; align-items: flex-start; gap: 40px; margin-top: 20px; padding-left: 10px;">
    <div style="width: 650px;">
    
        {f"<p><strong>Target ECU:</strong> {escape(target_ecu)}</p>" if target_ecu else ""}
        {"".join(f"<p><strong>{escape(k)}:</strong> {escape(v)}</p>" for k, v in ecu_info_data.items()) if ecu_info_data else ""}
        
        <hr style="width: 300px;border:1px solid #999; margin:25px 0;">
        
        <p><strong>Generated:</strong> {generated_time}</p>
        <p><strong>CAN Log File:</strong> {asc_filename}</p>
        <p><strong>Total Test Cases:</strong> {total}</p>
        <p class="pass"><strong>Passed:</strong> {passed}</p>
        <p class="fail"><strong>Failed:</strong> {failed}</p>
        <p><strong>Start_Time:</strong> {Start_Timestamp}</p>
        <p><strong>End_Time:</strong> {End_Timestamp}</p>
        <p><strong>Test Duration:</strong> {duration:.3f} seconds</p>
        
    </div>
    <button onclick="document.querySelectorAll('.case-block').forEach(el => el.style.display='');">Show All</button>
    <div id="chart-container" style="width: 320px; margin-left:70px;">
        <canvas id="passFailChart" width="300" height="300"></canvas>
    </div>
</div>

    <script>
        const ctx = document.getElementById('passFailChart').getContext('2d');
        const chart = new Chart(ctx, {{
            type: 'pie',
            data: {{
                labels: ['Passed', 'Failed'],
                datasets: [{{
                    data: [{passed}, {failed}],
                    backgroundColor: ['#4CAF50', '#F44336']
                }}]
            }},
            options: {{
                responsive: true,
                onClick: function (evt, item) {{
                    const segment = chart.getElementsAtEventForMode(evt, 'nearest', {{ intersect: true }}, true);
                    if (!segment.length) return;
                    const label = chart.data.labels[segment[0].index];
                    document.querySelectorAll('.case-block').forEach(el => el.style.display = 'none');
                    if (label === 'Passed') {{
                        document.querySelectorAll('.pass-case').forEach(el => el.style.display = '');
                    }} else if (label === 'Failed') {{
                        document.querySelectorAll('.fail-case').forEach(el => el.style.display = '');
                    }}
                }},
                plugins: {{
                    legend: {{ position: 'bottom' }},
                    title: {{ display: true, text: 'Test Case Results' }}
                }}
            }}
        }});
    </script>

    <hr><br>
    """

    for tc_id, steps in messages_by_tc.items():
        status = steps[0]['status']
        status_class = 'pass' if status == 'Pass' else 'fail' if status == 'Fail' else 'pending'
        html += f"<div class='case-block {status_class}-case'>\n"
        html += f"<details><summary>{tc_id} - <span class='{status_class}'>{status}</span></summary>\n"
        html += """<table><tr><th>Step</th><th>Description</th><th>Timestamp</th><th>Type</th><th>Data</th><th>Status</th><th>Failure Reason</th></tr>\n"""
        
        step_count = 1
        for msg in steps:
            desc = msg['desc']
            combined_desc = ""

            if "PreCondition:" in desc and "Testcase" in desc:
                parts = desc.split("PreCondition:", 1)[1].split("Testcase", 1)
                pre_detail = parts[0].strip()
                tc_detail = parts[1].strip()
                combined_desc = f"<b>PreCondition:</b> {escape(pre_detail)}<br><b>Testcase:</b>{escape(tc_detail)}"
            elif "PreCondition:" in desc:
                pre_detail = desc.split("PreCondition:", 1)[1].strip()
                combined_desc = f"<b>PreCondition:</b> {escape(pre_detail)}"
            else:
                combined_desc = escape(desc.strip())
            
            req_bytes = remove_trailing_padding(msg.get('data_bytes', []), "00")
            req_data = get_valid_request_data(msg.get('data_bytes', []))
            req_data_str = ' '.join(flatten_bytes(req_data))
            Expected_resp= get_valid_request_data(msg.get('expected_resp', []))
            Expected_resp_str = ' '.join(flatten_bytes(Expected_resp))
            
            html += f"<tr><td>{step_count}</td><td>{escape(msg['desc'])}</td><td>{msg['timestamp']:.6f}</td><td>Request Sent</td><td>{req_data_str}</td><td></td><td>-</td></tr>\n"
            step_count += 1
            html += f"<tr><td>{step_count}</td><td></td><td></td><td>Expected_data</td><td>{Expected_resp_str}</td><td></td><td>-</td></tr>\n"
            step_count += 1

            response = msg.get("response", {})
            raw_resp = msg.get("response_data_bytes", response.get("data_bytes", []))
            # Remove padding (AA) from response
            clean_resp = remove_trailing_padding(raw_resp, "AA")
            format_type = msg.get("format", "Hex").strip().lower()
            try:
                full_hex_str = ' '.join(clean_resp)
                # Default: full clean response if parsing fails
                payload = clean_resp

                # Locate 0x62 and skip SID + DID
                if "62" in [b.upper() for b in clean_resp]:
                    idx = next(i for i, b in enumerate(clean_resp) if b.upper() == "62")
                    if len(clean_resp) > idx + 2:
                        payload = clean_resp[idx + 3:]
                    else:
                        payload = []
                else:
                    payload = clean_resp

                # Format conversion
                if format_type == "ascii":
                    ascii_str = ''.join(chr(int(b, 16)) for b in payload if 32 <= int(b, 16) <= 126)
                    response_data_str = f"{full_hex_str} → {ascii_str}" if ascii_str else full_hex_str

                elif format_type == "decimal":
                    decimal_str = ' '.join(str(int(b, 16)) for b in payload)
                    response_data_str = f"{full_hex_str} → {decimal_str}" if decimal_str else full_hex_str

                else:  # default hex
                    response_data_str = full_hex_str

            except Exception:
                response_data_str = ' '.join(clean_resp)

            html += f"<tr><td>{step_count}</td><td></td><td>{response.get('timestamp', 0):.6f}</td><td>Response Received</td><td>{response_data_str}</td><td>{msg['status']}</td><td>{msg.get('failure_reason', '')}</td></tr>\n"
            step_count += 1
        
        html += "</table></details></div>\n"

    html += "</body></html>"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ UDS HTML Report generated at:\n{output_path}\n")

def generate_report(asc_file_path, txt_file_path, output_html_file, allowed_tx_ids, allowed_rx_ids, ecu_info_data=None, target_ecu=None):
    global DESCRIPTION_MAP
    DESCRIPTION_MAP = load_description_map(txt_file_path)
    get_description.used_tc_ids = set()

    messages_by_tc, start_ts, end_ts, base_datetime = parse_asc_file(
        asc_file_path, allowed_tx_ids, allowed_rx_ids
    )

    report_path = output_html_file

    generate_html_report(
        messages_by_tc,
        report_path,
        os.path.basename(asc_file_path),
        start_ts,
        end_ts,
        ecu_info_data,
        target_ecu,
        base_datetime
    )
