#!/bin/bash
#SBATCH --job-name=notebook
#SBATCH --begin=<BEGIN>

#SBATCH --partition=<PARTITION>

#SBATCH --error=<INSTALL_PATH>/notebook.err
#SBATCH --output=<INSTALL_PATH>/notebook.out

#SBATCH --time=<HOURS>:10:00
#SBATCH --mem=<MEM_GB>G
#SBATCH --cpus-per-task=<CPUS>

INSTALL_DIR=<INSTALL_PATH>

# Only schedule next job if we're doing a scheduled submission
if [ "<BEGIN>" != "now" ]; then
	python3 $INSTALL_DIR/schedule.py run-next
fi

hostname > $INSTALL_DIR/current-host

R_PORT=<R_PORT>
JUPYTER_PORT=<JUPYTER_PORT>
CODE_SERVER_PORT=<CODE_SERVER_PORT>

module load gsl rstudio R/4.0.2 code-server

RSERVER_PATH="<RSERVER_BINARY>"
RSERVER_EXTRA_ARGS="<RSERVER_EXTRA_ARGS>"

cd $HOME

export RSTUDIO_PASSWORD=$(cat $INSTALL_DIR/rstudio_password.txt)
"$RSERVER_PATH" $RSERVER_EXTRA_ARGS \
	--www-port=$R_PORT \
	--auth-none 0 \
	--rsession-which-r `which R` \
	--auth-pam-helper-path "$INSTALL_DIR/rserver_auth.sh" \
  	--auth-encrypt-password 0 \
	--rsession-config-file $INSTALL_DIR/rsession.conf \
	2> $INSTALL_DIR/rserver.err &
R_PID=$!
jupyter lab \
	--no-browser \
	--ip=127.0.0.1 \
	--port=$JUPYTER_PORT \
	2> $INSTALL_DIR/jupyter.err &
JUPYTER_PID=$!

CODE_SERVER_DATAROOT="$HOME/.local/share/code-server"
CODE_SERVER_USER_DIR="$CODE_SERVER_DATAROOT/User"
export PASSWORD=$(cat $INSTALL_DIR/rstudio_password.txt) 
code-server \
    --auth="password" \
    --bind-addr="0.0.0.0:$CODE_SERVER_PORT" \
    --disable-telemetry \
    --disable-update-check \
    --ignore-last-opened \
    --extensions-dir="$CODE_SERVER_DATAROOT/extensions" \
    --user-data-dir="$CODE_SERVER_DATAROOT" \
    "$HOME" 2> $INSTALL_DIR/code-server.err &
CODE_SERVER_PID=$!


# The server is running in the background; kill it when the time is up so it can shut down gracefully
# This funny workaround is because Sherlock apparently decided to ban the word s-l-e-e-p in job scripts.
# Given that running rstudio and jupyter via OnDemand is allowed, seems like this should be allowed
SLEE="slee"
${SLEE}p <HOURS>h

wait
kill $R_PID 
kill $JUPYTER_PID
kill $CODE_SERVER_PID
rm $INSTALLL_DIR/current-host

