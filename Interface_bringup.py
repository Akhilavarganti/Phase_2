import os
import subprocess
import sys


class PiHardwareInit:
    def __init__(self):
        self.reboot_required = False
        self.config_file = "/boot/config.txt"

    # ===========================
    # Helper: Run shell command
    # ===========================
    def _run(self, cmd):
        print(f"➡️ {cmd}")
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode != 0:
                print(f"❌ Error: {result.stderr.strip()}")
            return result.stdout.strip()
        except Exception as e:
            print(f"❌ Exception: {e}")
            return ""

    # ===========================
    # File helper
    # ===========================
    def _file_contains(self, text):
        try:
            with open(self.config_file, "r") as f:
                return text in f.read()
        except:
            return False

    def _append_if_missing(self, line):
        if not self._file_contains(line):
            with open(self.config_file, "a") as f:
                f.write(line + "\n")
            return True
        return False

    # ===========================
    # SPI
    # ===========================
    def _spi_enabled(self):
        return os.path.exists("/dev/spidev0.0")

    def _enable_spi(self):
        if self._spi_enabled():
            print("✅ SPI already enabled")
            return

        print("🔧 Enabling SPI...")

        changed = self._append_if_missing("dtparam=spi=on")

        if changed:
            self.reboot_required = True
            print("✅ SPI enabled (reboot required)")
        else:
            print("⚠️ SPI config already present")

    # ===========================
    # I2C
    # ===========================
    def _i2c_enabled(self):
        return os.path.exists("/dev/i2c-1")

    def _enable_i2c(self):
        if self._i2c_enabled():
            print("✅ I2C already enabled")
            return

        print("🔧 Enabling I2C...")

        changed = self._append_if_missing("dtparam=i2c_arm=on")

        if changed:
            self.reboot_required = True
            print("✅ I2C enabled (reboot required)")
        else:
            print("⚠️ I2C config already present")

    # ===========================
    # CAN FD (MCP2517FD / MCP2518FD)
    # ===========================
    def _canfd_configured(self):
        return self._file_contains("mcp251xfd")

    def _enable_canfd(self):
        if self._canfd_configured():
            print("✅ CAN FD already configured")
            return

        print("🔧 Enabling CAN FD...")

        changes = False

        changes |= self._append_if_missing("# CAN FD Setup")
        changes |= self._append_if_missing("dtparam=spi=on")
        changes |= self._append_if_missing(
            "dtoverlay=mcp251xfd,spi0-0,interrupt=25"
        )
        changes |= self._append_if_missing("dtoverlay=spi-bcm2835")

        if changes:
            self.reboot_required = True
            print("✅ CAN FD config added (reboot required)")
        else:
            print("⚠️ CAN FD config already exists")

    # ===========================
    # CAN FD Bring-up
    # ===========================
    def _can_exists(self):
        return os.path.exists("/sys/class/net/can0")

    def _can_up(self):
        output = self._run("ip link show can0")
        return "UP" in output

    def _bringup_canfd(self):
        if not self._can_exists():
            print("❌ CAN FD interface not found (reboot likely needed)")
            return

        if self._can_up():
            print("✅ CAN FD already UP")
            return

        print("🔧 Bringing up CAN FD...")

        self._run("sudo ip link set can0 down")
        self._run(
            "sudo ip link set can0 type can bitrate 500000 dbitrate 2000000 fd on"
        )
        self._run("sudo ip link set can0 up")

        if self._can_up():
            print("✅ CAN FD is UP")
        else:
            print("❌ CAN FD bring-up failed")

    # ===========================
    # Reboot handler
    # ===========================
    def _handle_reboot(self):
        if self.reboot_required:
            print("\n⚠️ Reboot required. Rebooting now...\n")
            sys.stdout.flush()
            subprocess.run("sudo reboot", shell=True)
            sys.exit(0)
        else:
            print("\n✅ No reboot required")

    # ===========================
    # PUBLIC ENTRY POINT
    # ===========================
    def initialize(self):
        print("\n===== INITIALIZING HARDWARE =====\n")

        self._enable_spi()
        self._enable_i2c()
        self._enable_canfd()

        # Reboot if needed (first-time setup)
        self._handle_reboot()

        # After reboot or if already configured
        print("\n--- CAN FD Bring-up ---")
        self._bringup_canfd()

        print("\n===== INITIALIZATION COMPLETE =====\n")
