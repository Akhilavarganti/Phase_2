def _normalize_desc(desc):
    return (
        (desc or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def _normalize_hex_bytes(payload):
    normalized = []
    for byte in payload or []:
        if isinstance(byte, int):
            normalized.append(f"{byte:02X}")
        elif isinstance(byte, str):
            normalized.append(byte.strip().upper())
    return [byte for byte in normalized if byte]


def _strip_positive_response_header(payload):
    clean_payload = _normalize_hex_bytes(payload)

    if not clean_payload:
        return []

    if len(clean_payload) >= 4 and clean_payload[0] == "62":
        return clean_payload[3:]

    for idx, byte in enumerate(clean_payload):
        if byte == "62" and len(clean_payload) > idx + 2:
            return clean_payload[idx + 3:]

    if (
        len(clean_payload) > 2
        and clean_payload[0][0] in ("B", "E", "F")
    ):
        return clean_payload[2:]

    return clean_payload


def _parse_bcd_byte(byte_str):
    if len(byte_str) != 2:
        return None

    try:
        high = int(byte_str[0], 16)
        low = int(byte_str[1], 16)
    except ValueError:
        return None

    if high > 9 or low > 9:
        return None

    return (high * 10) + low


def _trim_padding_bytes(payload, pad_bytes=("00", "20", "AA")):
    trimmed = list(payload or [])
    while trimmed and trimmed[-1] in pad_bytes:
        trimmed.pop()
    return trimmed


def decode_special_did_value(desc, payload):
    normalized_desc = _normalize_desc(desc)
    clean_payload = _strip_positive_response_header(payload)
    is_manufacturing_date = (
        "manufacturing date" in normalized_desc
        or "mfg date" in normalized_desc
    )

    if not clean_payload:
        if is_manufacturing_date:
            return ""
        return None

    if "b can" in normalized_desc and "version" in normalized_desc:
        ascii_payload = _trim_padding_bytes(clean_payload)
        if not ascii_payload:
            return ""

        try:
            if all(32 <= int(byte, 16) <= 126 for byte in ascii_payload):
                return "".join(chr(int(byte, 16)) for byte in ascii_payload)
        except ValueError:
            return None

        # Some ECUs return B-CAN version as version bytes like 25 08 01
        # instead of printable ASCII. Present this as a readable dotted value.
        bcd_parts = [_parse_bcd_byte(byte) for byte in ascii_payload]
        if all(part is not None for part in bcd_parts):
            return ".".join(f"{part:02d}" for part in bcd_parts)

        return None

    if "version" in normalized_desc:
        ascii_payload = _trim_padding_bytes(clean_payload)
        if not ascii_payload:
            return ""

        try:
            if all(32 <= int(byte, 16) <= 126 for byte in ascii_payload):
                return "".join(chr(int(byte, 16)) for byte in ascii_payload)
        except ValueError:
            return None

    if is_manufacturing_date:
        if len(clean_payload) < 4:
            return ""

        if all(byte == "00" for byte in clean_payload[:4]):
            return "00 00 00 00"

        year_hi = _parse_bcd_byte(clean_payload[0])
        year_lo = _parse_bcd_byte(clean_payload[1])
        month = _parse_bcd_byte(clean_payload[2])
        day = _parse_bcd_byte(clean_payload[3])

        if None in (year_hi, year_lo, month, day):
            return ""

        if month < 1 or month > 12 or day < 1 or day > 31:
            return ""

        year = f"{year_hi:02d}{year_lo:02d}"
        return f"{year}-{month:02d}-{day:02d}"

    return None
