import os
import re
import datetime
from collections import defaultdict
from html import escape
import logging

DESCRIPTION_MAP = {}

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
            expected_bytes = [b.replace("0x", "").upper() for b in expected_response_data.split() if b]
            format_type = parts[7].strip().capitalize() if len(parts) > 7 else "Hex"
            key = (sid, sub)
            value = (description, tc_id, expected_bytes, format_type)
            if key not in desc_map:
                desc_map[key] = []
            desc_map[key].append(value)
    return desc_map


def parse_data_bytes(line, ctype):
    if ctype == "CANFD":
       try:
           parts = line.strip().split()
           # Find the first occurrence of 8-byte payload: starts after the second '8'
           index = [i for i, x in enumerate(parts) if x == '8']
           if len(index) >= 2:
               start = index[1] + 1
               return parts[start:start+8]
       except:
             pass
    if ctype == "CAN":
       try:
           match = re.search(r'd\s+\d+\s+((?:[0-9A-Fa-f]{2}(?:\s+|$))+)', line)
           if match:
               return match.group(1).strip().split()

       except:
             pass
    return []




def get_description(data_bytes):
    if not data_bytes or len(data_bytes) < 1:
        return "", "", "", ""
    
    # Known UDS SIDs — extend as needed
    known_sids = {"10", "11", "22", "2E", "19", "27", "28","2F", "3E", "31", "14", "85"}
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

    actual_data_t = [b.strip().upper() for b in actual_data if isinstance(b, str)]
    expected_data_t = [b.strip().upper() for b in expected_response_data if isinstance(b, str)]

    # Remove padding (AA and 00) from response
    clean_resp_t = remove_trailing_padding(actual_data_t, "00")
    actual_data = remove_trailing_padding(clean_resp_t, "AA")
    # Remove padding (AA and 00) from expected response
    E_clean_resp_t = remove_trailing_padding(expected_data_t, "00")
    expected_data = remove_trailing_padding(E_clean_resp_t, "AA")

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
    if not line or ("CANFD" not in line and " d " not in line):
        return None

    parts = line.split()
    try:
        timestamp = float(parts[0])
        direction = parts[3]
        if "CANFD" in line:
            can_id = parts[4].upper()
            ctype = "CANFD"
        if "d" in line:
            can_id = parts[2].upper()
            ctype = "CAN"
    except:
        return None
    if direction not in ("Tx", "Rx"):
               direction = "Tx" if "Tx" in line else "Rx" if "Rx" in line else direction

    return {
        "timestamp": timestamp,
        "can_id": can_id,
        "direction": direction,
        "data_bytes": parse_data_bytes(line, ctype),
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
    skip_next_fc = False
    pending_flag = False

    start_ts, end_ts = None, None
    base_datetime = None



    allowed_tx_ids = set(f"{id:X}" for id in allowed_tx_ids)
    allowed_rx_ids = set(f"{id:X}" for id in allowed_rx_ids)
    
    ALLOWED_IDS = allowed_tx_ids | allowed_rx_ids
    
    with open(asc_file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
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

        msg = parse_line(line)  # ✅ This was incorrectly indented before
        if not msg or msg["can_id"] not in ALLOWED_IDS:
            continue

        can_id = msg["can_id"]
        direction = msg["direction"]
        data = msg["data_bytes"]
        
        # 🟦 Tx: Handle Request
        if direction == "Tx" and can_id in allowed_tx_ids:
            pci_type = data[0].upper()

            if pci_type == "10":  # First Frame of Multi-Frame Request
                assembling_request = True
                total_req_len = int(data[1], 16)
                request_buffer = data[2:]
                pending_first_frame = msg
                skip_next_fc = True
                continue

            elif skip_next_fc and pci_type == "30":
                skip_next_fc = False
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
                    assembling_request = False
                    request_buffer = []
                    pending_first_frame = None
                continue

            else:  # Single-Frame Request
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

        # ◀️ Rx: Handle Response
        elif direction == "Rx" and can_id in allowed_rx_ids and current_request:
            pci_type = data[0].upper()

            if pci_type == "30":
                continue  # Ignore flow control

            # Handle 0x7F xx 78 pending response
            if len(data) >= 4 and data[1].upper() == "7F" and data[3].upper() == "78":
                pending_flag = True
                continue  # Ignore pending response

            if pending_flag:
                pending_flag = False
                full_resp = data  # Treat next frame as actual response
            else:
                if pci_type == "10":  # First frame of multi-frame response
                    total_resp_len = int(data[1], 16)
                    response_buffer = data[:]  # include full frame including PCI
                    collected_len = len(data) - 2  # remove PCI and LEN from payload count
                    awaiting_response = True
                    continue

                elif pci_type.startswith("2") and awaiting_response:
                    response_buffer += data[1:]  # exclude PCI
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

# stage.............

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

# stage.............

def generate_html_report(messages_by_tc, output_path, asc_filename, start_ts, end_ts, ecu_info_data=None, target_ecu=None, base_datetime=None):

    total = len(messages_by_tc)
    passed = sum(1 for tc in messages_by_tc.values() if all(msg["status"] == "Pass" for msg in tc))
    failed = total - passed
    duration = end_ts - start_ts
    generated_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html>
<head>
<title>UDS Diagnostic Report</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body {{ font-family: Arial; margin: 20px; }}
h1 {{ text-align: center; }}

.pass {{ color: green; font-weight: bold; }}
.fail {{ color: red; font-weight: bold; }}

table {{
    border-collapse: collapse;
    width: 100%;
    margin-top: 10px;
}}

th, td {{
    border: 1px solid #ccc;
    padding: 8px;
}}

th {{ background: #f2f2f2; }}

.case {{
    border: 1px solid #aaa;
    margin-top: 15px;
    padding: 10px;
}}

</style>
</head>

<body>

<h1>UDS Diagnostic Report</h1>

<p><b>File:</b> {asc_filename}</p>
<p><b>Generated:</b> {generated_time}</p>
<p><b>Total:</b> {total}</p>
<p class="pass"><b>Passed:</b> {passed}</p>
<p class="fail"><b>Failed:</b> {failed}</p>
<p><b>Duration:</b> {duration:.3f} sec</p>

<canvas id="chart" width="200" height="200"></canvas>

<script>
var ctx = document.getElementById('chart').getContext('2d');
new Chart(ctx, {{
    type: 'pie',
    data: {{
        labels: ['Pass', 'Fail'],
        datasets: [{{
            data: [{passed}, {failed}],
            backgroundColor: ['green','red']
        }}]
    }}
}});
</script>

<hr>
"""

    # =========================
    # IMPROVED TESTCASE DISPLAY
    # =========================
    for tc_id, steps in messages_by_tc.items():

        status = steps[0]["status"]
        status_class = "pass" if status == "Pass" else "fail"

        html += f"""
<div class="case">
<h3>{tc_id} - <span class="{status_class}">{status}</span></h3>

<table>
<tr>
<th>Step</th>
<th>Description</th>
<th>Request</th>
<th>Expected</th>
<th>Actual</th>
<th>Status</th>
<th>Reason</th>
</tr>
"""

        step_no = 1

        for msg in steps:

            desc = msg.get("desc", "")

            # ✅ CLEAN REQUEST
            req = " ".join(get_valid_request_data(msg.get("data_bytes", [])))

            # ✅ EXPECTED
            exp = " ".join(msg.get("expected_resp", []))

            # ✅ ACTUAL RESPONSE
            act = " ".join(msg.get("response_data_bytes", [])) if msg.get("response_data_bytes") else "N/A"

            status = msg.get("status", "")
            reason = msg.get("failure_reason", "")

            row_class = "pass" if status == "Pass" else "fail"

            html += f"""
<tr>
<td>{step_no}</td>
<td>{escape(desc)}</td>
<td>{req}</td>
<td>{exp}</td>
<td>{act}</td>
<td class="{row_class}">{status}</td>
<td>{escape(reason)}</td>
</tr>
"""

            step_no += 1

        html += "</table></div>"

    html += "</body></html>"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Report Generated:", output_path)
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
