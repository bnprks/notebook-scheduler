#!/usr/bin/env python3

# Usages:
# schedule.py set [schedule.csv] -- set the schedule on sherlock 
# schedule.py run [template.sbatch] [schedule.csv] -- run the next job on sherlock at scheduled time, 
#   or submit immediately if no schedule is given
# schedule.py get -- print the current schedule from sherlock

# install.py install -- set installation
# install.py password -- reset passwords

import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import sys
import subprocess
import time

import install

# Ideal workflow
# - ~once a week run command to reset the schedule on sherlock
# - occasionally, run immediately outside of the schedule
# 

schedule_fields = ["day", "time", "hours", "cpus", "mem_gb"]
defaults = {
    "hours": 3,
    "cpus": 1,
    "mem_gb": 8
}

usage = """
Usage:
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
        hours: {hours}h, cpus: {cpus}, mem_gb: {mem_gb}gb

schedule.py get
    Print the current schedule from sherlock.
    (Run on local computer or on Sherlock)
""".format(**defaults)



def main():
    command, args = parse_args(sys.argv)
    if command == "reset":
        cmd_reset(args)
    elif command == "run-next":
        cmd_run_next()
    elif command == "run-now":
        cmd_run_now(args)
    elif command == "get":
        cmd_get()

def cmd_reset(schedule):
    ## Parse schedule as a check, then copy to sherlock
    read_schedule(open(schedule).read())
    config = json.load(open("config.json"))
    install_dir = config["INSTALL_PATH"]

    print(f"Copying schedule to {install_dir}/current_schedule.csv on Sherlock")
    install.cp_remote(schedule, install_dir + "/current_schedule.csv")

    # Cancel any pending jobs
    print(f"Cancelling all pending notebook jobs on Sherlock")
    pending_jobs = pending_notebook_jobids()
    if len(pending_jobs) > 0:
        run_sherlock(["scancel"] + pending_jobs)

    print(f"Starting schedule on Sherlock")
    cmd_run_next()
    

def cmd_run_next():
    file_dir = str(Path(__file__).parent)
    os.chdir(file_dir)
    
    if not on_sherlock():
        config = json.load(open("config.json"))
        install_dir = config["INSTALL_PATH"]    
        print("Running schedule.py on Sherlock...")
        run_sherlock(
            ["python", install_dir+"/schedule.py", "run-next"],
            check=True)
        sys.exit(0)
    # Guaranteed to be running on sherlock here
    
    config = json.load(open("config.json"))
    
    ## 1. Parse schedule
    today = datetime.datetime.today()
    entries = read_schedule(open("current_schedule.csv").read())
    next, next_time, rest = next_scheduled(entries, today)
    ## 2. Fill in notebook template
    notebook_sbatch = install.substitute_template(
        open("notebook.template.sbatch").read(),
        {
            "INSTALL_PATH": config["INSTALL_PATH"],
            "R_PORT":str(config["R_PORT"]),
            "JUPYTER_PORT":str(config["JUPYTER_PORT"]),
            "PARTITION": str(config["PARTITION"]),
            "HOURS": str(next["hours"]),
            "MEM_GB": str(next["mem_gb"]),
            "CPUS": str(next["cpus"]),
            "BEGIN": next_time.strftime("%Y-%m-%dT%H:%M")
        }
    )
    open("notebook.sbatch", 'w').write(notebook_sbatch)
    ## 3. Run sbatch command
    print("Submitting notebook.sbatch")
    subprocess.run(["sbatch", "notebook.sbatch"])

    ## 4. Remove the submitted job from the schedule
    print("Updating current_schedule.csv")
    write_schedule(rest, "current_schedule.csv")


def cmd_get():
    file_dir = str(Path(__file__).parent)
    os.chdir(file_dir)
    
    ## Just copy schedule down from sherlock
    config = json.load(open("config.json"))
    install_dir = config["INSTALL_PATH"]
    print(f"Fetching schedule from {install_dir}/current_schedule.csv on Sherlock")
    schedule = run_sherlock(
        ["cat", install_dir + "/current_schedule.csv"],
        capture_output=True
    ).stdout.decode()
    
    entries = read_schedule(schedule)
    _, next_time, _ = next_scheduled(entries, datetime.datetime.today())
    print("Next job running at:", next_time.ctime())
    print(schedule)

def cmd_run_now(args): 
    file_dir = str(Path(__file__).parent)
    os.chdir(file_dir)
    config = json.load(open("config.json"))

    notebook_sbatch = install.substitute_template(
        open("notebook.template.sbatch").read(),
        {
            "INSTALL_PATH": config["INSTALL_PATH"],
            "R_PORT":str(config["R_PORT"]),
            "JUPYTER_PORT":str(config["JUPYTER_PORT"]),
            "PARTITION": str(config["PARTITION"]),
            "HOURS": str(args["hours"]),
            "MEM_GB": str(args["mem_gb"]),
            "CPUS": str(args["cpus"]),
            "BEGIN": "now"
        }
    )
    print("Writing to notebook.sbatch on Sherlock...")
    if on_sherlock():
        open("notebook.sbatch", 'w').write(notebook_sbatch)
    else:
        install.cp_string_remote(
            notebook_sbatch, 
            config["INSTALL_PATH"] + "/notebook.sbatch")
    ## 3. Run sbatch command
    print("Submitting notebook job to sbatch...")
    run_sherlock(["sbatch", config["INSTALL_PATH"] + "/notebook.sbatch"])

def next_scheduled(entries, today):
    next = None
    for entry in entries:
        if next is None or scheduled_time(entry, today) < next_time:
            next = entry
            next_time = scheduled_time(next, today)
    
    rest = sorted(
        [e for e in entries if e != next],
        key = lambda e: scheduled_time(e, today))
    return next, next_time, rest

def scheduled_time(entry, today):
    time = datetime.datetime(
        year = today.year,
        month = today.month,
        day = today.day,
        hour = entry["start"].tm_hour,
        minute = entry["start"].tm_min
    )

    current_weekday = today.weekday()
    days_delay = (entry["day"] - current_weekday) % 7
    if time < today and days_delay == 0:
        days_delay = 7
    
    return time + datetime.timedelta(days=days_delay)
    
    
class CsvDialect(csv.excel):
    skipinitialspace = True

def read_schedule(schedule_text):
    lines = schedule_text.splitlines()
    body = [l for l in lines if not l.startswith("#")]
    entries = []
    for entry in csv.DictReader(body, dialect=CsvDialect):
        day, start, hours, cpus, mem_gb = parse_schedule_entry(entry)
        entries.append({
            "day": day,
            "start": start,
            "hours": hours,
            "cpus": cpus,
            "mem_gb": mem_gb,
        })
    return entries

def parse_schedule_entry(entry):
    try:
        day = time.strptime(entry["day"], "%a").tm_wday
    except ValueError:
        raise ValueError(
            f"Day \"{entry['day']}\" not recognized. (Use Mon, Tue, etc.)")

    try:
        start = time.strptime(entry["start"], "%I%p")
    except ValueError:
        start = None
    if start is None:
        try:
            start = time.strptime(entry["start"], "%I:%M%p")
        except ValueError:
            raise ValueError(
                f"Start time \"{entry['start']}\" not recognized. "
                "(Use 12pm, 10am, 10:30am, etc.)")
    
    if entry["hours"] == "":
        hours = defaults["hours"]
    else:
        hours = parse_hours(entry["hours"])
    
    if entry["cpus"] == "":
        cpus = defaults["cpus"]
    else:
        cpus = parse_cpus(entry["cpus"])

    if entry["mem_gb"] == "":
        mem_gb = defaults["mem_gb"]
    else:
        mem_gb = parse_mem_gb(entry["mem_gb"])
        

    return day, start, hours, cpus, mem_gb

def parse_hours(hours):
    try:
        return int(hours.lower().rstrip("h"))
    except ValueError:
        raise ValueError(
            f"Hours \"{hours}\" not recognized. Use e.g. 4h")

def parse_cpus(cpus):
    try:
        return int(cpus)
    except ValueError:
        raise ValueError(
            f"Cpus \"{cpus}\" not recognized. Use e.g. 1")
        
def parse_mem_gb(mem_gb):
    try:
        return int(mem_gb.lower().rstrip("gb"))
    except ValueError:
        raise ValueError(
            f"Mem_gb \"{mem_gb}\" not recognized. Use e.g. 8gb")

def write_schedule(entries, path):
    f = open(path, "w")
    print(", ".join(schedule_fields), file=f)
    for e in entries:
        print(entry_to_str(e), file=f)

def entry_to_str(entry):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    start = time.strftime("%I:%M%p", entry["start"])
    return f"{days[entry['day']]}, {start}, {entry['hours']}h, "\
           f"{entry['cpus']}, {entry['mem_gb']}gb"

def parse_args(argv):
    if len(argv) < 2:
        print(usage)
        sys.exit(1)
    if "-h" in argv or "--help" in argv:
        print(usage)
        sys.exit(1)
    command = argv[1]
    args = None

    if command not in ["reset", "run-now", "run-next", "get"]:
        print(f"Error: command {command} not recognized")
        print(usage)
        sys.exit(1)

    if command == "reset":
        if not len(argv) == 3:
            print("Error: reset must have exactly one schedule given")
            print(usage)
            sys.exit(1)
        else:
            args = argv[2]

    if command == "run-now":
        args = {**defaults}
        if len(argv) >= 3:
            args["hours"] = parse_hours(argv[2])
        if len(argv) >= 4:
            args["cpus"] = parse_cpus(argv[3])
        if len(argv) == 5:
            args["mem_gb"] = parse_mem_gb(argv[4])
        if len(argv) > 5:
            print(f"Error: too many arguments given for run-now")
            print(usage)
            sys.exit(1)
    
    if command in ["run-next", "get"]:
        if len(argv) != 2:
            print(f"Error: {command} must have zero arguments given")
            print(usage)
            sys.exit(1)
    
    return command, args
        
def pending_notebook_jobids():
    command = [
        "squeue", 
        "--user", "$USER", 
        "--name", "notebook",
        "--noheader",
        "--format" ,"%i",
        "--states", "PD"]
    result = run_sherlock(command, capture_output=True).stdout.decode()
    return result.splitlines()


def on_sherlock():
    return "SHERLOCK" in os.environ

def run_sherlock(args, **kwargs):
    if not on_sherlock():
        args = ["ssh", "sherlock"] + args 
    return subprocess.run(args, **kwargs)

if __name__ == "__main__":
  main()