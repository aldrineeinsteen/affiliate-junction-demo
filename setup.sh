

# Bootstrap python environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt


# Enable backend services
echo "Configuring systemctl"
sudo cp generate_traffic.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable generate_traffic
sudo systemctl start generate_traffic
echo "systemctl done"

