#!/bin/bash


# Bootstrap infrastructure
sudo perl -i -pe 'if($.==1 && !/ibm-lh-presto-svc/){s/$/ ibm-lh-presto-svc/}' /etc/hosts
sudo dnf -y install java-17-openjdk java-17-openjdk-devel



# Bootstrap python environment
echo "Setup Python"
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "python setup done"


cp env-sample .env

git config --global user.email "you@example.com"
git config --global user.name "Your Name"


# Enable backend services
echo "Configuring systemctl"
sudo cp *.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn.service truncate_all_tables.service
sudo systemctl start generate_traffic hcd_to_presto uvicorn.service
sleep 60 	# Wait for Presto DDL commands to complete
sudo systemctl start presto_to_hcd presto_insights presto_cleanup
echo "systemctl done"

# Add virtual environment activation to .bashrc if not already present
if ! grep -q "source $(pwd)/.venv/bin/activate" ~/.bashrc; then
    echo "source $(pwd)/.venv/bin/activate" >> ~/.bashrc
fi

# source ./venv/bin/activate
# uvicorn web.main:app --reload --host 0.0.0.0 --port 10000

