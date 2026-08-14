import os
import sys
import subprocess
import logging
import pwd


class ServiceInstaller:

    @staticmethod
    def install():

        home = os.path.expanduser("~")
        service_dir = os.path.join(home, ".config", "systemd", "user")
        os.makedirs(service_dir, exist_ok=True)

        service_path = os.path.join(service_dir, "uds.service")

        # Get executable path
        if getattr(sys, "frozen", False):
            exe_path = os.path.realpath(sys.executable)
        else:
            exe_path = os.path.realpath(sys.argv[0])

        working_dir = os.path.dirname(exe_path)
        uid = os.getuid()
        username = pwd.getpwuid(uid).pw_name

        service_text = f"""[Unit]
Description=UDS Diagnostics
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={working_dir}
ExecStart={exe_path}

Restart=always
RestartSec=5

Environment=PYTHONUNBUFFERED=1
Environment=XDG_RUNTIME_DIR=/run/user/{uid}
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus

[Install]
WantedBy=default.target
"""

        try:
            # Only write the service if it's new or has changed
            write_service = True

            if os.path.exists(service_path):
                with open(service_path, "r") as f:
                    if f.read() == service_text:
                        write_service = False

            if write_service:
                logging.info("Installing/Updating uds.service...")

                with open(service_path, "w") as f:
                    f.write(service_text)

                subprocess.run(
                    ["systemctl", "--user", "daemon-reload"],
                    check=True
                )

                subprocess.run(
                    ["systemctl", "--user", "enable", "uds.service"],
                    check=True
                )

                logging.info("uds.service installed successfully.")
            else:
                logging.info("uds.service already up-to-date.")

            # Enable linger (ignore failure)
            result = subprocess.run(
                ["sudo", "loginctl", "enable-linger", username],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logging.info("User lingering enabled.")
            else:
                logging.warning(
                    f"Could not enable lingering: {result.stderr.strip()}"
                )

        except Exception as e:
            logging.error(f"Service installation failed: {e}")