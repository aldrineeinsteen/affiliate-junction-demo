#!/bin/bash

set -e

echo "=== Affiliate Junction Setup ==="

# Check if .env already exists (created by setup-infra.sh)
if [ ! -f .env ]; then
    echo "Creating .env from env-sample..."
    cp env-sample .env
else
    echo ".env already exists, skipping..."
fi

# Bootstrap python environment
echo "Setting up Python virtual environment..."

# Detect available Python version
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD=python3.11
elif command -v python3.9 &> /dev/null; then
    PYTHON_CMD=python3.9
elif command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    echo "ERROR: No Python 3 installation found!"
    echo "Please install Python 3.9 or higher:"
    echo "  sudo dnf install -y python3 python3-pip python3-devel"
    exit 1
fi

echo "Using Python: $PYTHON_CMD ($($PYTHON_CMD --version))"

# Create virtual environment if it doesn't exist
if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
else
    echo "Virtual environment already exists"
fi

# Activate and install dependencies
echo "Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Python setup complete"

# Enable backend services
echo "Configuring systemd services..."
sudo cp *.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn.service truncate_all_tables.service

# Start services in stages
echo "Starting services..."
sudo systemctl start uvicorn.service
sudo systemctl start generate_traffic
sudo systemctl start hcd_to_presto

echo "Waiting 60 seconds for initial data processing..."
sleep 60

# Start remaining services
sudo systemctl start presto_to_hcd
sudo systemctl start presto_insights
sudo systemctl start presto_cleanup

echo "Systemd services configured and started"

# Add virtual environment activation to .bashrc if not already present
if ! grep -q "source $(pwd)/.venv/bin/activate" ~/.bashrc; then
    echo "Adding virtual environment activation to .bashrc..."
    echo "source $(pwd)/.venv/bin/activate" >> ~/.bashrc
fi

echo ""
echo "=== Setup Complete ==="
echo "Services running:"
echo "  - uvicorn (Web UI on port 10000)"
echo "  - generate_traffic (Traffic generator)"
echo "  - hcd_to_presto (HCD to Presto ETL)"
echo "  - presto_to_hcd (Presto to HCD ETL)"
echo "  - presto_insights (Analytics)"
echo "  - presto_cleanup (Data cleanup)"
echo ""
echo "Check service status:"
echo "  systemctl status uvicorn generate_traffic hcd_to_presto"
echo ""

