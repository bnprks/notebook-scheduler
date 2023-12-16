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

if sys.version_info < (3, 5):
    print("Error: Python version 3.5 or greater is required")
    sys.exit(1)

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
    if on_sherlock():
        print("Error: run install.py from your local computer, not on Sherlock")
        sys.exit(0)
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

def on_sherlock():
    return "SHERLOCK" in os.environ

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

    if "RSERVER_BINARY" not in config:
        config["RSERVER_BINARY"] = "rserver"
    if "RSERVER_EXTRA_ARGS" not in config:
        config["RSERVER_EXTRA_ARGS"] = ""

    # 2. Decide on port numbers
    if "JUPYTER_PORT" not in config:
        config["JUPYTER_PORT"] = random.randint(49152, 65535)
    if "R_PORT" not in config:
        config["R_PORT"] = random.randint(49152, 65535)
    if "CODE_SERVER_PORT" not in config:
        config["CODE_SERVER_PORT"] = random.randint(49152, 65535)
    assert len(set([config["JUPYTER_PORT"], config["R_PORT"], config["CODE_SERVER_PORT"]])) == 3

    # 3. Write out config (possibly with modifications made)
    json.dump(config , open("config.json", "w"), indent=4, sort_keys=True)
    
    username = config["SHERLOCK_USER"]
    install_dir = config["INSTALL_PATH"]
    rstudio_port = config["R_PORT"]
    jupyter_port = config["JUPYTER_PORT"]
    code_server_port = config["CODE_SERVER_PORT"]
    print("Your RStudio port number is:", rstudio_port)
    print("Your Jupyter port number is:", jupyter_port)
    print("Your Code server port number is:", code_server_port)

    # 4. Get user to set up SSH config
    if yes_or_no("Set up files for ssh proxying in your ~/.ssh folder now? "):
        ssh_config_entry = ssh_config.format(username=username)
        ssh_config_path = (Path.home() / ".ssh/config")
        if not ssh_config_path.exists() or \
            ssh_config_entry not in ssh_config_path.read_text():
            print("\nCopy the following text to the file ~/.ssh/config:\n")
            print(ssh_config_entry)
            input("\nPress enter once you have copied over the above text")

        print("Testing ssh connection...\n")
        if not ssh_works():
            print("\nError connecting via 'ssh sherlock', exiting now")
            sys.exit(1)

        print("Copying script to ~/.ssh/connect-nb.sh")
        (Path.home() / ".ssh/connect-nb.sh")\
            .write_text(connect_script.format(
                install_dir=install_dir, 
                jupyter_port=jupyter_port, 
                rstudio_port=rstudio_port,
                code_server_port=code_server_port,
            ))
        alias_text = "alias \"nb=bash $HOME/.ssh/connect-nb.sh\""
        
        profile = Path.home() / ".bash_profile"
        if (Path.home() / ".profile").exists() and not profile.exists():
            profile = (Path.home() / ".profile")
        elif "zsh" in os.environ["SHELL"]:
            profile = (Path.home() / ".zshrc")
        if not profile.exists() or alias_text not in profile.read_text():
            print("\nCopy the following text to the file ~/{}:\n".format(profile.name))
            print(alias_text)
            input("\nPress enter once you have copied over the above text")
    else:
        print("Skipping ssh config installation.")
        print("Testing ssh connection...\n")
        if not ssh_works():
            print("\nError connecting via 'ssh sherlock', exiting now")
            sys.exit(1)
        
    
    # 5. Copy files to sherlock 
    if yes_or_no("Copy required files to sherlock now? "):
        print("Making directory {} on sherlock and copying files...".format(install_dir))
        subprocess.run(["ssh", "sherlock", "mkdir", "-p", install_dir])
        for file in ["schedule.py", "install.py", "set_jupyter_password.py", 
                     "config.json", "notebook.template.sbatch", "rserver_auth.sh"]:
            print("Copying {} to Sherlock".format(file))
            cp_remote(file, install_dir + "/" + file)

        # Make sure rserver_auth.sh is executable
        subprocess.run(["ssh", "sherlock", "chmod", "u+x", install_dir + "/rserver_auth.sh"])

        # Make substitutions in rsession.template.conf before upload
        print("Fetching R_LIBS_USER from Sherlock...", end="")
        # Use bash -l to get R_LIBS_USER even if it's only set in bash_profile
        r_libs = get_sherlock_output(["bash", "-l", "-c", "'echo $R_LIBS_USER'"]).decode().strip()
        if r_libs:
           r_libs_line = "r-libs-user=" + r_libs
        else:
            r_libs_line = ""
        print("found R_LIBS_USER=\"{}\"".format(r_libs))
        rsession_conf = substitute_template(
            open("rsession.template.conf").read(),
            {"R_LIBS_USER": r_libs_line}
        )
        
        print("Writing rsession.conf to Sherlock")
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
    if type(file) is str:
        file = open(file)
    subprocess.run(
        ["ssh", "sherlock", "cat > '{}'".format(dest)],
        stdin=file,
    )

def cp_string_remote(string, dest):
    f = tempfile.TemporaryFile()
    f.write(string.encode())
    f.flush()
    f.seek(0)
    cp_remote(f, dest)
    

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
        "python3", install_dir + "/set_jupyter_password.py", password])
    print("Password reset.")
    print("Restart any notebooks running on Sherlock see the new password take effect")

def ssh_works():
    try:
        output = get_sherlock_output(["echo", "Hello World"])
        return output == b"Hello World\n"
    except:
        return False

def get_sherlock_output(args):
    f = tempfile.TemporaryFile()
    p = subprocess.run(["ssh", "sherlock"] + args, stdout=f, check=True)
    f.seek(0)
    return f.read()

    

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
"""

connect_script = """\
#!/bin/bash
NB=$(ssh sherlock 'cat {install_dir}/current-host')
if [ ! -z "$NB" ]; then
    ssh -t sherlock -L {rstudio_port}:$NB:{rstudio_port} -L {jupyter_port}:$NB:{jupyter_port} -L {code_server_port}:$NB:{code_server_port} ssh $NB
else
    echo "Error: No running notebook job detected on Sherlock"
fi
"""

if __name__ == "__main__":
    main()