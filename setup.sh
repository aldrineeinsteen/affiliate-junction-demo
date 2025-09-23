

# Bootstrap infrastructure
sudo dnf install java-17-openjdk java-17-openjdk-devel



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
sudo cp generate_traffic.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable generate_traffic
sudo systemctl start generate_traffic
echo "systemctl done"

