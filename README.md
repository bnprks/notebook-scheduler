# Notebook-scheduler
Schedule RStudio and Jupyter notebooks to run on Sherlock

**Features**:
- Schedule notebooks to run up to a week in advance, so they're ready when you want them (no waiting for allocations)
- Only 2 short commands needed to establish a first connection, and just run `ssh nb` to reconnect
- Notebook worker node is available to act in place of an `sdev` node


## Installation
0. Set up your R and python environments on Sherlock ([here's a guide I wrote](https://github.com/GreenleafLab/lab-wiki/wiki/Sherlock-Software-Setup-Guide))
1. Install Jupyter lab on Sherlock if needed: `conda install -c conda-forge jupyterlab`
2. Clone the notebook on your local laptop/desktop
```{bash}
git clone https://github.com/bnprks/notebook-scheduler.git
cd notebook-scheduler
```
3. Run install.py from your laptop/desktop and follow the instructions. (Read all of the instructions, they're important!)
```{bash}
python install.py install
```
## Basic Usage
### Scheduling Notebooks
(Do this either on Sherlock or your laptop)
1. Write your schedule for the coming week in `run_schedule.csv`.
    (Follow the format of the example in `example_schedule.csv`)
2. Run `python schedule.py reset run_schedule.csv`

Note: you can only schedule notebooks at most one week in advance, but if you save the file `run_schedule.csv` you can re-use it to reset your schedule each week.

### Running a One-off Notebook
(Do this either on Sherlock or your laptop)
1. Run `python schedule.py run-now [hours] [cpus] [mem_gb]`

### Connecting to Running Notebooks
(Do this on your laptop after you have completed the full installation)
1. Fetch the id of the current worker node for your notebook: `fetch-notebook-location` on your laptop.
2. Connect to your worker node: `ssh nb`
3. Look up the port number for RStudio or Jupyter in `config.json`
4. Go to `http://localhost:[port_number]` in your laptop's web browser.
5. Log on using your Sherlock userid, and the password given during installation.

To reconnect to a notebook after a dropped connection, just run steps 2-4.

## FAQs
#### I forgot my password 
Look it up in `rstudio_password.txt` on Sherlock, or reset it using `install.py reset-password` and save it somewhere you'll remember next time.
#### I can't access files on $OAK, $SCRATCH, etc. from Jupyter
Make a link from your home directory to oak, e.g. by running `ln -s $OAK ~/oak` on Sherlock. The same applies for `$SCRATCH` and other file systems.
#### `ssh nb` isn't working
Try removing all saved persistent connections from  your laptop: `rm ~/.ssh/*@*:22`

## Command usage
### install.py
```
Usage:
install.py --help
    Show this help.

install.py install 
    Set up a fresh installation on Sherlock.
    (Run the command on your local computer)

install.py reset-password
    Reset the password for notebook access
    (Run the command on your local computer)
```
### schedule.py
```
schedule.py --help
    Show this help.

schedule.py reset [schedule.csv]
    Reset the schedule on sherlock to match schedule.csv,
    then queue up the first job.
    (Run on local computer or on Sherlock)

schedule.py run-next
    Submit the next scheduled job to sbatch
    Modifies current_schedule.csv on Sherlock.
    (Run on local computer or on Sherlock)

schedule.py run-now [hours] [cpus] [mem_gb]
    Submit a notebook job immediately, outside of normal scheduling.
    (Run on local computer or on Sherlock)
    Defaults are:
        hours: 3h, cpus: 1, mem_gb: 8gb

schedule.py get
    Print the current schedule from sherlock.
    (Run on local computer or on Sherlock)
```

## How it works
### Recurring Jobs
- The current database of scheduled jobs is held in `current_schedule.csv` on Sherlock
- Every time a previously scheduled notebook job runs, it schedules the next job in `current_schedule.csv` using sbatch, and removes that job from `current_schedule.csv`
- `notebook.template.sbatch` is the template that will be run, but all of the variables `<VARIABLE>` are substitued by `schedule.py` before job submission
### Easy SSH connections
- Every time a notebook runs, it writes the worker node id to `current-host` on Sherlock
- `fetch-notebook-location` (alias for `bash ~/.ssh/fetch-current-notebook-host.sh`) fetches the node id from Sherlock and saves it to your laptop at `~/.ssh/current-notebook-host`
- With the recommended `~/.ssh/config` settings, `ssh nb`:
    - Looks up the worker node id saved in `~/.ssh/current-notebook-host`
    - Makes a first-hop connection to `ssh sherlock` (a login node) using normal password + Duo authentication
    - Makes a second-hop connection from the login node to the worker node using publickey authentication. (Requires local `~/.ssh/id_sherlock.pub` to be listed in Sherlock's `~/.ssh/authorized_keys`)
    - Saves both of these connections persistently in local files `~/.ssh/[local_name]@[remote_name]:22` to prevent repeated duo prompts
### Authentication
- Notebook passwords are important! Otherwise anyone can connect and run commands
  as if they were you
- RStudio uses the script `rserver_auth.sh` to handle its authentication. It checks
  the password against an environment variable derived from `rstudio_password.txt`
  on Sherlock.
- The same password is used for Jupyter, and it is set by the script `set_jupyter_password.py`