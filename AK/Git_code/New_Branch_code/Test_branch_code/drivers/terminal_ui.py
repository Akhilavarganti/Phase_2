import atexit
import getpass
import select
import sys

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None


class TerminalDisplay:
    def __init__(self):
        self.wifi_status = "W-"
        self._last_rendered_output = None

    def set_wifi_status(self, status):
        self.wifi_status = status

    def clear(self):
        self._last_rendered_output = None
        # Clear terminal and move cursor to top-left.
        print("\033[2J\033[H", end="")

    def display_text(self, text, line=0):
        del line
        self.display_centered_text(text)

    def display_centered_text(self, text):
        rendered_output = f"[WiFi: {self.wifi_status}]\n{text}"
        if rendered_output == self._last_rendered_output:
            return
        self._last_rendered_output = rendered_output
        print("\033[2J\033[H", end="")
        print(rendered_output)


class DisplayRouter:
    def __init__(self, *displays):
        self.displays = [display for display in displays if display is not None]

    def set_wifi_status(self, status):
        for display in self.displays:
            display.set_wifi_status(status)

    def clear(self):
        for display in self.displays:
            display.clear()

    def display_text(self, text, line=0):
        for display in self.displays:
            display.display_text(text, line=line)

    def display_centered_text(self, text):
        for display in self.displays:
            display.display_centered_text(text)


class TerminalInput:
    def __init__(self):
        self.stdin = sys.stdin
        self.enabled = False
        self._original_termios = None
        self._line_buffer = ""
        self._setup_terminal()

    def _setup_terminal(self):
        if termios is None or tty is None:
            return
        if not self.stdin.isatty():
            return
        try:
            self._original_termios = termios.tcgetattr(self.stdin.fileno())
            tty.setcbreak(self.stdin.fileno())
            atexit.register(self.restore)
            self.enabled = True
        except Exception:
            self.enabled = False

    def restore(self):
        if not self.enabled or self._original_termios is None:
            return
        try:
            termios.tcsetattr(
                self.stdin.fileno(),
                termios.TCSADRAIN,
                self._original_termios
            )
        except Exception:
            pass

    def is_available(self):
        return self.enabled

    def _read_char(self, timeout=0):
        if not self.enabled:
            return None
        readable, _, _ = select.select([self.stdin], [], [], timeout)
        if not readable:
            return None
        return self.stdin.read(1)

    def read_key(self, timeout=0):
        char = self._read_char(timeout=timeout)
        if char is None:
            return None

        if char == "\x1b":
            next_char = self._read_char(timeout=0.01)
            if next_char == "[":
                arrow = self._read_char(timeout=0.01)
                return {
                    "A": "UP",
                    "B": "DOWN",
                    "C": "RIGHT",
                    "D": "LEFT"
                }.get(arrow, "ESC")
            return "ESC"

        if char in ("\r", "\n"):
            return "ENTER"
        if char in ("\x08", "\x7f"):
            return "BACKSPACE"
        if char == "\t":
            return "TAB"
        if char == " ":
            return "SPACE"
        return char

    def poll_action(self, timeout=0.1):
        key = self.read_key(timeout=timeout)
        if key is None:
            return None
        if key in {"LEFT", "UP", "a", "A", "p", "P"}:
            return "prev"
        if key in {"RIGHT", "DOWN", "d", "D", "n", "N"}:
            return "next"
        if key in {"ENTER", "s", "S"}:
            return "select"
        if key in {"ESC", "q", "Q"}:
            return "cancel"
        if isinstance(key, str) and key.isdigit():
            return ("digit", int(key))
        return None

    def prompt_password(self, ssid):
        self.restore()
        try:
            return getpass.getpass(f"Enter password for '{ssid}': ")
        finally:
            self._setup_terminal()
