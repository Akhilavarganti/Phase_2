import os
import subprocess


def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def ensure_openssh():
    print("Checking openssh-client...")
    result = run_cmd("which ssh-agent")
    if result.returncode != 0:
        print("Installing openssh-client...")
        subprocess.run("sudo apt update && sudo apt install -y openssh-client", shell=True, check=True)
    else:
        print("openssh-client already installed")


def ensure_ssh_agent():
    print("Checking ssh-agent...")

    if "SSH_AUTH_SOCK" not in os.environ:
        print("Starting ssh-agent...")
        agent = subprocess.run(["ssh-agent", "-s"], capture_output=True, text=True)

        for line in agent.stdout.splitlines():
            if "=" in line:
                key, val = line.split(";", 1)[0].split("=")
                os.environ[key] = val
    else:
        print("ssh-agent already running")


def ensure_keys(ssh_dir, private_key_content, public_key_content):
    ssh_dir = os.path.expanduser(ssh_dir)
    private_key_path = os.path.join(ssh_dir, "id_rsa")
    public_key_path = private_key_path + ".pub"

    # Create directory if missing
    if not os.path.exists(ssh_dir):
        print(f"Creating {ssh_dir}...")
        os.makedirs(ssh_dir, mode=0o700)

    # Private key
    if not os.path.exists(private_key_path):
        print("Writing private key...")
        with open(private_key_path, "w") as f:
            f.write(private_key_content)
        os.chmod(private_key_path, 0o600)
    else:
        print("Private key already exists")

    # Public key
    if not os.path.exists(public_key_path):
        print("Writing public key...")
        with open(public_key_path, "w") as f:
            f.write(public_key_content)
        os.chmod(public_key_path, 0o644)
    else:
        print("Public key already exists")

    return private_key_path


def add_key_to_agent(private_key_path):
    print("Adding key to ssh-agent...")

    # Check if already added
    result = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True)

    if private_key_path in result.stdout:
        print("Key already added to agent")
    else:
        subprocess.run(["ssh-add", private_key_path], check=True)
        print("Key added successfully")


def setup_ssh():
    PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
YOUR_PRIVATE_KEY
-----END RSA PRIVATE KEY-----"""

    PUBLIC_KEY = """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... your-email"""

    SSH_DIR = "~/.ssh"   # change to "~/.ssh" if needed

    ensure_openssh()
    ensure_ssh_agent()
    key_path = ensure_keys(SSH_DIR, PRIVATE_KEY, PUBLIC_KEY)
    add_key_to_agent(key_path)

    print("SSH setup completed ✔")


if __name__ == "__main__":
    setup_ssh()