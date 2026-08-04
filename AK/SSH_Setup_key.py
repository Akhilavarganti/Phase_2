import os
import subprocess
import logging
import textwrap


class ssh_key_setup:

    @staticmethod
    def run_cmd(cmd):
        return subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )

    @staticmethod
    def ensure_openssh():
        logging.info("Checking openssh-client...")

        result = ssh_key_setup.run_cmd("which ssh-agent")

        if result.returncode != 0:
            logging.info("Installing openssh-client...")
            subprocess.run(
                "sudo apt update && sudo apt install -y openssh-client",
                shell=True,
                check=True
            )
        else:
            logging.info("openssh-client already installed.")

    @staticmethod
    def ensure_ssh_agent():

        if "SSH_AUTH_SOCK" in os.environ:
            logging.info("ssh-agent already running.")
            return

        logging.info("Starting ssh-agent...")

        agent = subprocess.run(
            ["ssh-agent", "-s"],
            capture_output=True,
            text=True,
            check=True
        )

        for line in agent.stdout.splitlines():

            if "=" in line and ";" in line:

                key, value = line.split(";", 1)[0].split("=", 1)
                os.environ[key] = value

        logging.info("ssh-agent started successfully.")

    @staticmethod
    def ensure_keys(ssh_dir, private_key_content, public_key_content):

        ssh_dir = os.path.expanduser(ssh_dir)

        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)

        private_key_path = os.path.join(
            ssh_dir,
            "diagtestpi_bitbucket"
        )

        public_key_path = private_key_path + ".pub"

        logging.info("Writing private key...")

        with open(private_key_path, "w") as f:
            f.write(private_key_content.strip() + "\n")

        os.chmod(private_key_path, 0o600)

        logging.info("Writing public key...")

        with open(public_key_path, "w") as f:
            f.write(public_key_content.strip() + "\n")

        os.chmod(public_key_path, 0o644)

        logging.info("Validating private key...")

        result = subprocess.run(
            ["ssh-keygen", "-lf", private_key_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Invalid private key:\n" + result.stderr
            )

        logging.info("Private key validated successfully.")

        return private_key_path

    @staticmethod
    def add_key_to_agent(private_key_path):

        logging.info("Checking existing keys in ssh-agent...")

        result = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True,
            text=True
        )

        if private_key_path in result.stdout:
            logging.info("Key already present in ssh-agent.")
            return

        logging.info("Adding key to ssh-agent...")

        result = subprocess.run(
            ["ssh-add", private_key_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Failed to add SSH key:\n" + result.stderr
            )

        logging.info("SSH key added successfully.")

    @staticmethod
    def setup_ssh():

        PRIVATE_KEY = textwrap.dedent("""\
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACA7J7oiJbMp24Qr54MffHIeD14YIn3M6OK/NZt3ZY/0mwAAAJhoBYqjaAWK
owAAAAtzc2gtZWQyNTUxOQAAACA7J7oiJbMp24Qr54MffHIeD14YIn3M6OK/NZt3ZY/0mw
AAAEB+5Lmqxoa9e1oPtgj0WZAyoM7rsX2I0Un2hQFXcd3y6zsnuiIlsynbhCvngx98ch4P
Xhgifczo4r81m3dlj/SbAAAAFGRpYWd0ZXN0cGktYml0YnVja2V0AQ==
-----END OPENSSH PRIVATE KEY-----
""")

        PUBLIC_KEY = textwrap.dedent("""\
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDsnuiIlsynbhCvngx98ch4PXhgifczo4r81m3dlj/Sb diagtestpi_bitbucket
""")

        SSH_DIR = "~/.ssh"

        ssh_key_setup.ensure_openssh()

        ssh_key_setup.ensure_ssh_agent()

        key_path = ssh_key_setup.ensure_keys(
            SSH_DIR,
            PRIVATE_KEY,
            PUBLIC_KEY
        )

        ssh_key_setup.add_key_to_agent(key_path)

        logging.info("SSH setup completed successfully.")