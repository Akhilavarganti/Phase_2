import csv
from collections import defaultdict

HEADER_ALIASES = {
    "TC_ID": ["TC_ID/PC_ID", "TC_ID", "PC_ID"],
    "DESCRIPTION": ["Testcase_Description", "Description", "Test Description"],
    "SERVICE": ["Service_ID", "SID", "Service"],
    "SUBFUNC": ["SubService_ID", "SubFunction", "DID"],
    "EXPECTED": ["Expected_Response_Data", "Expected", "Response"],
    "WRITE": ["Write_Data", "Data", "Payload"],
    "ADDRESSING": ["Addressing", "Mode"],
    "FORMAT": ["Format"],
    "STATUS_MASK": ["Status_Mask", "StatusMask"],
    "COMM_TYPE": ["Communication_Type", "CommunicationType"],
    "CONTROLTYPE": ["controltype", "ControlType"],
}
def find_column(col, aliases, required=True):
    for alias in aliases:
        if alias in col:
            return col[alias]
    if required:
        raise KeyError(f"Column not found. Tried: {aliases}")
    return None
grouped_cases = defaultdict(list)

def normalize_row(row, header_len, description_idx):
    if len(row) > header_len and description_idx is not None:
        extra_count = len(row) - header_len
        merged_description = ",".join(
            row[description_idx : description_idx + extra_count + 1]
        )
        row = (
            row[:description_idx]
            + [merged_description]
            + row[description_idx + extra_count + 1 :]
        )

    if len(row) < header_len:
        row = row + [""] * (header_len - len(row))

    return row

def load_testcases(file_path):
    grouped_cases.clear()
    try:
        with open(file_path, "r", newline="") as f:
            reader = csv.reader(f)
            header = []
            for row in reader:
                candidate = [h.strip().lstrip("#").lstrip("\ufeff") for h in row]
                if "TC_ID/PC_ID" in candidate or "TC_ID" in candidate:
                    header = candidate
                    break

            if not header:
                raise ValueError("TXT header row not found")

            col = {
                name : idx
                for idx, name in enumerate(header)
            }
            description_idx = find_column(
                col,
                HEADER_ALIASES["DESCRIPTION"],
                required=False
            )
            
            current_tc_id = None
            for row in reader:
                if not row:
                    continue  # Skip empty or malformed lines
                row = normalize_row(row, len(header), description_idx)
                row_values = [str(cell).strip().upper() for cell in row]
                cmd = None
                if "WAIT" in row_values:
                    cmd = "WAIT"       
                if cmd == "WAIT":
                    if current_tc_id:
                        wait_index = row_values.index("WAIT")
                        wait_value = row[wait_index + 1].strip()
                        grouped_cases[current_tc_id].append(
                            (
                                "WAIT",
                                int(wait_value, 16)
                            )
                        )
                    continue    
                if len(row) < 5:
                    continue

                tc_id = row[find_column(col, HEADER_ALIASES["TC_ID"])].strip()
                current_tc_id = tc_id
                step_desc = row[find_column(col, HEADER_ALIASES["DESCRIPTION"])].strip()
                service_id = row[find_column(col, HEADER_ALIASES["SERVICE"])].strip()
                subfunction_or_did = row[find_column(col, HEADER_ALIASES["SUBFUNC"])].strip()
                expected_response = row[find_column(col, HEADER_ALIASES["EXPECTED"])].strip()
                write_data = row[find_column(col, HEADER_ALIASES["WRITE"])].strip()
                addressing = row[find_column(col, HEADER_ALIASES["ADDRESSING"])].strip().lower()
                format_type = row[find_column(col, HEADER_ALIASES["FORMAT"])].strip()
                status_mask_idx = find_column(
                    col,
                    HEADER_ALIASES["STATUS_MASK"],
                    required=False
                )
                communication_type_idx = find_column(
                    col,
                    HEADER_ALIASES["COMM_TYPE"],
                    required=False
                )
                controltype_idx = find_column(
                    col,
                    HEADER_ALIASES["CONTROLTYPE"],
                    required=False
                )
                status_mask = (
                    row[status_mask_idx].strip()
                    if status_mask_idx is not None and status_mask_idx < len(row)
                    else ""
                )
                communication_type = (
                    row[communication_type_idx].strip()
                    if communication_type_idx is not None and communication_type_idx < len(row)
                    else ""
                )
                controltype = (
                    row[controltype_idx].strip()
                    if controltype_idx is not None and controltype_idx < len(row)
                    else ""
                )

                grouped_cases[tc_id].append(
                    (
                        tc_id,
                        step_desc,
                        service_id,
                        subfunction_or_did,
                        expected_response,
                        write_data,
                        addressing,
                        format_type,
                        status_mask,
                        communication_type,
                        controltype,
                    )
                )

        return grouped_cases

    except Exception as e:
        print(f"Error parsing testcases: {e}")
        return {}
