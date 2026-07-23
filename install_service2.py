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
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
WorkingDirectory={working_dir}

Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/{username}/.Xauthority
Environment=PYTHONUNBUFFERED=1

ExecStart=/bin/bash -c 'if command -v lxterminal >/dev/null 2>&1 && [ -n "$DISPLAY" ]; then exec lxterminal -e "{exe_path}"; else exec "{exe_path}"; fi'

Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
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