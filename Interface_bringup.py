import os
import subprocess
import sys


class PiHardwareInit:
    def __init__(self):
        self.reboot_required = False

    # ---------------------------
    # Helper
    # ---------------------------
    def _run(self, cmd):
        try:
            result = subprocess.run(
                cmd, shell=True, check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return e.stderr.strip()

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
        self._run("sudo raspi-config nonint do_spi 0")
        self.reboot_required = True

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
        self._run("sudo raspi-config nonint do_i2c 0")
        self.reboot_required = True

    # ===========================
    # CAN FD (MCP2517FD/2518FD)
    # ===========================
    def _canfd_configured(self):
        try:
            with open("/boot/config.txt", "r") as f:
                return "mcp251xfd" in f.read()
        except:
            return False

    def _enable_canfd(self):
        if self._canfd_configured():
            print("✅ CAN FD already configured")
            return

        print("🔧 Enabling CAN FD (MCP2517FD/2518FD)...")

        lines = [
            "\n# CAN FD Setup",
            "dtparam=spi=on",
            "dtoverlay=mcp251xfd,spi0-0,interrupt=25",
            "dtoverlay=spi-bcm2835"
        ]

        try:
            with open("/boot/config.txt", "a") as f:
                f.write("\n".join(lines) + "\n")

            self.reboot_required = True
            print("✅ CAN FD config added")

        except Exception as e:
            print(f"❌ Failed to configure CAN FD: {e}")

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
            return

        if self._can_up():
            print("✅ CAN FD already UP")
            return

        print("🔧 Bringing up CAN FD...")

        # CAN FD specific settings
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
    # Reboot Handler
    # ===========================
    def _handle_reboot(self):
        if self.reboot_required:
            print("\n⚠️ Reboot required. Rebooting now...\n")
            sys.stdout.flush()
            subprocess.run("sudo reboot", shell=True)
            sys.exit(0)

    # ===========================
    # PUBLIC METHOD (CALL THIS)
    # ===========================
    def initialize(self):
        """
        Call this from your main application.
        Safe to call multiple times.
        """

        print("\n===== HW INIT (SPI + I2C + CAN FD) =====\n")

        self._enable_spi()
        self._enable_i2c()
        self._enable_canfd()

        # Reboot if first-time setup
        self._handle_reboot()

        # After reboot or if already configured
        print("\n--- CAN FD Bring-up ---")
        self._bringup_canfd()

        print("\n===== INIT COMPLETE =====\n")
