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
    def ensure_known_host():
        ssh_dir = os.path.expanduser("~/.ssh")
        known_hosts = os.path.join(ssh_dir, "known_hosts")
    
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
    
        if not os.path.exists(known_hosts):
            open(known_hosts, "a").close()
            os.chmod(known_hosts, 0o644)
    
        # Check whether bitbucket.org is already present
        result = subprocess.run(
            ["ssh-keygen", "-F", "bitbucket.org", "-f", known_hosts],
            capture_output=True,
            text=True
        )
    
        if result.returncode == 0:
            logging.info("bitbucket.org already exists in known_hosts.")
            return
    
        logging.info("Adding bitbucket.org to known_hosts...")
    
        result = subprocess.run(
            ["ssh-keyscan", "-H", "bitbucket.org"],
            capture_output=True,
            text=True
        )
    
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError(
                "Failed to retrieve Bitbucket host key:\n" + result.stderr
            )
    
        with open(known_hosts, "a") as f:
            f.write(result.stdout)
    
        logging.info("bitbucket.org added to known_hosts successfully.")
    
    @staticmethod
    def configure_git_identity():
    
        logging.info("Checking Git identity...")
    
        name_result = subprocess.run(
            ["git", "config", "--global", "user.name"],
            capture_output=True,
            text=True
        )
    
        email_result = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True
        )
    
        user_name = name_result.stdout.strip()
        user_email = email_result.stdout.strip()
    
        # Both are already configured
        if user_name and user_email:
            logging.info(
                "Git identity already configured: %s <%s>",
                user_name,
                user_email
            )
            return
    
        # Ask only for missing details
        if not user_name:
            user_name = input("Enter Git user name: ").strip()
    
        if not user_email:
            user_email = input("Enter Git email: ").strip()
    
        if not user_name or not user_email:
            raise RuntimeError("Git user name and email cannot be empty.")
    
        subprocess.run(
            ["git", "config", "--global", "user.name", user_name],
            check=True
        )
    
        subprocess.run(
            ["git", "config", "--global", "user.email", user_email],
            check=True
        )
    
        logging.info(
            "Git identity configured: %s <%s>",
            user_name,
            user_email
        )

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
        
        ssh_key_setup.ensure_known_host()

        key_path = ssh_key_setup.ensure_keys(
            SSH_DIR,
            PRIVATE_KEY,
            PUBLIC_KEY
        )

        ssh_key_setup.add_key_to_agent(key_path)
        
        ssh_key_setup.configure_git_identity()

        logging.info("SSH setup completed successfully.")
