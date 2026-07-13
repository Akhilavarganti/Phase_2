import os
import subprocess
import logging

class ssh_key_setup:

    def run_cmd(cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True)
    

    def ensure_openssh():
        logging.info("Checking openssh-client...")
        result = ssh_key_setup.run_cmd("which ssh-agent")
        if result.returncode != 0:
            logging.info("Installing openssh-client...")
            subprocess.run("sudo apt update && sudo apt install -y openssh-client", shell=True, check=True)
        else:
            logging.info("openssh-client already installed")


    def ensure_ssh_agent():
        logging.info("Checking ssh-agent...")
        if "SSH_AUTH_SOCK" not in os.environ:
            logging.info("Starting ssh-agent...")
            agent = subprocess.run(["ssh-agent", "-s"], capture_output=True, text=True)
            
            for line in agent.stdout.splitlines():
                if "=" in line:
                    key, val = line.split(";", 1)[0].split("=")
                    os.environ[key] = val
        else:
            logging.info("ssh-agent already running")


    def ensure_keys(ssh_dir, private_key_content, public_key_content):
        ssh_dir = os.path.expanduser(ssh_dir)
        private_key_path = os.path.join(ssh_dir, "diagtestpi_bitbucket")
        public_key_path = private_key_path + ".pub"
        # Create directory if missing
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        # Private key
        if not os.path.exists(private_key_path):
            logging.info("Writing private key...")
            with open(private_key_path, "w") as f:
                f.write(private_key_content)
            os.chmod(private_key_path, 0o600)
        else:
            logging.info("Private key already exists")
        # Public key
        if not os.path.exists(public_key_path):
            logging.info("Writing public key...")
            with open(public_key_path, "w") as f:
                f.write(public_key_content)
            os.chmod(public_key_path, 0o644)
        else:
            logging.info("Public key already exists")
        
        return private_key_path


    def add_key_to_agent(private_key_path):
        logging.info("Adding key to ssh-agent...")
        result = subprocess.run(
            ["ssh-add", private_key_path],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logging.info("Key added successfully")
        else:
            logging.info(result.stderr.strip())


    def setup_ssh():
        PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
        b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
        QyNTUxOQAAACA7J7oiJbMp24Qr54MffHIeD14YIn3M6OK/NZt3ZY/0mwAAAJhoBYqjaAWK
        owAAAAtzc2gtZWQyNTUxOQAAACA7J7oiJbMp24Qr54MffHIeD14YIn3M6OK/NZt3ZY/0mw
        AAAEB+5Lmqxoa9e1oPtgj0WZAyoM7rsX2I0Un2hQFXcd3y6zsnuiIlsynbhCvngx98ch4P
        Xhgifczo4r81m3dlj/SbAAAAFGRpYWd0ZXN0cGktYml0YnVja2V0AQ==
        -----END OPENSSH PRIVATE KEY-----"""
        PUBLIC_KEY = """ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDsnuiIlsynbhCvngx98ch4PXhgifczo4r81m3dlj/Sb diagtestpi_bitbucket"""
        
        SSH_DIR = "~/.ssh"   # change to "~/.ssh" if needed
        
        ssh_key_setup.ensure_openssh()
        ssh_key_setup.ensure_ssh_agent()
        key_path = ssh_key_setup.ensure_keys(
            SSH_DIR,
            PRIVATE_KEY,
            PUBLIC_KEY
        )
        ssh_key_setup.add_key_to_agent(key_path)
        logging.info("SSH setup completed ✔")
