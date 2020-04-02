import hashlib
import json
from pathlib import Path
import random
import sys

# Adapted from https://github.com/jupyter/notebook/blob/806904c0f9701fcee9281d97b20f69f9d2350896/notebook/auth/security.py#L24
def passwd(passphrase):
    algorithm = "sha1"
    salt_len = 12
    h = hashlib.new(algorithm)
    salt = ('%0' + str(salt_len) + 'x') % random.getrandbits(4 * salt_len)
    h.update(passphrase.encode('utf-8') + salt.encode('ascii'))

    return ':'.join((algorithm, salt, h.hexdigest()))

password = passwd(sys.argv[1])

config_file = Path.home() / ".jupyter" / "jupyter_notebook_config.json"
config_file.parent.mkdir(exist_ok=True)

if not config_file.is_file():
    config_file.write_text("{}")

config = json.loads(config_file.read_text())

if "NotebookApp" not in config:
    config["NotebookApp"] = {}
config["NotebookApp"]["password"] = password

config_file.write_text(json.dumps(config, indent=4, sort_keys=True))