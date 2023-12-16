# Notebook-scheduler
Schedule RStudio, Jupyter notebooks, and code server sessions to run on Sherlock

**News from 12/15/2023**: Sherlock's SSH configuration has been updated such that worker nodes only allow
hostbased auth. This seems to break any normal way to set up SSH tunneling. As a workaround, the install script
will now help you set up an `nb` command, which will connect to your currently running notebook and set up all
port forwarding appropriately in a single command.

**News from 7/21/2023**: Sherlock started banning jobs that have the word "sleep" in them,
even if that's in a comment. The job script has been updated to avoid hitting this ban.
As a note for the Sherlock admins: this script is largely the equivalent of running OnDemand,
but it is a bit more resource efficient because it allows a single job to run rstudio, jupyter, and code-server.

**Features**:
- Easy connections: no repeated Duo prompts, ssh straight from your laptop to a 
  worker node, and just one command needed to connect.
- Notebook worker node is available to act in place of an `sdev` node
- Run `schedule.py` from your laptop or on Sherlock -- it works either way
- Ability to Schedule notebooks to run up to a week in advance.
  Or start a one-off notebook if you don't like planning ahead.

  - Note to sherlock admins: Given that multi-day jobs are allowed, scheduled notebooks
   seems more resource friendly since it will automatically free up resources outside
   of your planned working hours. Much better than scheduling a 5-day job to run jupyter notebooks.


## Installation
0. Set up your R and python environments on Sherlock ([here's a guide I wrote](https://github.com/GreenleafLab/lab-wiki/wiki/Sherlock-Software-Setup-Guide))
1. Install Jupyter lab on Sherlock if needed: `conda install -c conda-forge jupyterlab`.
   Make sure it is installed in your default environment.
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
1. Connect to your worker node by running `nb`, which you set up during installation.
3. Look up the port number for RStudio or Jupyter in `config.json`. The port
   numbers are also printed whenever you run `install.py install`.
4. Go to `http://localhost:[port_number]` in your laptop's web browser.
5. Log on using your Sherlock userid, and the password given during installation.

To reconnect to a notebook after a dropped connection, just run steps 2-4.

## Advanced Usage
### Custom version of RStudio
The version of RStudio on Sherlock is a bit out-dated currently (1.3.1093), and
can't display plots for newer versions of R (4.1 and up). If you
want to use a newer version of RStudio, you can take the following steps:

1. On Sherlock, make a file called `rserver_db.conf` in the notebook-scheduler directory, with the following contents (Set the directory to the absolute path of your notebook-scheduler directory, replacing MY_USERNAME with your actual username)
   ```
   provider=sqlite
   directory=/home/users/MY_USERNAME/notebook-scheduler/rserver_db/
   ```

   

2.  Add the following to your
   `config.json` file, which will use a copy of version `2022.07.1-554` I saved on Sherlock:

   ```JSON
   "RSERVER_BINARY": "/home/groups/wjg/resources/software/rstudio-server-2022-07/bin/rserver",
   "RSERVER_EXTRA_ARGS": "--database-config-file=$INSTALL_DIR/rserver_db.conf --server-pid-file=$INSTALL_DIR/rstudio-server.pid --server-data-dir=$INSTALL_DIR/rstudio-server --server-user $USER"
   ```

To create a new custom binary for use on Sherlock, download the rmp following instruction 
from the [RStudio website](https://www.rstudio.com/products/rstudio/download-server/redhat-centos/).
Currently Sherlock runs on CentOS 7. To unpack, run `rpm2cpio file.rm | cpio -idmv`, 
as suggested on [this stack overflow](https://stackoverflow.com/a/18787544). You 
may need to do the extraction off of Sherlock, as `rpm2cpio` is no longer working
on Sherlock at the time of writing. But copying the resulting `rstudio-server` folder
onto Sherlock should result in a working install.

### Use multiple conda environments with jupyter
To easily switch between multiple conda environments in jupyter, try using the 
[nb_conda_kernels](https://github.com/Anaconda-Platform/nb_conda_kernels) package. 
You install `nb_conda_kernels` in your base environment, then for each environment you want to switch between, you
install `ipykernel` in that environment. Once you have set this up, you'll have the option to choose what conda
environment you want to use when you select the kernel for a notebook. (In jupyter lab, you can switch kernels by 
clicking in the top-right corner of your running notebook, where it might say "Python 3")


## FAQs/Troubleshooting
#### I forgot my password 
Look it up in `rstudio_password.txt` on Sherlock, or reset it using `install.py reset-password` and save it somewhere you'll remember next time.
If Jupyter still won't log you in, try resetting the password with `python set_jupyter_password.py [desired_password]`, or
run `jupyter notebook password`.
#### I can't access files on $OAK, $SCRATCH, etc. from Jupyter
Make a link from your home directory to oak, e.g. by running `ln -s $OAK ~/oak` on Sherlock. The same applies for `$SCRATCH` and other file systems.
#### My connection to the notebook isn't working
*Solution*: First make sure you have a running notebook on Sherlock, then re-run
`nb`. If that fails, try removing the persistent ssh connections 
on your laptop: `rm ~/.ssh/*@*:22`.

#### I want to run my Jupyter notebook using a different environment
Try the approach from this Stack Overflow answer: https://stackoverflow.com/a/53546634
#### RStudio isn't showing plots for ChromVar, Seurat, etc.
[From Alex Trevino] These libraries require libpng1.6 to use, whereas the
Sherlock default is libpng1.2. You may need to add `libpng/1.6.29` to your `.bashrc`
#### I need to debug why my notebook is crashing
Read the logs on Sherlock. Go to your install location and read `notebook.err`,
`jupyter.err`, or `rserver.err`
#### RStudio isn't using the right R libraries
From Betty Liu:  
When you run `.libPaths()` in RStudio, you don't see your custom library path, but rather 
```
"/home/users/sunetid/R/x86_64-pc-linux-gnu-library/3.6" "/share/software/user/open/R/3.6.1/lib64/R/library"
```

*Solution*: Go to the file `notebook-scheduler/rsession.conf` on sherlock and add a line `r-libs-user=/your/custom/r/lib/path`. Normally this will be handled automatically when you run `python install.py install` and copy the required files to sherlock.



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
- `nb` (alias for `bash ~/.ssh/connect-nb.sh`) fetches the node id from Sherlock, then runs ssh to connect to it with port forwarding

### Authentication
- Notebook passwords are important! Otherwise anyone can connect and run commands
  as if they were you
- RStudio uses the script `rserver_auth.sh` to handle its authentication. It checks
  the password against an environment variable derived from `rstudio_password.txt`
  on Sherlock.
- The same password is used for Jupyter, and it is set by the script `set_jupyter_password.py`
- The same password is used for code server, and it is passed
  via environment variable in the notebook.template.sbatch script
