"""API Client for NEC devices (LAN Control - TCP Port 7142 - Revised Get Reply Handling & Refactoring)."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

_LOGGER = logging.getLogger(__name__)

NEC_CONTROL_PORT = 7142
SOH = b"\x01"
RESERVED = b"0"
SOURCE = b"0"
EOT = b"\x04"
STX = b"\x02"
ETX = b"\x03"

MONITOR_ID_MAP = {
    1: b"A",
    2: b"B",
    3: b"C",
    4: b"D",
    5: b"E",
    6: b"F",
    7: b"G",
    8: b"H",
    9: b"I",
    10: b"J",
    11: b"K",
    12: b"L",
    13: b"M",
    14: b"N",
    15: b"O",
    16: b"P",
    17: b"Q",
    18: b"R",
    19: b"S",
    20: b"T",
    21: b"U",
    22: b"V",
    23: b"W",
    24: b"X",
    25: b"Y",
    26: b"Z",
    51: b"s",
    52: b"t",
    53: b"u",
    54: b"v",
    55: b"w",
    56: b"x",
    57: b"y",
    58: b"z",
    59: b"{",
    60: b"|",
    61: b"}",
    62: b"~",
    63: b"\x7f",
    64: b"\x80",
    65: b"\x81",
    66: b"\x82",
    67: b"\x83",
    68: b"\x84",
    69: b"\x85",
    70: b"\x86",
    71: b"\x87",
    72: b"\x88",
    73: b"\x89",
    74: b"\x8a",
    75: b"\x8b",
    76: b"\x8c",
    77: b"\x8d",
    78: b"\x8e",
    79: b"\x8f",
    80: b"\x90",
    81: b"\x91",
    82: b"\x92",
    83: b"\x93",
    84: b"\x94",
    85: b"\x95",
    86: b"\x96",
    87: b"\x97",
    88: b"\x98",
    89: b"\x99",
    90: b"\x9a",
    91: b"\x9b",
    92: b"\x9c",
    93: b"\x9d",
    94: b"\x9e",
    95: b"\x9f",
    96: b"\xa0",
    97: b"\xa1",
    98: b"\xa2",
    99: b"\xa3",
    100: b"\xa4",
    "ALL": b"*",
}

GROUP_ID_MAP = {
    "A": b"1",
    "B": b"2",
    "C": b"3",
    "D": b"4",
    "E": b"5",
    "F": b"6",
    "G": b"7",
    "H": b"8",
    "I": b"9",
    "J": b":",
}

RESPONSE_TYPE_MAP = {
    b"A": b"B",  # Command -> Reply
    b"C": b"D",  # Get -> Get Reply
    b"E": b"F",  # Set -> Set Reply
}


@dataclass
class ParameterValue:
    """Data class for parameter get responses."""

    result: str
    op_code_page: str
    op_code: str
    type: str
    max_value: int
    current_value: int


@dataclass
class TimingReport:
    """Data class for timing report."""

    status_byte: int
    h_frequency_khz: float
    v_frequency_hz: float


async def get_timing_report(self) -> Optional[TimingReport]:
    """Send the command to get the timing report and parse the reply."""
    op_code = "07"
    op_code_page = ""  # No OP code page specified for this command format
    params = b""
    response_payload = await self._send_command(
        op_code, op_code_page, params, message_type=b"A"
    )

    if (
        response_payload
        and len(response_payload) == 10
        and response_payload[0:2] == b"4E"
    ):
        status_bytes_hex = response_payload[2:4].decode("ascii")
        try:
            status_byte = int(status_bytes_hex, 16)
            h_freq_hex = response_payload[4:8].decode("ascii")
            h_frequency_khz = int(h_freq_hex, 16) * 0.01
            v_freq_hex = response_payload[8:12].decode("ascii")
            v_frequency_hz = int(v_freq_hex, 16) * 0.01
            return self.TimingReport(
                status_byte, h_frequency_khz, v_frequency_hz
            )
        except ValueError:
            _LOGGER.warning(
                f"Error parsing timing report data: {response_payload.hex()}"
            )
            return None
    elif response_payload:
        _LOGGER.warning(
            f"Unexpected timing report reply format: {response_payload.hex()}"
        )
    return None


class NECAPI:
    """API Client for NEC devices (LAN Control - TCP Port 7142 - Revised Get Reply Handling & Refactoring)."""

    def __init__(
        self,
        host: str,
        port: int = 7142,
        monitor_id: int = 1,
        timeout: int = 5,
    ):
        """Initialize the API client for LAN control."""
        self.host = host
        self.port = port
        self.monitor_id = monitor_id
        self.timeout = timeout
        self.reader = None
        self.writer = None
        self._lock = asyncio.Lock()

    async def connect(self, timeout=None):
        """Connect to the device via TCP/IP."""
        connect_timeout = timeout if timeout is not None else self.timeout
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port
            )
            _LOGGER.info(
                f"Connected to NEC device on {self.host}:{self.port} (LAN Control)"
            )
            return True
        except ConnectionRefusedError:
            _LOGGER.error(f"Connection refused to {self.host}:{self.port}")
            return False
        except OSError as e:
            _LOGGER.error(f"Error connecting to {self.host}:{self.port}: {e}")
            return False
        except asyncio.TimeoutError:
            _LOGGER.error(
                f"Timeout of {connect_timeout} seconds connecting to {self.host}:{self.port}"
            )
            return False

    def _calculate_checksum(self, data: bytes) -> bytes:
        """Calculate the XOR checksum from after SOH to ETX."""
        checksum = 0
        for byte in data:
            checksum ^= byte
        return hex(checksum)[2:].upper().encode("ascii").zfill(2)

    async def _receive_response(self, command: bytes) -> Optional[bytes]:
        """Receive and validate a response."""
        try:
            response = await asyncio.wait_for(
                self.reader.readuntil(EOT), timeout=self.timeout
            )
            _LOGGER.debug(f"Received response: {response.hex()}")
            if not (
                response
                and len(response) >= 7
                and response.startswith(SOH)
                and response.endswith(EOT)
            ):
                _LOGGER.warning(f"Invalid response format: {response.hex()}")
                return None

            header = response[0:5]
            length_bytes = response[5:7]
            try:
                payload_length = int(length_bytes.decode("ascii"), 16)
            except ValueError:
                _LOGGER.warning(
                    f"Could not parse response length: {length_bytes}"
                )
                return None

            payload = response[7:-3]
            if len(payload) != payload_length:
                _LOGGER.warning(
                    f"Received payload length mismatch: Received {len(payload)}, Expected {payload_length}"
                )
                return None

            checksum_received = response[-3:-1]
            calculated_checksum = self._calculate_checksum(response[0:-3])
            if checksum_received != calculated_checksum:
                _LOGGER.warning(
                    f"Checksum mismatch: Received {checksum_received.decode()}, Calculated {calculated_checksum.decode()}"
                )
                return None

            if not (payload.startswith(STX) and payload.endswith(ETX)):
                _LOGGER.warning("Response payload missing STX/ETX.")
                return None

            return payload[1:-1]
        except asyncio.TimeoutError:
            _LOGGER.warning(
                f"Timeout of {self.timeout} seconds waiting for response."
            )
            return None
        except Exception as e:
            _LOGGER.error(f"Error reading response: {e}")
            return None

    async def save_current_settings(self) -> bool:
        """Send the command to save current settings."""
        op_code = "OC"
        op_code_page = ""  # No OP code page specified for this command format
        params = b""
        response_payload = await self._send_command(
            op_code, op_code_page, params, message_type=b"A"
        )
        return response_payload == b"OC"

    async def _send_command(
        self,
        op_code: str,
        op_code_page: str = "00",
        params: bytes = b"",
        message_type: bytes = b"A",
    ) -> Optional[bytes]:
        """Construct and send a command, then receive and validate the response."""
        async with self._lock:
            if self.writer is None or self.reader is None:
                _LOGGER.error("Not connected to the NEC device.")
                return None

            dest_address = MONITOR_ID_MAP.get(self.monitor_id)
            if not dest_address:
                _LOGGER.error(f"Invalid Monitor ID: {self.monitor_id}")
                return None

            message_payload = (
                STX
                + op_code_page.encode("ascii")
                + op_code.encode("ascii")
                + params
                + ETX
            )
            message_length = (
                hex(len(message_payload))[2:].upper().encode("ascii").zfill(2)
            )
            header_without_soh = (
                RESERVED
                + dest_address
                + SOURCE
                + message_type
                + message_length
            )
            data_for_checksum = header_without_soh + message_payload
            checksum = self._calculate_checksum(data_for_checksum)
            command = (
                SOH + header_without_soh + message_payload + checksum + EOT
            )
            _LOGGER.debug(f"Sending command: {command.hex()}")
            self.writer.write(command)
            await asyncio.sleep(0.1)

            expected_response_type = RESPONSE_TYPE_MAP.get(message_type)
            response_payload = await self._receive_response(command)

            if response_payload and expected_response_type:
                response_header_type = self._get_response_header_type(
                    command, response_payload
                )
                if response_header_type != expected_response_type:
                    _LOGGER.warning(
                        f"Unexpected response type. Sent: {message_type.decode()}, Received: {response_header_type.decode()}"
                    )
                    return None
            return response_payload

    def _get_response_header_type(
        self, command: bytes, response_payload: bytes
    ) -> Optional[bytes]:
        """Extract the message type from the response header."""
        if response_payload:
            # Need to reconstruct the full response to get the header
            # This is a simplified approach, we might need to adjust based on how _receive_response evolves
            full_response = (
                SOH
                + command[1:4]
                + response_payload[:2]
                + hex(len(response_payload) + 2)[2:]
                .upper()
                .encode("ascii")
                .zfill(2)
                + response_payload
                + self._calculate_checksum(command[1:4] + response_payload)
                + EOT
            )
            if len(full_response) >= 5:
                return full_response[4:5]
        return None

    async def _get_parameter(
        self, op_code: str, op_code_page: str = "00"
    ) -> Optional[ParameterValue]:
        """Helper to get a parameter with a standard get reply format."""
        response = await self._send_command(
            op_code, op_code_page, message_type=b"C"
        )
        if response and len(response) == 16:
            result = response[0:2].decode("ascii")
            response_op_code_page = response[2:4].decode("ascii")
            response_op_code = response[4:6].decode("ascii")
            type_code = response[6:8].decode("ascii")
            max_value = int(response[8:12].decode("ascii"), 16)
            current_value = int(response[12:16].decode("ascii"), 16)
            return ParameterValue(
                result,
                response_op_code_page,
                response_op_code,
                type_code,
                max_value,
                current_value,
            )
        elif response:
            _LOGGER.warning(
                f"Unexpected response length for get parameter ({op_code}): {len(response)}"
            )
        return None

    async def get_device_info(self) -> dict:
        """Get device information (using OP code 'A0' on page '00' and message type 'C')."""
        response = await self._send_command(
            "A0", op_code_page="00", message_type=b"C"
        )
        if response and len(response) >= 16:
            model_name = response[0:8].decode("ascii").strip()
            serial_number = response[8:16].decode("ascii").strip()
            return {
                "model_name": model_name,
                "serial_number": serial_number,
                "firmware_version": "N/A",
                "manufacturer": "NEC",
            }
        return {
            "model_name": "NEC Device (LAN)",
            "serial_number": "N/A",
            "firmware_version": "N/A",
            "manufacturer": "NEC",
        }

    async def get_power_status(self) -> str:
        """Get the power status of the device (using OP code 'KA' on page '00' and message type 'C')."""
        response = await self._send_command(
            "KA", op_code_page="00", message_type=b"C"
        )
        if response == b"01":
            return "on"
        elif response == b"00":
            return "off"
        return "unknown"


async def set_power(self, power: str) -> bool:
    """Set the power status of the device (using OP code 'KA' on page '00' and message type 'E')."""
    op_code = "KA"
    op_code_page = "00"  # Assuming page 00 for power, needs verification
    value = "01" if power.lower() == "on" else "00"
    set_value = value.zfill(4)  # 16-bit value as 4 ASCII hex chars
    params = set_value.encode("ascii")
    response = await self._send_command(
        op_code, op_code_page, params, message_type=b"E"
    )
    return response == b"OK"


async def set_input(self, input_code: str) -> bool:
    """Set the input source (using OP code 'KI' on page '00' and message type 'E')."""
    op_code = "KI"
    op_code_page = "00"  # Assuming page 00 for input, needs verification
    set_value_hex = int(input_code).to_bytes(2, "big").hex().upper().zfill(4)
    params = set_value_hex.encode("ascii")
    response = await self._send_command(
        op_code, op_code_page, params, message_type=b"E"
    )
    return response == b"OK"


async def get_input(self) -> Optional[str]:
    """Get the current input source code (using OP code 'KI' on page '00' and message type 'C')."""
    response = await self._send_command(
        "KI", op_code_page="00", message_type=b"C"
    )
    if response and len(response) == 2:
        return response.decode("ascii")
    return None


async def get_all_data(self) -> dict:
    """Get all relevant data from the device."""
    power_status = await self.get_power_status()
    current_input = await self.get_input()
    device_info = await self.get_device_info()
    return {
        **device_info,
        "power_status": power_status,
        "input_source": current_input,
    }


async def close(self) -> None:
    """Close the TCP/IP connection."""
    if self.writer:
        self.writer.close()
    if self.reader:
        await self.reader.wait_closed()
    self.reader = None
    self.writer = None


async def get_temperature(self, sensor_id: int) -> Optional[int]:
    """Get the temperature from the specified sensor."""
    if not 1 <= sensor_id <= 3:
        _LOGGER.error(f"Invalid sensor ID: {sensor_id}. Must be 1, 2, or 3.")
        return None

    op_code_page = "02"
    op_code = "78"
    sensor_str = f"{sensor_id:02d}"
    params = sensor_str.encode("ascii")

    command = await self._send_command(
        op_code, op_code_page, params, message_type=b"A"
    )
    if command:
        response_payload = await self._receive_response(command)
        if (
            response_payload
            and len(response_payload) == 8
            and response_payload[2:4].decode("ascii") == op_code
        ):
            result = response_payload[0:2].decode("ascii")
            reported_sensor = response_payload[4:6].decode("ascii")
            value_hex = response_payload[6:8].decode("ascii")
            if result == "00" and reported_sensor == sensor_str:
                try:
                    temperature_value = int(value_hex, 16)
                    return temperature_value
                except ValueError:
                    _LOGGER.warning(
                        f"Error parsing temperature value: {value_hex}"
                    )
                    return None
            else:
                _LOGGER.warning(
                    f"Error reading temperature: Result={result}, Sensor={reported_sensor}"
                )
                return None
        else:
            _LOGGER.warning(
                f"Unexpected response format for temperature: {response_payload.hex() if response_payload else None}"
            )
            return None
    return None


async def get_backlight(self) -> Optional[int]:
    """Get the current backlight setting."""
    response = await self._get_parameter(op_code="10", op_code_page="00")
    if response:
        return response.current_value
    return None


async def set_backlight(self, brightness: int) -> bool:
    """Set the backlight brightness."""
    if 0 <= brightness <= 100:
        hex_value = f"{brightness:04x}".upper()
        return await self._set_parameter(
            op_code="10",
            op_code_page="00",
            set_value=hex_value.encode("ascii"),
        )
    else:
        _LOGGER.warning("Brightness value must be between 0 and 100.")
        return False


async def get_contrast(self) -> Optional[int]:
    """Get the current contrast setting."""
    response = await self._get_parameter(op_code="12", op_code_page="00")
    if response:
        return response.current_value
    return None


async def set_contrast(self, contrast: int) -> bool:
    """Set the contrast level."""
    if 0 <= contrast <= 100:
        hex_value = f"{contrast:04x}".upper()
        return await self._set_parameter(
            op_code="12",
            op_code_page="00",
            set_value=hex_value.encode("ascii"),
        )
    else:
        _LOGGER.warning("Contrast value must be between 0 and 100.")
        return False


async def get_sharpness(self) -> Optional[int]:
    """Get the current sharpness setting."""
    response = await self._get_parameter(op_code="8C", op_code_page="00")
    if response:
        return response.current_value
    return None


async def set_sharpness(self, sharpness: int) -> bool:
    """Set the sharpness level."""
    if 0 <= sharpness <= 100:
        hex_value = f"{sharpness:04x}".upper()
        return await self._set_parameter(
            op_code="8C",
            op_code_page="00",
            set_value=hex_value.encode("ascii"),
        )
    else:
        _LOGGER.warning("Sharpness value must be between 0 and 100.")
        return False


async def set_telecine(self, mode: str) -> bool:
    """Set the Telecine mode."""
    mode_map = {"off": "01", "auto": "02"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="23",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Telecine mode: {mode}. Supported modes: off, auto."
        )
        return False


async def get_picture_mode(self) -> Optional[str]:
    """Get the current Picture Mode."""
    response = await self._get_parameter(op_code="1A", op_code_page="02")
    if response:
        mode_map_reverse = {
            0: "sRGB",
            3: "HIGHBRIGHT",
            4: "STANDARD",
            5: "CINEMA1",
            6: "CINEMA2",
            8: "CUSTOM1",
            9: "CUSTOM2",
        }
        return mode_map_reverse.get(response.current_value)
    return None


async def set_picture_mode(self, mode: str) -> bool:
    """Set the Picture Mode."""
    mode_map = {
        "srgb": "00",
        "highbright": "03",
        "standard": "04",
        "cinema1": "05",
        "cinema2": "06",
        "custom1": "08",
        "custom2": "09",
    }
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="1A",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Picture Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def reset_picture_settings(self) -> bool:
    """Reset the picture settings to default (momentary command)."""
    return await self._set_parameter(
        op_code="CB", op_code_page="02", set_value=b"0001"
    )  # Assuming '1' is the 'Reset' parameter


async def auto_setup(self) -> bool:
    """Execute Auto Setup (momentary command)."""
    return await self._set_parameter(
        op_code="1E", op_code_page="00", set_value=b"0001"
    )  # Assuming '1' is the 'Execute' parameter


async def auto_adjust(self, on: bool) -> bool:
    """Set Auto Adjust On/Off."""
    value = "02" if on else "01"
    return await self._set_parameter(
        op_code="B7",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_input_resolution(self, resolution_mode: str) -> bool:
    """Set the Input Resolution mode."""
    mode_map = {
        "no mean": "00",
        "always auto": "01",
        "item 2": "02",
        "item 3": "03",
        "item 4": "04",
        "item 5": "05",
    }
    hex_value = mode_map.get(resolution_mode.lower().replace(" ", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="DA",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input Resolution mode: {resolution_mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_aspect_ratio(self, aspect: str) -> bool:
    """Set the Aspect Ratio mode."""
    aspect_map = {
        "no mean": "00",
        "normal": "01",
        "full": "02",
        "zoom": "03",
        "wide": "04",
        "dynamic": "05",
    }
    hex_value = aspect_map.get(aspect.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="70",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Aspect Ratio: {aspect}. Supported modes: {', '.join(aspect_map.keys())}."
        )
        return False


async def set_zoom(self, percentage: int) -> bool:
    """Set the Zoom percentage (0-100)."""
    if 0 <= percentage <= 100:
        # Map percentage to the documented range 0-89 (59h), 90 (5Ah), 91 (5Bh), 100 (64h), 300 (12Ch)
        if percentage <= 89:
            hex_value = f"{percentage:02x}".upper()
        elif percentage == 90:
            hex_value = "5A"
        elif percentage == 91:
            hex_value = "5B"
        elif percentage == 100:
            hex_value = "64"
        elif (
            percentage == 300
        ):  # This seems like an outlier, but we'll include it as documented
            hex_value = "12C"
        else:
            _LOGGER.warning(
                f"Zoom percentage {percentage} is outside the explicitly documented mapping."
            )
            hex_value = (
                f"{percentage:02x}".upper()
            )  # Fallback to hex if not in explicit mapping

        return await self._set_parameter(
            op_code="2C",
            op_code_page="11",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Zoom percentage must be between 0 and 100.")
        return False


async def set_h_zoom(self, percentage: int) -> bool:
    """Set the Horizontal Zoom percentage (0-100)."""
    if 0 <= percentage <= 100:
        # Map percentage to the documented range 0-89 (59h), 90 (5Ah), 91 (5Bh), 100 (64h), 300 (12Ch)
        if percentage <= 89:
            hex_value = f"{percentage:02x}".upper()
        elif percentage == 90:
            hex_value = "5A"
        elif percentage == 91:
            hex_value = "5B"
        elif percentage == 100:
            hex_value = "64"
        elif (
            percentage == 300
        ):  # This seems like an outlier, but we'll include it as documented
            hex_value = "12C"
        else:
            _LOGGER.warning(
                f"Horizontal Zoom percentage {percentage} is outside the explicitly documented mapping."
            )
            hex_value = (
                f"{percentage:02x}".upper()
            )  # Fallback to hex if not in explicit mapping

        return await self._set_parameter(
            op_code="91",
            op_code_page="11",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            "Horizontal Zoom percentage must be between 0 and 100."
        )
        return False


async def set_v_zoom(self, percentage: int) -> bool:
    """Set the Vertical Zoom percentage (0-100)."""
    if 0 <= percentage <= 100:
        # Map percentage to the documented range 0-89 (59h), 90 (5Ah), 91 (5Bh), 100 (64h), 300 (12Ch)
        if percentage <= 89:
            hex_value = f"{percentage:02x}".upper()
        elif percentage == 90:
            hex_value = "5A"
        elif percentage == 91:
            hex_value = "5B"
        elif percentage == 100:
            hex_value = "64"
        elif (
            percentage == 300
        ):  # This seems like an outlier, but we'll include it as documented
            hex_value = "12C"
        else:
            _LOGGER.warning(
                f"Vertical Zoom percentage {percentage} is outside the explicitly documented mapping."
            )
            hex_value = (
                f"{percentage:02x}".upper()
            )  # Fallback to hex if not in explicit mapping

        return await self._set_parameter(
            op_code="2E",
            op_code_page="11",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Vertical Zoom percentage must be between 0 and 100.")
        return False


async def set_h_position_page_02(self, side: str) -> bool:
    """Set the Horizontal Position (page 02h)."""
    side_map = {"left": "00", "right": "01"}
    hex_value = side_map.get(side.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="CC",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Horizontal Position side: {side}. Supported sides: left, right."
        )
        return False


async def set_v_position_page_02(self, side: str) -> bool:
    """Set the Vertical Position (page 02h)."""
    side_map = {"down": "00", "up": "01"}
    hex_value = side_map.get(side.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="CD",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Vertical Position side: {side}. Supported sides: down, up."
        )
        return False


async def set_image_flip(self, flip_mode: str) -> bool:
    """Set the Image Flip mode."""
    mode_map = {
        "none": "00",
        "h flip": "02",
        "v flip": "03",
        "180 rotate": "04",
    }
    hex_value = mode_map.get(flip_mode.lower().replace(" ", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="D7",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Image Flip mode: {flip_mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_osd_flip(self, flip_mode: str) -> bool:
    """Set the OSD Flip mode."""
    mode_map = {"off": "00", "on": "01"}
    hex_value = mode_map.get(flip_mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="B8",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid OSD Flip mode: {flip_mode}. Supported modes: off, on."
        )
        return False


async def reset_adjust_settings(self, adjust_category: str) -> bool:
    """Reset adjustment settings (momentary command)."""
    category_map = {"no mean": "00", "reset": "01", "picture": "02"}
    hex_value = category_map.get(adjust_category.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="CB",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Reset (Adjust) category: {adjust_category}. Supported categories: {', '.join(category_map.keys())}."
        )
        return False


async def set_volume(self, volume: int) -> bool:
    """Set the volume level (0-100)."""
    if 0 <= volume <= 100:
        hex_value = f"{volume:02x}".upper()
        return await self._set_parameter(
            op_code="82",
            op_code_page="00",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Volume level must be between 0 and 100.")
        return False


async def set_balance(self, balance: int) -> bool:
    """Set the audio balance (-30 to 30)."""
    if -30 <= balance <= 30:
        hex_value = f"{balance + 30:02x}".upper()  # Shift range to 0-60
        return await self._set_parameter(
            op_code="93",
            op_code_page="00",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Balance must be between -30 and 30.")
        return False


async def set_treble(self, treble: int) -> bool:
    """Set the treble level (-6 to 6)."""
    if -6 <= treble <= 6:
        hex_value = f"{treble + 6:02x}".upper()  # Shift range to 0-12
        return await self._set_parameter(
            op_code="94",
            op_code_page="00",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Treble must be between -6 and 6.")
        return False


async def set_bass(self, bass: int) -> bool:
    """Set the bass level (-6 to 6)."""
    if -6 <= bass <= 6:
        hex_value = f"{bass + 6:02x}".upper()  # Shift range to 0-12
        return await self._set_parameter(
            op_code="91",
            op_code_page="00",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Bass must be between -6 and 6.")
        return False


async def set_pip_audio(self, source: str) -> bool:
    """Set the PIP Audio source."""
    source_map = {"main audio": "01", "pip audio": "02"}
    hex_value = source_map.get(source.lower().replace(" ", "_"))
    if hex_value:
        return await self._set_parameter(
            op_code="80",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid PIP Audio source: {source}. Supported sources: main audio, pip audio."
        )
        return False


async def set_line_out(self, mode: str) -> bool:
    """Set the Line Out mode."""
    mode_map = {"no mean": "00", "fixed": "01", "variable": "02"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="91",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Line Out mode: {mode}. Supported modes: no mean, fixed, variable."
        )
        return False


async def set_surround(self, on: bool) -> bool:
    """Set Surround sound On/Off."""
    value = "02" if on else "01"
    return await self._set_parameter(
        op_code="34",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_audio_input(self, input_source: str) -> bool:
    """Set the Audio Input source."""
    source_map = {
        "no mean": "00",
        "in1": "01",
        "in2": "02",
        "in3": "03",
        "hdmi1": "04",
        "option": "06",
        "dport1": "08",
        "dport2": "09",
        "hdmi2": "0A",
        "hdmi3": "0B",
    }
    hex_value = source_map.get(
        input_source.lower().replace("-", "").replace(" ", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="20",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Audio Input source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def set_audio_delay(self, on: bool, delay_time: int = 0) -> bool:
    """Set the Audio Delay On/Off and time (0-100)."""
    on_value = "01" if on else "00"
    if 0 <= delay_time <= 100:
        hex_delay = f"{delay_time:02x}".upper()
        return await self._set_parameter(
            op_code="CA",
            op_code_page="10",
            set_value=(on_value + hex_delay).encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Audio Delay time must be between 0 and 100.")
        return False


async def reset_audio_settings(self, audio_category: str) -> bool:
    """Reset audio settings (momentary command)."""
    category_map = {"no mean": "00", "reset": "01", "audio": "04"}
    hex_value = category_map.get(audio_category.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="CB",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Reset (Audio) category: {audio_category}. Supported categories: {', '.join(category_map.keys())}."
        )
        return False


async def set_off_timer(self, hours: int) -> bool:
    """Set the Off Timer (1-24 hours)."""
    if 1 <= hours <= 24:
        hex_value = f"{hours:02x}".upper()
        return await self._set_parameter(
            op_code="26",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Off Timer must be between 1 and 24 hours.")
        return False


async def set_schedule_enable(
    self, enable: bool, schedule_number: int = 1
) -> bool:
    """Enable or disable a schedule (1-7)."""
    if 1 <= schedule_number <= 7:
        value = (
            f"{schedule_number - 1:x}".upper()
            if enable
            else f"{schedule_number + 6:x}".upper()
        )
        return await self._set_parameter(
            op_code="E5",
            op_code_page="02",
            set_value=value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Schedule number must be between 1 and 7.")
        return False


async def set_keep_pip_mode(self, keep: bool) -> bool:
    """Set Keep PIP Mode On/Off."""
    value = "01" if keep else "00"
    return await self._set_parameter(
        op_code="82",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_pip_mode(self, mode: str) -> bool:
    """Set the PIP Mode."""
    mode_map = {
        "off": "00",
        "pip": "01",
        "p&p": "02",
        "still": "03",
        "picture by picture": "05",
        "picture by picture full": "06",
    }
    hex_value = mode_map.get(mode.lower().replace(" ", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="72",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid PIP Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_pip_size(self, size: str) -> bool:
    """Set the PIP Size."""
    size_map = {"small": "00", "large": "01"}
    hex_value = size_map.get(size.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="B9",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid PIP Size: {size}. Supported sizes: small, large."
        )
        return False


async def set_pip_position_x(self, x: int) -> bool:
    """Set the PIP Horizontal Position (0-100)."""
    if 0 <= x <= 100:
        hex_value = f"{x:02x}".upper()
        return await self._set_parameter(
            op_code="74",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("PIP Horizontal Position must be between 0 and 100.")
        return False


async def set_pip_position_y(self, y: int) -> bool:
    """Set the PIP Vertical Position (0-100)."""
    if 0 <= y <= 100:
        hex_value = f"{y:02x}".upper()
        return await self._set_parameter(
            op_code="75",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("PIP Vertical Position must be between 0 and 100.")
        return False


async def set_aspect_ratio_page_02(self, aspect: str) -> bool:
    """Set the Aspect Ratio (page 02h)."""
    aspect_map = {
        "no mean": "00",
        "normal": "01",
        "full": "02",
        "zoom": "03",
        "wide": "04",
    }
    hex_value = aspect_map.get(aspect.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="83",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Aspect Ratio: {aspect}. Supported modes: {', '.join(aspect_map.keys())}."
        )
        return False


async def set_text_ticker_mode(self, mode: str) -> bool:
    """Set the Text Ticker Mode."""
    mode_map = {"off": "00", "horizontal": "01", "vertical": "02"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="09",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Text Ticker Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_text_ticker_position(self, position: str) -> bool:
    """Set the Text Ticker Position."""
    position_map = {"top/left": "00", "bottom/right": "01"}
    hex_value = position_map.get(position.lower().replace("/", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="0A",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Text Ticker Position: {position}. Supported positions: {', '.join(position_map.keys())}."
        )
        return False


async def set_text_ticker_size(self, size: str) -> bool:
    """Set the Text Ticker Size."""
    size_map = {"narrow": "00", "wide": "01"}
    hex_value = size_map.get(size.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="0B",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Text Ticker Size: {size}. Supported sizes: narrow, wide."
        )
        return False


async def set_text_ticker_blend(self, blend: int) -> bool:
    """Set the Text Ticker Blend (0-100%)."""
    if 0 <= blend <= 100:
        hex_value = f"{blend:02x}".upper()
        return await self._set_parameter(
            op_code="0C",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Text Ticker Blend must be between 0 and 100.")
        return False


async def set_text_ticker_detect(self, detect: str) -> bool:
    """Set the Text Ticker Detect mode."""
    detect_map = {"no mean": "00", "auto": "01", "off": "02"}
    hex_value = detect_map.get(detect.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="0C",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )  # OP code is the same as BLEND - likely different parameters
    else:
        _LOGGER.warning(
            f"Invalid Text Ticker Detect mode: {detect}. Supported modes: {', '.join(detect_map.keys())}."
        )
        return False


async def set_text_ticker_fade_in(self, fade: str) -> bool:
    """Set the Text Ticker Fade In mode."""
    fade_map = {"no mean": "00", "off": "01", "on": "02"}
    hex_value = fade_map.get(fade.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="0D",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Text Ticker Fade In mode: {fade}. Supported modes: {', '.join(fade_map.keys())}."
        )
        return False


async def set_pip_input(self, input_source: str) -> bool:
    """Set the PIP (Sub) Input source."""
    source_map = {
        "no mean": "00",
        "vga": "01",
        "ypbpr/component": "02",
        "svideo": "03",
        "dvi": "04",
        "hdmi (set only)": "05",
        "video": "07",
        "ypbpr": "0C",
        "option": "0D",
        "ypbpr2": "0E",
        "rgbhv": "0F",
        "dport1": "15",
        "dport2": "16",
        "hdmi2": "1B",
        "hdmi3": "80",
    }
    hex_value = source_map.get(
        input_source.lower().replace("/", "").replace(" ", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="7B",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid PIP Input source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def reset_pip_settings(self, pip_category: str) -> bool:
    """Reset PIP settings (momentary command)."""
    category_map = {"no mean": "00", "reset": "01", "pip": "06"}
    hex_value = category_map.get(pip_category.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="CB",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Reset (PIP) category: {pip_category}. Supported categories: {', '.join(category_map.keys())}."
        )
        return False


async def set_language(self, language: str) -> bool:
    """Set the OSD Language."""
    language_map = {
        "english": "01",
        "german": "02",
        "french": "03",
        "spanish": "04",
        "chinese": "05",
        "italian": "06",
        "swedish": "07",
        "russian": "08",
        # Note: The table shows "CHINESE" with value 14 (0E in hex). Double-check documentation if needed.
    }
    hex_value = language_map.get(language.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="6B",
            op_code_page="00",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    elif language.lower() == "chinese":
        return await self._set_parameter(
            op_code="6B",
            op_code_page="00",
            set_value="0E".encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid OSD Language: {language}. Supported languages: {', '.join(language_map.keys()) + ', chinese'}."
        )
        return False


async def set_menu_display_time(self, seconds: int) -> bool:
    """Set the OSD Menu Display Time (5, 10, 15, 30, 60, 240 seconds)."""
    time_map = {5: "01", 10: "02", 15: "03", 30: "04", 60: "05", 240: "06"}
    hex_value = time_map.get(seconds)
    if hex_value:
        return await self._set_parameter(
            op_code="FCh",
            op_code_page="00",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Menu Display Time: {seconds}. Supported times: {', '.join(map(str, time_map.keys()))} seconds."
        )
        return False


async def set_osd_position_x(self, x: int) -> bool:
    """Set the OSD Horizontal Position (0-255)."""
    if 0 <= x <= 255:
        hex_value = f"{x:02x}".upper()
        return await self._set_parameter(
            op_code="38",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("OSD Horizontal Position must be between 0 and 255.")
        return False


async def set_osd_position_y(self, y: int) -> bool:
    """Set the OSD Vertical Position (0-255)."""
    if 0 <= y <= 255:
        hex_value = f"{y:02x}".upper()
        return await self._set_parameter(
            op_code="39",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("OSD Vertical Position must be between 0 and 255.")
        return False


async def show_information_osd(self, duration: int = 5) -> bool:
    """Show the Information OSD for a specified duration (5 or 10 seconds)."""
    duration_map = {5: "01", 10: "02"}
    hex_value = duration_map.get(duration)
    if hex_value:
        return await self._set_parameter(
            op_code="30",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Information OSD duration must be 5 or 10 seconds.")
        return False


async def get_carbon_savings(self) -> Optional[dict]:
    """Get the Carbon Savings (Read Only - Refer to Chapter 16)."""
    # This is a read-only value. We would need to know the specific
    # Get command and response format from Chapter 16 to implement this.
    _LOGGER.warning(
        "Getting Carbon Savings requires information from Chapter 16."
    )
    return None


async def get_carbon_usage(self) -> Optional[dict]:
    """Get the Carbon Usage (Read Only - Refer to Chapter 16)."""
    # This is a read-only value. We would need to know the specific
    # Get command and response format from Chapter 16 to implement this.
    _LOGGER.warning(
        "Getting Carbon Usage requires information from Chapter 16."
    )
    return None


async def set_osd_transparency(self, transparency: str) -> bool:
    """Set the OSD Transparency."""
    transparency_map = {"off": "00", "low": "01", "medium": "02", "high": "03"}
    hex_value = transparency_map.get(transparency.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="2B",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid OSD Transparency: {transparency}. Supported levels: {', '.join(transparency_map.keys())}."
        )
        return False


async def set_osd_rotation(self, rotation: str) -> bool:
    """Set the OSD Rotation."""
    rotation_map = {"normal": "00", "landscape": "01", "rotated": "02"}
    hex_value = rotation_map.get(rotation.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="41",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid OSD Rotation: {rotation}. Supported modes: {', '.join(rotation_map.keys())}."
        )
        return False


async def reset_menu_settings(self) -> bool:
    """Reset the menu settings to default (momentary command)."""
    return await self._set_parameter(
        op_code="EAh", op_code_page="10", set_value=b"0001"
    )  # Assuming '1' is the 'Display a Menu' parameter for reset


async def set_monitor_id(self, monitor_id: int) -> bool:
    """Set the Monitor ID (1-100)."""
    if 1 <= monitor_id <= 100:
        hex_value = f"{monitor_id:02x}".upper()
        return await self._set_parameter(
            op_code="3A",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Monitor ID must be between 1 and 100.")
        return False


async def set_group_id(self, group: str) -> bool:
    """Set the Group ID (A-J)."""
    group_map = {
        "a": "01",
        "b": "02",
        "c": "04",
        "d": "08",
        "e": "10",
        "f": "20",
        "g": "40",
        "h": "80",
        "i": "100",
        "j": "200",
    }  # Using decimal for bit positions
    hex_value = f"{int(group_map.get(group.lower(), '0'), 16):02x}".upper()
    if group.lower() in group_map:
        return await self._set_parameter(
            op_code="7F",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Group ID must be one of A-J.")
        return False


async def set_ir_lock(self, locked: bool) -> bool:
    """Set the IR Lock (On/Off)."""
    value = "01" if locked else "00"
    return await self._set_parameter(
        op_code="D4",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_power_lock(self, locked: str) -> bool:
    """Set the Power Button Lock mode."""
    lock_map = {
        "no mean": "00",
        "unlock": "01",
        "lock": "02",
        "custom lock": "03",
    }
    hex_value = lock_map.get(locked.lower().replace(" ", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="D5",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Power Lock mode: {locked}. Supported modes: {', '.join(lock_map.keys())}."
        )
        return False


async def set_volume_lock(self, locked: str) -> bool:
    """Set the Volume Button Lock mode."""
    lock_map = {"no mean": "00", "unlock": "01", "lock": "02"}
    hex_value = lock_map.get(locked.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="D6",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Volume Lock mode: {locked}. Supported modes: {', '.join(lock_map.keys())}."
        )
        return False


async def set_min_volume(self, volume: int) -> bool:
    """Set the Minimum Volume level (0-100)."""
    if 0 <= volume <= 100:
        hex_value = f"{volume:02x}".upper()
        return await self._set_parameter(
            op_code="D7",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Minimum Volume must be between 0 and 100.")
        return False


async def get_model_name(self) -> Optional[str]:
    _LOGGER.warning("Getting Model Name requires information from Chapter 12.")
    return None


async def get_serial_number(self) -> Optional[str]:
    _LOGGER.warning(
        "Getting Serial Number requires information from Chapter 12."
    )
    return None


async def get_firmware_version(self) -> Optional[str]:
    _LOGGER.warning(
        "Getting Firmware Version requires information from Chapter 12."
    )
    return None


async def set_input_name(self, input_source: str, name: str) -> bool:
    _LOGGER.warning("Setting Input Name requires information from Chapter 18.")
    return False


async def reset_input_name(self, input_source: str) -> bool:
    _LOGGER.warning(
        "Resetting Input Name requires information from Chapter 18."
    )
    return False


async def get_auto_id_status(self) -> Optional[str]:
    _LOGGER.warning(
        "Getting Auto ID status requires information from Chapter 17."
    )
    return None


async def trigger_auto_id(self) -> bool:
    _LOGGER.warning("Triggering Auto ID requires information from Chapter 17.")
    return False


async def set_max_volume(self, volume: int) -> bool:
    """Set the Maximum Volume level (0-100)."""
    if 0 <= volume <= 100:
        hex_value = f"{volume:02x}".upper()
        return await self._set_parameter(
            op_code="D8",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Maximum Volume must be between 0 and 100.")
        return False


async def set_input_unlock_select(self, input_source: str) -> bool:
    """Set the Input source via Unlock Select."""
    source_map = {
        "no mean": "00",
        "vga": "01",
        "ypbpr/component": "02",
        "svideo": "03",
        "dvi": "04",
        "hdmi (set only)": "05",
        "video2": "07",
        "svideo2": "0B",
        "ypbpr/rgb": "0C",
        "option": "0D",
        "ypbpr2": "0E",
        "rgb/scart": "0F",
        "dport1": "15",
        "dport2": "16",
        "hdmi2": "17",
        "hdmi3": "80",
    }
    hex_value = source_map.get(
        input_source.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="DA",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input source for Unlock Select: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def set_tile_matrix_h_monitors(self, count: int) -> bool:
    """Set the number of horizontal monitors in the tile matrix (0-10)."""
    if 0 <= count <= 10:
        hex_value = f"{count:02x}".upper()
        return await self._set_parameter(
            op_code="D0",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Horizontal monitor count must be between 0 and 10.")
        return False


async def set_tile_matrix_v_monitors(self, count: int) -> bool:
    """Set the number of vertical monitors in the tile matrix (0-10)."""
    if 0 <= count <= 10:
        hex_value = f"{count:02x}".upper()
        return await self._set_parameter(
            op_code="D1",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Vertical monitor count must be between 0 and 10.")
        return False


async def set_tile_matrix_position(self, position: int) -> bool:
    """Set the position of this monitor in the tile matrix (0-100)."""
    if 0 <= position <= 100:
        hex_value = f"{position:02x}".upper()
        return await self._set_parameter(
            op_code="D2",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Tile matrix position must be between 0 and 100.")
        return False


async def set_tile_compensation(self, enabled: bool) -> bool:
    """Enable or disable Tile Compensation."""
    value = "01" if enabled else "00"
    return await self._set_parameter(
        op_code="D5",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def enable_tile_matrix(self, enable: bool) -> bool:
    """Enable or disable Tile Matrix mode."""
    value = "02" if enable else "00"
    return await self._set_parameter(
        op_code="D3",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_frame_compensation_auto(self, mode: str) -> bool:
    """Set Frame Compensation to Auto mode."""
    mode_map = {"no mean": "00", "off": "01", "on": "02"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="02",
            op_code_page="11",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Frame Compensation (Auto) mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_frame_compensation_manual(self, value: float) -> bool:
    """Set Frame Compensation to Manual mode (0.0 - 2.0F)."""
    if 0.0 <= value <= 2.0:
        # Map float to the documented hex values
        if value == 0.0:
            hex_value = "00"
        elif value == 0.25:
            hex_value = "19"
        elif value == 0.5:
            hex_value = "32"
        elif value == 0.75:
            hex_value = "4B"
        elif value == 1.0:
            hex_value = "64"
        elif value == 1.25:
            hex_value = "7D"
        elif value == 1.5:
            hex_value = "96"
        elif value == 1.75:
            hex_value = "AF"
        elif value == 2.0:
            hex_value = "C8"
        else:
            _LOGGER.warning(
                f"Manual Frame Compensation value {value} is not in the documented steps."
            )
            hex_value = ""
        if hex_value:
            return await self._set_parameter(
                op_code="03",
                op_code_page="11",
                set_value=hex_value.encode("ascii").zfill(4),
            )
        else:
            return False
    else:
        _LOGGER.warning(
            "Manual Frame Compensation value must be between 0.0 and 2.0."
        )
        return False


async def set_v_scan_reverse(self, reverse: str) -> bool:
    """Set the Vertical Scan Reverse mode."""
    reverse_map = {"none": "00", "auto": "01", "manual": "02", "reverse": "03"}
    hex_value = reverse_map.get(reverse.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="04",
            op_code_page="11",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Vertical Scan Reverse mode: {reverse}. Supported modes: {', '.join(reverse_map.keys())}."
        )
        return False


async def set_tile_matrix_memory(self, memory_action: str) -> bool:
    """Control Tile Matrix Memory (Save/Load)."""
    memory_map = {"no mean": "00", "save": "01", "load": "02", "input": "03"}
    hex_value = memory_map.get(memory_action.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="4A",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Tile Matrix Memory action: {memory_action}. Supported actions: {', '.join(memory_map.keys())}."
        )
        return False


async def set_power_on_delay(self, delay: int) -> bool:
    """Set the Power On Delay (0 or 50 seconds)."""
    delay_map = {0: "00", 50: "01"}
    hex_value = delay_map.get(delay)
    if hex_value:
        return await self._set_parameter(
            op_code="D8",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Power On Delay must be 0 or 50 seconds.")
        return False


async def set_link_to_id(self, linked: bool) -> bool:
    """Enable or disable Link to ID."""
    value = "01" if linked else "00"
    return await self._set_parameter(
        op_code="BCh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_video_out(self, on: bool) -> bool:
    """Set Video Out On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="EAh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_power_indicator(self, on: bool) -> bool:
    """Set Power Indicator On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="BEh",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def reset_multi_display_settings(self, reset_category: str) -> bool:
    """Reset multi-display settings (momentary command)."""
    category_map = {"no mean": "00", "reset": "01", "multi display": "02"}
    hex_value = category_map.get(reset_category.lower().replace(" ", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="CBh",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Reset (Multi Display) category: {reset_category}. Supported categories: {', '.join(category_map.keys())}."
        )
        return False


async def get_heat_status(self, fan_number: int) -> Optional[dict]:
    """Get the Heat Status for the specified fan (1, 2, or 3)."""
    if 1 <= fan_number <= 3:
        fan_code = f"{fan_number:x}".upper()
        response = await self._get_parameter(
            op_code="7Ah",
            op_code_page="02",
            params=fan_code.encode("ascii").zfill(2),
            message_type=b"C",
        )  # Assuming it's a Get command
        if (
            response and len(response.payload) == 4
        ):  # Adjust payload length based on actual response
            status_code = response.payload[2:4].decode("ascii")
            # Need to decode the status code based on documentation
            return {"fan": fan_number, "status_code": status_code}
        else:
            _LOGGER.warning(
                f"Unexpected response for Heat Status (Fan {fan_number}): {response.payload.hex() if response and response.payload else None}"
            )
            return None
    else:
        _LOGGER.warning("Fan number must be 1, 2, or 3.")
        return None


async def get_backlight_temperature_status(
    self, sensor_number: int
) -> Optional[dict]:
    """Get the Backlight and Temperature Status for the specified sensor (1, 2, or 3)."""
    if 1 <= sensor_number <= 3:
        sensor_code = f"{sensor_number:x}".upper()
        response = await self._get_parameter(
            op_code="79h",
            op_code_page="02",
            params=sensor_code.encode("ascii").zfill(2),
            message_type=b"C",
        )  # Assuming it's a Get command
        if (
            response and len(response.payload) >= 4
        ):  # Adjust payload length based on actual response
            status = response.payload[2:4].decode("ascii")
            temperature_hex = response.payload[
                4:...
            ]  # Remaining bytes are temperature
            try:
                temperature_celsius = (
                    int(temperature_hex, 16) * 0.5
                )  # Assuming 0.5 degree step
                return {
                    "sensor": sensor_number,
                    "status": status,
                    "temperature_celsius": temperature_celsius,
                }
            except ValueError:
                _LOGGER.warning(
                    f"Error parsing temperature for Sensor {sensor_number}: {temperature_hex}"
                )
                return None
        else:
            _LOGGER.warning(
                f"Unexpected response for Backlight/Temp Status (Sensor {sensor_number}): {response.payload.hex() if response and response.payload else None}"
            )
            return None
    else:
        _LOGGER.warning("Sensor number must be 1, 2, or 3.")
        return None


async def set_cooling_fan_control(self, mode: str) -> bool:
    """Set the Cooling Fan Control mode."""
    mode_map = {"no mean": "00", "auto": "01", "high": "02", "low": "03"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="75h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Cooling Fan Control mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_fan_speed(self, speed: str) -> bool:
    """Set the Fan Speed."""
    speed_map = {"high": "01", "low": "02"}
    hex_value = speed_map.get(speed.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="3Fh",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Fan Speed: {speed}. Supported speeds: {', '.join(speed_map.keys())}."
        )
        return False


# We need to refer to Chapters 19, 20, and 21 for details on
# Auto Tile Matrix Setup, Power Save, and Setting Copy.
async def auto_tile_matrix_setup(self) -> bool:
    _LOGGER.warning(
        "Auto Tile Matrix Setup requires information from Chapter 19."
    )
    return False


async def get_power_save_settings(self) -> Optional[dict]:
    _LOGGER.warning(
        "Getting Power Save settings requires information from Chapter 20."
    )
    return None


async def copy_settings(self, destination_id: int) -> bool:
    _LOGGER.warning("Copying settings requires information from Chapter 21.")
    return False


async def set_sensor_offset_celsius(
    self, sensor_number: int, offset: int
) -> bool:
    """Set the Celsius offset for the specified sensor (1, 2, or 3)."""
    if 1 <= sensor_number <= 3 and 0 <= offset <= 65535:
        op_code = f"E{sensor_number - 1:x}h".upper()
        hex_value = f"{offset:04x}".upper()
        return await self._set_parameter(
            op_code, "10", set_value=hex_value.encode("ascii").zfill(4)
        )
    else:
        _LOGGER.warning(
            f"Invalid sensor number ({sensor_number}) or Celsius offset ({offset}). Sensor must be 1-3, offset 0-65535."
        )
        return False


async def set_sensor_offset_normalized(
    self, sensor_number: int, offset: int
) -> bool:
    """Set the normalized offset (0-10) for the specified sensor (1, 2, or 3)."""
    if 1 <= sensor_number <= 3 and 0 <= offset <= 10:
        op_code = f"E{sensor_number + 2:x}h".upper()
        hex_value = f"{offset:02x}".upper()
        return await self._set_parameter(
            op_code, "10", set_value=hex_value.encode("ascii").zfill(4)
        )
    else:
        _LOGGER.warning(
            f"Invalid sensor number ({sensor_number}) or normalized offset ({offset}). Sensor must be 1-3, offset 0-10."
        )
        return False


async def set_screensaver_gamma(self, on: bool) -> bool:
    """Set Screen Saver Gamma On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="D8h",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_screensaver_backlight(self, on: bool) -> bool:
    """Set Screen Saver Backlight On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="DCh",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_screensaver_interval(self, interval_seconds: int) -> bool:
    """Set Screen Saver Interval (10-900 seconds, 10s steps)."""
    if 10 <= interval_seconds <= 900 and interval_seconds % 10 == 0:
        hex_value = f"{interval_seconds // 10:02x}".upper()
        return await self._set_parameter(
            op_code="DDh",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            "Screen Saver Interval must be between 10 and 900 seconds in steps of 10."
        )
        return False


async def set_screensaver_zoom(self, zoom_percent: int) -> bool:
    """Set Screen Saver Zoom (10-100%)."""
    if 10 <= zoom_percent <= 100:
        hex_value = (
            f"{zoom_percent * 10 // 105:02x}".upper()
        )  # Approximate mapping
        return await self._set_parameter(
            op_code="DFh",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Screen Saver Zoom must be between 10 and 100%.")
        return False


async def set_screensaver_side_border_color(self, color: str) -> bool:
    """Set Screen Saver Side Border Color (black or white)."""
    color_map = {"black": "00", "white": "01"}
    hex_value = color_map.get(color.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="DFh",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )  # Same OP code as Zoom - likely different parameter byte
    else:
        _LOGGER.warning(
            f"Invalid Screen Saver Side Border Color: {color}. Supported colors: black, white."
        )
        return False


async def reset_display_protection(self) -> bool:
    """Reset Display Protection settings (momentary command)."""
    return await self._set_parameter(
        op_code="CBh", op_code_page="02", set_value=b"0001"
    )  # Assuming '1' is the reset parameter


async def set_ddcci(self, enabled: bool) -> bool:
    """Enable or disable DDC/CI."""
    value = "01" if enabled else "00"
    return await self._set_parameter(
        op_code="BEh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def reset_external_control(self) -> bool:
    """Reset External Control settings (momentary command)."""
    return await self._set_parameter(
        op_code="CEh", op_code_page="02", set_value=b"0001"
    )  # Assuming '1' is the reset parameter


async def set_input_detect(self, detect_mode: str) -> bool:
    """Set the Input Detect mode."""
    mode_map = {
        "first detect": "01",
        "last detect": "02",
        "none": "03",
        "video detect": "04",
        "custom detect": "05",
    }
    hex_value = mode_map.get(detect_mode.lower().replace(" ", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="40h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input Detect mode: {detect_mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_custom_detect_priority(self, priority: str) -> bool:
    """Set the priority for Custom Detect."""
    priority_map = {
        "no mean": "00",
        "vga": "01",
        "rgb/hv": "02",
        "dvi": "03",
        "hdmi": "04",
    }
    hex_value = priority_map.get(priority.lower().replace("/", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="2Eh",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Custom Detect Priority: {priority}. Supported priorities: {', '.join(priority_map.keys())}."
        )
        return False


# We need to refer to Chapters 22 and 23 for details on
# Change Password and IP/MAC Address/LAN Power settings.
async def change_password(self) -> bool:
    _LOGGER.warning("Changing password requires information from Chapter 22.")
    return False


async def set_network_settings(self) -> bool:
    _LOGGER.warning(
        "Setting network (IP/MAC/LAN Power) requires information from Chapter 23."
    )
    return False


async def set_input_priority2(self, priority: str) -> bool:
    """Set the priority for Input 2."""
    priority_map = {
        "video": "05",
        "svideo2": "07",
        "ypbpr": "0c",
        "option": "0d",
        "ypbpr2": "0e",
        "rgb/hv2": "0f",
        "dport1": "16",
        "dport2": "17",
        "hdmi2": "18",
        "hdmi3": "80",
    }
    hex_value = priority_map.get(
        priority.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="2Fh",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input 2 Priority: {priority}. Supported priorities: {', '.join(priority_map.keys())}."
        )
        return False


async def set_input_priority3(self, priority: str) -> bool:
    """Set the priority for Input 3."""
    priority_map = {
        "video": "05",
        "svideo2": "07",
        "ypbpr": "0c",
        "option": "0d",
        "ypbpr2": "0e",
        "rgb/scart": "0f",
        "dport1": "16",
        "dport2": "17",
        "hdmi2": "18",
        "dport3": "80",
    }
    hex_value = priority_map.get(
        priority.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="30h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input 3 Priority: {priority}. Supported priorities: {', '.join(priority_map.keys())}."
        )
        return False


async def set_long_cable_comp(self, on: bool) -> bool:
    """Set Long Cable Compensation On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="1Dh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_long_cable_hog_peak(self, value: int) -> bool:
    """Set Long Cable Compensation HOG Peak (0-32)."""
    if 0 <= value <= 32:
        hex_value = f"{value:02x}".upper()
        return await self._set_parameter(
            op_code="37h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            "Long Cable Compensation HOG Peak must be between 0 and 32."
        )
        return False


async def set_long_cable_gain(self, value: int) -> bool:
    """Set Long Cable Compensation Gain (0-7)."""
    if 0 <= value <= 7:
        hex_value = f"{value:x}".upper()
        return await self._set_parameter(
            op_code="38h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            "Long Cable Compensation Gain must be between 0 and 7."
        )
        return False


async def set_rgb_hv_position(self, value: int) -> bool:
    """Set R-G H Position (0-7)."""
    if 0 <= value <= 7:
        hex_value = f"{value:x}".upper()
        return await self._set_parameter(
            op_code="58h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("R-G H Position must be between 0 and 7.")
        return False


async def set_b_y_h_position(self, value: int) -> bool:
    """Set B-Y H Position (0-7)."""
    if 0 <= value <= 7:
        hex_value = f"{value:x}".upper()
        return await self._set_parameter(
            op_code="59h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("B-Y H Position must be between 0 and 7.")
        return False


async def set_rgb_hv_position_v(self, value: int) -> bool:
    """Set R-G V Position (0-7)."""
    if 0 <= value <= 7:
        hex_value = f"{value:x}".upper()
        return await self._set_parameter(
            op_code="5Ah",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("R-G V Position must be between 0 and 7.")
        return False


async def set_b_y_position_v(self, value: int) -> bool:
    """Set B-Y V Position (0-7)."""
    if 0 <= value <= 7:
        hex_value = f"{value:x}".upper()
        return await self._set_parameter(
            op_code="5Bh",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("B-Y V Position must be between 0 and 7.")
        return False


async def set_sync_termination(self, impedance: str) -> bool:
    """Set Sync Termination impedance."""
    impedance_map = {"no mean": "00", "75 ohm": "01", "low": "02"}
    hex_value = impedance_map.get(impedance.lower().replace(" ", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="E1h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Sync Termination impedance: {impedance}. Supported options: {', '.join(impedance_map.keys())}."
        )
        return False


async def set_input_change(self, change_mode: str) -> bool:
    """Set the Input Change behavior."""
    mode_map = {"normal": "00", "quick": "01", "super": "02"}
    hex_value = mode_map.get(change_mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="86h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input Change mode: {change_mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_input1_source(self, input_source: str) -> bool:
    """Set the Input Source for Input 1."""
    source_map = {
        "no mean": "00",
        "vga": "01",
        "rgb/hv": "02",
        "dvi": "03",
        "hdmi": "04",
        "video": "05",
        "ypbpr": "0c",
        "option": "0d",
        "ypbpr2": "0e",
        "rgb/scart": "0f",
        "dport1": "16",
        "dport2": "17",
        "hdmi2": "18",
        "dport3": "80",
    }
    hex_value = source_map.get(
        input_source.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="CEh",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input 1 Source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def set_input2_source(self, input_source: str) -> bool:
    """Set the Input Source for Input 2."""
    source_map = {
        "no mean": "00",
        "vga": "01",
        "rgb/hv": "02",
        "dvi": "03",
        "hdmi": "04",
        "video": "05",
        "ypbpr": "0c",
        "option": "0d",
        "ypbpr2": "0e",
        "rgb/scart": "0f",
        "dport1": "16",
        "dport2": "17",
        "hdmi2": "18",
        "dport3": "80",
    }
    hex_value = source_map.get(
        input_source.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="CFh",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input 2 Source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def set_dvi_mode(self, mode: str) -> bool:
    """Set the DVI Mode."""
    mode_map = {"no mean": "00", "dvi-pc": "01", "dvi-hd": "02"}
    hex_value = mode_map.get(mode.lower().replace("-", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="CFh",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid DVI Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_bnc_mode(self, mode: str) -> bool:
    """Set the BNC Mode."""
    mode_map = {"no mean": "00", "rgb": "01", "component": "02"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="7Eh",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid BNC Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_dsub_mode(self, mode: str) -> bool:
    """Set the D-Sub Mode."""
    mode_map = {"no mean": "00", "rgb": "01", "component": "02"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="8Eh",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid D-Sub Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_scart_mode(self, on: bool) -> bool:
    """Set SCART Mode On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="9Eh",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def select_displayport(self, port: int) -> bool:
    """Select the target DisplayPort (1, 2, or 3)."""
    if 1 <= port <= 3:
        hex_value = f"{port - 1:x}".upper()
        return await self._set_parameter(
            op_code="F1h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("DisplayPort must be 1, 2, or 3.")
        return False


async def get_displayport_status(self) -> Optional[str]:
    """Read the status of the target DisplayPort."""
    response = await self._get_parameter(op_code="F2h", op_code_page="10")
    if response and response.current_value in [0, 1, 2]:
        status_map = {0: "No mean", 1: "1.1a", 2: "1.2"}
        return status_map.get(response.current_value)
    return None


async def set_hdmi_signal(self, format: str) -> bool:
    """Set the HDMI Signal format (1.1 or 1.2)."""
    format_map = {"1.1": "01", "1.2": "02"}
    hex_value = format_map.get(format.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="40h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("HDMI Signal format must be 1.1 or 1.2.")
        return False


async def set_deinterlace(self, on: bool) -> bool:
    """Set Deinterlace On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="25h",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_color_system(self, system: str) -> bool:
    """Set the Color System."""
    system_map = {
        "no mean": "00",
        "ntsc": "01",
        "pal": "02",
        "secam": "03",
        "auto": "04",
        "pal60": "05",
    }
    hex_value = system_map.get(system.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="21h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Color System: {system}. Supported systems: {', '.join(system_map.keys())}."
        )
        return False


async def set_overscan(self, on: bool) -> bool:
    """Set Over Scan On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="E3h",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_option_power(self, on: bool) -> bool:
    """Set Option Power On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="41h",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_audio_input_type(self, audio_type: str) -> bool:
    """Set Audio Input type (Analog or Digital)."""
    type_map = {"analog": "01", "digital": "02"}
    hex_value = type_map.get(audio_type.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="B6h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Audio Input type must be Analog or Digital.")
        return False


async def set_internal_pc_power(self, on: bool) -> bool:
    """Set Internal PC Power On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="C0h",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_internal_pc_warning(self, on: bool) -> bool:
    """Set Internal PC Warning On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="C1h",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_internal_pc_auto(self, on: bool) -> bool:
    """Set Internal PC Auto Power On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="C1h",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )  # Same OP code as Warning - likely different parameter


async def start_pc_force_quit(self) -> bool:
    """Start Internal PC Force Quit (momentary)."""
    return await self._set_parameter(
        op_code="C2h", op_code_page="10", set_value=b"0001"
    )  # Assuming '1' is execute


async def stop_pc_force_quit(self) -> bool:
    """Stop Internal PC Force Quit (momentary)."""
    return await self._set_parameter(
        op_code="C3h", op_code_page="10", set_value=b"0001"
    )  # Assuming '1' is execute


async def set_120hz_mode(self, on: bool) -> bool:
    """Set 120Hz Mode On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="B7h",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_touch_panel(self, on: bool) -> bool:
    """Set Touch Panel On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="C4h",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_pc_source(self, source: str) -> bool:
    """Set PC Source (Internal or Auto)."""
    source_map = {"internal": "01", "auto": "02"}
    hex_value = source_map.get(source.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="C5h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("PC Source must be Internal or Auto.")
        return False


async def reset_advanced_options(self) -> bool:
    """Reset Advanced Options (momentary)."""
    return await self._set_parameter(
        op_code="CBh",
        op_code_page="02",
        set_value="0A".encode("ascii").zfill(4),
    )  # Using the provided parameter


async def set_auto_brightness(self, on: bool) -> bool:
    """Set Auto Brightness On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="CBh",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )  # Same OP code as Reset - likely different parameter


async def set_room_light_sensing(self, mode: str) -> bool:
    """Set Room Light Sensing mode."""
    mode_map = {"off": "00", "model1": "01", "model2": "02"}
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="C8h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Room Light Sensing mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_backlight_max_limit(self, limit: int) -> bool:
    """Set Backlight Max Limit (0-100)."""
    if 0 <= limit <= 100:
        hex_value = f"{limit:02x}".upper()
        return await self._set_parameter(
            op_code="C9h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Backlight Max Limit must be between 0 and 100.")
        return False


async def set_human_sensing_bright_threshold(self, threshold: int) -> bool:
    """Set the Human Sensing Bright Threshold (0-100)."""
    if 0 <= threshold <= 100:
        hex_value = f"{threshold:02x}".upper()
        return await self._set_parameter(
            op_code="33h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            "Human Sensing Bright Threshold must be between 0 and 100."
        )
        return False


async def set_human_sensing_dark_threshold(self, threshold: int) -> bool:
    """Set the Human Sensing Dark Threshold (0-100)."""
    if 0 <= threshold <= 100:
        hex_value = f"{threshold:02x}".upper()
        return await self._set_parameter(
            op_code="34h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            "Human Sensing Dark Threshold must be between 0 and 100."
        )
        return False


async def get_illuminance(self) -> Optional[int]:
    """Get the current illuminance (Read Only)."""
    response = await self._get_parameter(op_code="B4h", op_code_page="02")
    if response:
        try:
            return response.current_value
        except ValueError:
            _LOGGER.warning(
                f"Could not parse illuminance value: {response.payload.hex()}"
            )
            return None
    return None


async def set_human_sensing_mode(self, mode: str) -> bool:
    """Set the Human Sensing Mode."""
    mode_map = {
        "no mean": "00",
        "disable": "01",
        "auto off": "02",
        "custom": "04",
    }
    hex_value = mode_map.get(mode.lower().replace(" ", "_"))
    if hex_value:
        return await self._set_parameter(
            op_code="75h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Human Sensing Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_backlight_on(self, on: bool) -> bool:
    """Set Backlight On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="DDh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_backlight_level(self, level: int) -> bool:
    """Set Backlight Level (0-100)."""
    if 0 <= level <= 100:
        hex_value = f"{level:02x}".upper()
        return await self._set_parameter(
            op_code="C6h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Backlight Level must be between 0 and 100.")
        return False


async def set_volume_on(self, on: bool) -> bool:
    """Set Volume On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="DFh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )  # Note: Same OP code as Input On/Off - likely different parameter


async def set_volume_level(self, level: int) -> bool:
    """Set Volume Level (0-100)."""
    if 0 <= level <= 100:
        hex_value = f"{level:02x}".upper()
        return await self._set_parameter(
            op_code="C7h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Volume Level must be between 0 and 100.")
        return False


async def set_input_select_on(self, on: bool) -> bool:
    """Set Input Select On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="DFh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )  # Note: Same OP code as Volume On/Off - likely different parameter


async def set_input_source(self, input_source: str) -> bool:
    """Set the Input Source."""
    source_map = {
        "no mean": "00",
        "vga": "01",
        "rgb/hv": "02",
        "dvi": "03",
        "hdmi": "04",
        "video": "05",
        "ypbpr": "0c",
        "option": "0d",
        "ypbpr2": "0e",
        "rgb/scart": "0f",
        "dport1": "16",
        "dport2": "17",
        "hdmi2": "18",
        "dport3": "80",
    }
    hex_value = source_map.get(
        input_source.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="D0h",
            op_code_page="10",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input Source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def set_waiting_time(self, seconds: int) -> bool:
    """Set the Waiting Time (short or long)."""
    if seconds == 30:
        hex_value = "01"
    elif (
        600 <= seconds <= 25500
    ):  # Long wait, 1-second step (30h - 19Eh in hex)
        hex_value = (
            f"{seconds // 1:02x}".upper()
        )  # Assuming direct hex representation of seconds
    else:
        _LOGGER.warning(
            "Waiting Time must be 30 seconds (short) or between 600 and 25500 seconds (long)."
        )
        return False
    return await self._set_parameter(
        op_code="78h",
        op_code_page="10",
        set_value=hex_value.encode("ascii").zfill(4),
    )


async def set_intelli_wireless_data(self, on: bool) -> bool:
    """Set Intelli Wireless Data On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="ECh",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def reset_advanced_options2(self) -> bool:
    """Reset Advanced Options 2 (momentary)."""
    return await self._set_parameter(
        op_code="CBh",
        op_code_page="02",
        set_value="0Bh".encode("ascii").zfill(4),
    )  # Using the provided parameter


async def factory_reset(self) -> bool:
    """Perform a Factory Reset (momentary)."""
    return await self._set_parameter(
        op_code="CBh",
        op_code_page="02",
        set_value="0Ch".encode("ascii").zfill(4),
    )  # Using the provided parameter


async def set_input_direct(self, input_source: str) -> bool:
    """Directly select the Input Source (alternative OP code)."""
    source_map = {
        "no mean": "00",
        "vga": "01",
        "rgb/hv": "02",
        "dvi": "03",
        "hdmi": "04",
        "video": "05",
        "svideo": "07",
        "ypbpr": "0c",
        "option": "0d",
        "ypbpr2": "0e",
        "rgb/scart": "0f",
        "dport1": "15",
        "dport2": "16",
        "hdmi2": "17",
        "dport3": "80",
    }
    hex_value = source_map.get(
        input_source.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="60h",
            op_code_page="00",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Input Source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def set_audio_input_direct(self, input_source: str) -> bool:
    """Directly select the Audio Input Source (alternative OP code)."""
    source_map = {
        "no mean": "00",
        "in1": "01",
        "in2": "02",
        "in3": "03",
        "hdmi": "04",
        "option": "06",
        "dport1": "08",
        "dport2": "09",
        "hdmi2": "0a",
        "hdmi3": "0b",
    }
    hex_value = source_map.get(
        input_source.lower().replace("-", "").replace(" ", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="2Eh",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Audio Input source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def volume_up(self) -> bool:
    """Increase the Volume."""
    return await self._set_parameter(
        op_code="62h", op_code_page="00", set_value=b"0001"
    )  # Assuming '1' is the parameter for up


async def volume_down(self) -> bool:
    """Decrease the Volume."""
    return await self._set_parameter(
        op_code="62h", op_code_page="00", set_value=b"0000"
    )  # Assuming '0' is the parameter for down


async def set_mute(self, on: bool) -> bool:
    """Set Mute On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="80h",
        op_code_page="00",
        set_value=value.encode("ascii").zfill(4),
    )


async def unmute_set_only(self) -> bool:
    """Unmute (Set only) - may behave differently from standard unmute."""
    return await self._set_parameter(
        op_code="80h", op_code_page="00", set_value=b"0101"
    )  # Assuming '01' is the parameter for unmute (set only)


async def set_screen_mute(self, on: bool) -> bool:
    """Set Screen Mute On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="B6h",
        op_code_page="10",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_mts_mode(self, mode: str) -> bool:
    """Set MTS (Mono/Stereo) Mode."""
    mode_map = {
        "no mean": "00",
        "mono": "01",
        "stereo": "02",
        "main": "03",
        "sub": "04",
        "main + sub": "05",
    }
    hex_value = mode_map.get(mode.lower().replace(" + ", "_"))
    if hex_value:
        return await self._set_parameter(
            op_code="2Ch",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid MTS Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_sound(self, on: bool) -> bool:
    """Set Sound On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="34h",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def set_picture_mode(self, mode: str) -> bool:
    """Set the Picture Mode."""
    mode_map = {
        "no mean": "00",
        "srgb": "01",
        "highbright": "03",
        "standard": "04",
        "cinema": "06",
        "custom1": "08",
        "custom2": "09",
    }
    hex_value = mode_map.get(mode.lower())
    if hex_value:
        return await self._set_parameter(
            op_code="1Ah",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Picture Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_aspect_ratio_direct(self, aspect: str) -> bool:
    """Set the Aspect Ratio (alternative OP code)."""
    aspect_map = {
        "no mean": "00",
        "normal": "01",
        "full": "02",
        "wide": "03",
        "zoom": "04",
        "dynamic": "06",
        "1:1": "07",
    }
    hex_value = aspect_map.get(aspect.lower().replace(":", ""))
    if hex_value:
        return await self._set_parameter(
            op_code="70h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid Aspect Ratio: {aspect}. Supported modes: {', '.join(aspect_map.keys())}."
        )
        return False


async def set_pip_still(self, mode: str) -> bool:
    """Control PIP On/Off and Still On/Off."""
    mode_map = {
        "no mean": "00",
        "off": "01",
        "pip": "02",
        "pop": "03",
        "still": "04",
        "picture by picture": "05",
        "picture by picture full": "06",
    }
    hex_value = mode_map.get(mode.lower().replace(" ", "_").replace("-", "_"))
    if hex_value:
        return await self._set_parameter(
            op_code="72h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid PIP/Still Mode: {mode}. Supported modes: {', '.join(mode_map.keys())}."
        )
        return False


async def set_pip_input_direct(self, input_source: str) -> bool:
    """Directly select the PIP Input Source (alternative OP code)."""
    source_map = {
        "no mean": "00",
        "vga": "01",
        "rgb/hv": "02",
        "dvi": "03",
        "hdmi (set only)": "04",
        "video": "07",
        "ypbpr": "0c",
        "option": "0d",
        "ypbpr2": "0e",
        "rgb/scart": "0f",
        "dport1": "15",
        "dport2": "16",
        "hdmi2": "1b",
        "hdmi3": "80",
    }
    hex_value = source_map.get(
        input_source.lower().replace("/", "").replace(" ", "").replace("-", "")
    )
    if hex_value:
        return await self._set_parameter(
            op_code="73h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning(
            f"Invalid PIP Input source: {input_source}. Supported sources: {', '.join(source_map.keys())}."
        )
        return False


async def trigger_still_capture(self) -> bool:
    """Trigger Still Capture (momentary)."""
    return await self._set_parameter(
        op_code="76h", op_code_page="02", set_value=b"0001"
    )  # Assuming '1' is the trigger


async def set_signal_information_display(self, on: bool) -> bool:
    """Set Signal Information Display On/Off."""
    value = "01" if on else "00"
    return await self._set_parameter(
        op_code="EAh",
        op_code_page="02",
        set_value=value.encode("ascii").zfill(4),
    )


async def trigger_auto_setup(self) -> bool:
    """Trigger Auto Setup (momentary)."""
    return await self._set_parameter(
        op_code="1Eh", op_code_page="00", set_value=b"0001"
    )  # Assuming '1' is the trigger


async def tv_channel_up(self) -> bool:
    """Navigate TV Channel Up (requires TV tuner)."""
    return await self._set_parameter(
        op_code="8Bh", op_code_page="00", set_value=b"0001"
    )  # Assuming '1' is the parameter for up


async def tv_channel_down(self) -> bool:
    """Navigate TV Channel Down (requires TV tuner)."""
    return await self._set_parameter(
        op_code="8Bh", op_code_page="00", set_value=b"0000"
    )  # Assuming '0' is the parameter for down


async def select_temperature_sensor(self, sensor_number: int) -> bool:
    """Select the Temperature Sensor to read (1, 2, or 3)."""
    if 1 <= sensor_number <= 3:
        hex_value = f"{sensor_number:x}".upper()
        return await self._set_parameter(
            op_code="78h",
            op_code_page="02",
            set_value=hex_value.encode("ascii").zfill(4),
        )
    else:
        _LOGGER.warning("Sensor number must be 1, 2, or 3.")
        return False


async def readout_temperature(self) -> Optional[float]:
    """Read the temperature from the selected sensor (returns in Celsius)."""
    response = await self._get_parameter(op_code="79h", op_code_page="02")
    if response and len(response.payload) == 4:
        try:
            hex_temp = response.payload[2:4].decode("ascii")
            int_temp = int(hex_temp, 16)
            # Assuming 2's complement for negative values (check section 6.2)
            if int_temp > 127:
                int_temp -= 256
            return float(int_temp)
        except ValueError:
            _LOGGER.warning(
                f"Could not parse temperature value: {response.payload.hex()}"
            )
            return None
    else:
        _LOGGER.warning(
            f"Unexpected response for temperature readout: {response.payload.hex() if response and response.payload else None}"
        )
        return None


async def readout_carbon_footprint_grams(self) -> Optional[int]:
    """Read the Carbon Footprint in grams (Read Only)."""
    response = await self._get_parameter(op_code="10h", op_code_page="10")
    if response:
        try:
            return response.current_value
        except ValueError:
            _LOGGER.warning(
                f"Could not parse carbon footprint (g) value: {response.payload.hex()}"
            )
            return None
    return None


async def readout_carbon_footprint_kg(self) -> Optional[float]:
    """Read the Carbon Footprint in kilograms (Read Only)."""
    response = await self._get_parameter(op_code="11h", op_code_page="10")
    if response:
        try:
            return response.current_value / 1000.0
        except ValueError:
            _LOGGER.warning(
                f"Could not parse carbon footprint (kg) value: {response.payload.hex()}"
            )
            return None
    return None


async def readout_carbon_usage_grams(self) -> Optional[int]:
    """Read the Carbon Usage in grams (Read Only)."""
    response = await self._get_parameter(op_code="26h", op_code_page="10")
    if response:
        try:
            return response.current_value
        except ValueError:
            _LOGGER.warning(
                f"Could not parse carbon usage (g) value: {response.payload.hex()}"
            )
            return None
    return None


async def readout_carbon_usage_kg(self) -> Optional[float]:
    """Read the Carbon Usage in kilograms (Read Only)."""
    response = await self._get_parameter(op_code="27h", op_code_page="10")
    if response:
        try:
            return response.current_value / 1000.0
        except ValueError:
            _LOGGER.warning(
                f"Could not parse carbon usage (kg) value: {response.payload.hex()}"
            )
            return None
    return None


def _calculate_bcc(self, data: bytes) -> bytes:
    """Calculates the Block Check Character (XOR of all bytes)."""
    bcc = 0
    for byte in data:
        bcc ^= byte
    return bytes([bcc])


async def get_power_status(self) -> Optional[str]:
    """Gets the current power status of the monitor."""
    monitor_id_hex = f"{self._monitor_id:02X}"[0].encode(
        "ascii"
    )  # Assuming _monitor_id is an integer

    header = b"\x01" + b"0" + monitor_id_hex + b"0" + b"A" + b"6"
    message = b"\x02" + b"0" + b"1" + b"\x03"
    data_to_checksum = header + message
    bcc = self._calculate_bcc(data_to_checksum)
    command = data_to_checksum + bcc + b"\x0d"

    self._serial.write(command)
    await asyncio.sleep(0.1)  # Give time for response

    response = self._serial.read(1024)  # Adjust buffer size as needed
    if response:
        if (
            response[5:6] == b"8"
            and response[6:7] == b"\x02"
            and response[9:10] == b"4"
        ):
            status_byte = response[10:11]
            if status_byte == b"\x00":
                return "ON"
            elif status_byte == b"\x01":
                return "STANDBY"
            elif status_byte == b"\x02":
                return "SUSPEND"
            elif status_byte == b"\x04":
                return "OFF"
            else:
                _LOGGER.warning(f"Unknown power status: {status_byte.hex()}")
                return None
        else:
            _LOGGER.warning(
                f"Unexpected power status response: {response.hex()}"
            )
            return None
    else:
        _LOGGER.warning("No response received for power status request.")
        return None


async def set_power_state(self, power_state: str) -> bool:
    """Sets the power state of the monitor."""
    monitor_id_hex = f"{self._monitor_id:02X}"[0].encode("ascii")

    power_mode_map = {
        "on": b"\x01",
        "standby": b"\x01",
        "suspend": b"\x02",
        "off": b"\x04",
    }
    power_mode = power_mode_map.get(power_state.lower())
    if not power_mode:
        _LOGGER.warning(
            f"Invalid power state: {power_state}. Supported states: on, standby, suspend, off."
        )
        return False

    header = b"\x01" + b"0" + monitor_id_hex + b"0" + b"A" + b"\x0c"
    message = b"\x02" + b"1" + b"0" + b"0" + b"1" + power_mode + b"\x03"
    data_to_checksum = header + message
    bcc = self._calculate_bcc(data_to_checksum)
    command = data_to_checksum + bcc + b"\x0d"

    _LOGGER.debug(f"Sending power command: {command.hex()}")
    self._serial.write(command)
    await asyncio.sleep(0.1)  # Give time for response

    response = self._serial.read(1024)  # Adjust buffer size as needed
    if response:
        _LOGGER.debug(f"Received power response: {response.hex()}")
        if (
            response[5:6] == b"E"
            and response[6:7] == b"\x02"
            and response[7:8] == b"1"
            and response[8:9] == b"0"
        ):
            responded_power_mode = response[11:12]
            if responded_power_mode == power_mode:
                _LOGGER.info(f"Successfully set power state to: {power_state}")
                return True
            else:
                _LOGGER.warning(
                    f"Power state set command acknowledged, but reported state is different: {responded_power_mode.hex()}"
                )
                return False
        else:
            _LOGGER.warning(
                f"Unexpected power control response: {response.hex()}"
            )
            return False
    else:
        _LOGGER.warning("No response received for power control command.")
        return False
