#!/usr/bin/env python3

# install.py install -- set installation
# install.py password -- reset passwords for notebooks

import csv
import datetime
import json
import os
from pathlib import Path
import random
import string
import subprocess
import sys
import tempfile
import time

usage = """
Usage:
install.py --help
    Show this help.

install.py install 
    Set up a fresh installation on Sherlock.
    (Run the command on your local computer)

install.py reset-password
    Reset the password for notebook access
    (Run the command on your local computer)
"""

def main():
    install_dir = str(Path(__file__).parent)
    os.chdir(install_dir)

    if len(sys.argv) != 2 or "-h" in sys.argv or "--help" in sys.argv:
        print(usage)
        sys.exit(1)
    if sys.argv[1] not in ["install", "reset-password"]:
        print(usage)
        sys.exit(1)

    command = sys.argv[1]
    if command == "install":
        cmd_install()
    elif command == "reset-password":
        cmd_password()

def cmd_install():
    # 1. Get user input
    config_exists = os.path.isfile("config.json")
    if config_exists:
        config = json.load(open("config.json"))
    else:
        config = {}
    if "SHERLOCK_USER" not in config:
        config["SHERLOCK_USER"] = input("Sherlock username: ")

    if "INSTALL_PATH" not in config:
        install_dir = input(
            "Sherlock installation directory (default=notebook-scheduler): ") \
            or "notebook-scheduler"
        if install_dir.startswith("~/"):
            install_dir = install_dir.replace("~/", "")
        if install_dir.endswith("/"):
            install_dir = install_dir.rstrip("/")
        if not install_dir.startswith("/"):
            install_dir = "/home/users/" + config["SHERLOCK_USER"] + \
                "/" + install_dir
        config["INSTALL_PATH"] = install_dir
    
    if "PARTITION" not in config:
        config["PARTITION"] = input(
            "Sherlock slurm partitions (default=wjg,sfgf,biochem): ") \
                or "wjg,sfgf,biochem"

    # 2. Decide on port numbers
    if "JUPYTER_PORT" not in config:
        config["JUPYTER_PORT"] = random.randint(49152, 65535)
    if "R_PORT" not in config:
        config["R_PORT"] = random.randint(49152, 65535)
    assert config["JUPYTER_PORT"] != config["R_PORT"]

    # 3. Write out config (possibly with modifications made)
    json.dump(config , open("config.json", "w"), indent=4, sort_keys=True)
    
    username = config["SHERLOCK_USER"]
    install_dir = config["INSTALL_PATH"]
    rstudio_port = config["R_PORT"]
    jupyter_port = config["JUPYTER_PORT"]

    # 4. Get user to set up SSH config
    if yes_or_no("Is it okay to set up files for easy ssh proxying in your ~/.ssh folder? "):
        ssh_dir = (Path.home() / ".ssh")
        if not (ssh_dir / "id_sherlock").is_file():
            print("Generating ~/.ssh/id_sherlock ssh key...")
            subprocess.run([
                "ssh-keygen", 
                "-f", str(ssh_dir.absolute()) + "/id_sherlock", 
                "-N", ""])
            print("Adding ~/.ssh/id_sherlock.pub to Sherlock's ~/.ssh/authorized_keys")
            subprocess.run(
                ["ssh", "sherlock", "cat >> .ssh/authorized_keys"],
                stdin=open(ssh_dir / "id_sherlock.pub"))
            subprocess.run(["ssh", "sherlock", "chmod 600 .ssh/authorized_keys"])
        else:
            print("Using existing ~/.ssh/id_sherlock ssh key, skipping key setup...")
        
        print("\nCopy the following text to the file ~/.ssh/config:\n")
        
        print(ssh_config.format(
            username=username, 
            jupyter_port=jupyter_port, 
            rstudio_port=rstudio_port,
            home_dir=str(Path.home().absolute())))
        input("\nPress enter once you have copied over the above text")

        print("Copying script to ~/.ssh/fetch-current-notebook-host.sh")
        (Path.home() / ".ssh/fetch-current-notebook-host.sh")\
            .write_text(fetch_script.format(install_dir=install_dir))
        print("\nCopy the following text to the file ~/.bash_profile (or ~/.profile):\n")
        print("alias \"fetch-notebook-location=bash $HOME/.ssh/fetch-current-notebook-host.sh\"")
        input("\nPress enter once you have copied over the above text")
    else:
        print("Skipping utility script installation.")
    
    # 4. Copy files to sherlock 
    if yes_or_no("Copy required files to sherlock now? "):
        print("Making directory {} on sherlock and copying files".format(install_dir))
        subprocess.run(["ssh", "sherlock", "mkdir", "-p", install_dir])
        cp_remote("schedule.py", install_dir)
        cp_remote("install.py", install_dir)
        cp_remote("set_jupyter_password.py", install_dir)
        cp_remote("config.json", install_dir)
        cp_remote("notebook.template.sbatch", install_dir)
        cp_remote("rserver_auth.sh", install_dir)

        # Make substitutions in rsession.template.conf before upload
        r_libs = subprocess.run(
            ["ssh", "sherlock", "printenv", "R_LIBS_USER"], 
            capture_output=True
        ).stdout.decode().strip()
        rsession_conf = substitute_template(
            open("rsession.template.conf").read(),
            {"R_LIBS_USER": r_libs}
        )
        cp_string_remote(rsession_conf, install_dir + "/rsession.conf")
    else:
        print("Skipping file copying.")

    # 5. Set first password
    if yes_or_no("Set notebook passwords? "):
        print("Setting notebook access password")
        cmd_password()
    else:
        print("Skipping password setting.")

    # 6. Give instructions for setting up ssh + commands
    print("\nAll done!")



def substitute_template(text, substitutions_dict):
    for k, v in substitutions_dict.items():
        text = text.replace("<"+k+">", v)
    return text

def cp_remote(file, dest):
    subprocess.run(["scp", file, "sherlock:'{}'".format(dest)])

def cp_string_remote(string, dest):
    f = tempfile.NamedTemporaryFile()
    f.write(string.encode())
    f.flush()
    subprocess.run(["scp", f.name, "sherlock:'{}'".format(dest)])

def cmd_password(length = 12):
    chars = string.ascii_letters + string.digits
    password = ''.join(random.choice(chars) for i in range(length))
    install_dir = json.load(open("config.json"))["INSTALL_PATH"]
    print("New password is: ", password)
    print("Copying password to rstudio_password.txt on Sherlock...")
    cp_string_remote(password, install_dir + "/rstudio_password.txt")
    print("Setting jupyter notebook password on Sherlock...")
    subprocess.run([
        "ssh", "sherlock", 
        "python", install_dir + "/set_jupyter_password.py", password])

def yes_or_no(question):
    answer = input(question + "(y/n): ").lower().strip()
    print("")
    while answer not in ["y", "yes", "n", "no"]:
        print("Input yes or no")
        answer = input(question + "(y/n):").lower().strip()
        print("")
    if answer in ["yes", "y"]:
        return True
    else:
        return False

ssh_config = """\
Host sherlock
    User {username}
    HostName login.sherlock.stanford.edu
    ControlMaster auto
    ControlPersist yes
    ControlPath ~/.ssh/%l%r@%h:%p

Host nb
    User {username}
    ProxyCommand bash -c 'host=$(cat $HOME/.ssh/current-notebook-host); ssh sherlock -W $host:%p'
    IdentityFile {home_dir}/.ssh/id_sherlock
    ControlMaster auto
    ControlPersist yes
    ControlPath ~/.ssh/%l%r@%h:%p
    LocalForward localhost:{rstudio_port} localhost:{rstudio_port}
    LocalForward localhost:{jupyter_port} localhost:{jupyter_port}
"""

fetch_script = """\
#!/bin/bash
ssh sherlock 'cat {install_dir}/current-host' > $HOME/.ssh/current-notebook-host
"""

if __name__ == "__main__":
    main()