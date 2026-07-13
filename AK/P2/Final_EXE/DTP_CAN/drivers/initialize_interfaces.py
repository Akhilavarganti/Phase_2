import os
import subprocess
import sys
from drivers import oled_display

class interface:
    def __init__(self):
        self.reboot_required = False
        self.config_file = "/boot/firmware/config.txt"

    # ---------------------------
    # Command runner
    # ---------------------------
    def _run(self, cmd):
        print(f"➡️ {cmd}")
        result = subprocess.run(
            cmd, shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            print(f"❌ {result.stderr.strip()}")
        return result.stdout.strip()

    # ---------------------------
    # Safe append using sudo
    # ---------------------------
    def _append_line_root(self, line):
        check = subprocess.run(
            f"grep -qxF '{line}' {self.config_file}",
            shell=True
        )

        if check.returncode == 0:
            return False  # already exists

        self._run(f"echo '{line}' | sudo tee -a {self.config_file} > /dev/null")
        return True

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
        if self._append_line_root("dtparam=spi=on"):
            self.reboot_required = True
            print("✅ SPI enabled (reboot required)")

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
        if self._append_line_root("dtparam=i2c_arm=on"):
            self.reboot_required = True
            print("✅ I2C enabled (reboot required)")

    # ===========================
    # CAN FD
    # ===========================
    def _canfd_configured(self):
        result = subprocess.run(
            f"grep -q mcp251xfd {self.config_file}",
            shell=True
        )
        return result.returncode == 0

    def _enable_canfd(self):
        if self._canfd_configured():
            print("✅ CAN FD already configured")
            return

        print("🔧 Enabling CAN FD...")

        changes = False
        changes |= self._append_line_root("# CAN FD Setup")
        changes |= self._append_line_root("dtparam=spi=on")
        changes |= self._append_line_root(
            "dtoverlay=mcp251xfd,spi0-0,interrupt=25"
        )
        changes |= self._append_line_root("dtoverlay=mcp251xfd,spi1-0,interrupt=24")

        if changes:
            self.reboot_required = True
            print("✅ CAN FD config added (reboot required)")

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
            print("❌ CAN FD interface not found (reboot needed)")
            #self.oled.display_centered_text("CAN FD interface not found (reboot needed)")
            return

        if self._can_up():
            print("✅ CAN FD already UP")
            return

        print("🔧 Bringing up CAN FD...")

        self._run("sudo ip link set can0 down")
        self._run(
            "sudo ip link set can0 up type can bitrate 1000000 dbitrate 8000000 restart-ms 1000 berr-reporting on fd on"
        )
        self._run("sudo ip link set can0 up")

        if self._can_up():
            print("✅ CAN FD is UP")
            #self.oled.display_centered_text("CAN FD is UP")
        else:
            print("❌ CAN FD bring-up failed")
            #self.oled.display_centered_text("CAN FD bring-up failed")

    # ===========================
    # Reboot
    # ===========================
    def _handle_reboot(self):
        if self.reboot_required:
            print("\n⚠️ Reboot required. Rebooting...\n")
            sys.stdout.flush()
            subprocess.run("sudo reboot", shell=True)
            sys.exit(0)
        else:
            print("\n✅ No reboot required")

    # ===========================
    # PUBLIC ENTRY
    # ===========================
    def initialize(self):
        print("\n===== HARDWARE INIT =====\n")
        
        self._enable_spi()
        self._enable_i2c()
        self._enable_canfd()

        self._handle_reboot()

        print("\n--- CAN FD Bring-up ---")
        self._bringup_canfd()

        print("\n===== DONE =====\n")
