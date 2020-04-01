import json
import os
import sys

from notebook.auth import passwd

password = passwd(sys.argv[1])
config_file = os.environ["HOME"] + "/.jupyter/jupyter_notebook_config.json"
if not os.path.isfile(config_file):
    open(config_file, "w").write("{}")

config = json.load(open(config_file))

if "NotebookApp" not in config:
    config["NotebookApp"] = {}
config["NotebookApp"]["password"] = password

json.dump(config, open(config_file, "w"), indent=4, sort_keys=True)