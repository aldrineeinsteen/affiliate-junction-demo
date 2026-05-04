#!/bin/bash

# Setup Port Forwards for watsonx.data Services
# This script creates systemd services for persistent port forwarding

set -e

echo "=========================================="
echo "Port Forward Setup for watsonx.data"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: This script must be run as root"
    exit 1
fi

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if wxd namespace exists
if ! kubectl get namespace wxd &> /dev/null; then
    echo "ERROR: wxd namespace not found. Please ensure watsonx.data is installed."
    exit 1
fi

echo "✓ Prerequisites check passed"
echo ""

# Define service files
SERVICE_FILES=(
    "presto-port-forward.service"
    "wxd-ui-port-forward.service"
    "minio-api-port-forward.service"
    "minio-console-port-forward.service"
    "metastore-port-forward.service"
)

# Copy service files to systemd directory
echo "Installing systemd service files..."
for service in "${SERVICE_FILES[@]}"; do
    if [ -f "$service" ]; then
        echo "  - Installing $service"
        cp "$service" /etc/systemd/system/
        chmod 644 "/etc/systemd/system/$service"
    else
        echo "  ✗ ERROR: $service not found in current directory"
        exit 1
    fi
done
echo "✓ Service files installed"
echo ""

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload
echo "✓ Systemd reloaded"
echo ""

# Stop any existing manual port forwards
echo "Stopping existing manual port forwards..."
pkill -f "kubectl port-forward" || true
sleep 2
echo "✓ Manual port forwards stopped"
echo ""

# Enable services
echo "Enabling port forward services..."
for service in "${SERVICE_FILES[@]}"; do
    echo "  - Enabling $service"
    systemctl enable "$service"
done
echo "✓ Services enabled"
echo ""

# Start services
echo "Starting port forward services..."
for service in "${SERVICE_FILES[@]}"; do
    echo "  - Starting $service"
    systemctl start "$service"
done
echo "✓ Services started"
echo ""

# Wait for services to initialize
echo "Waiting for services to initialize..."
sleep 5
echo ""

# Check service status
echo "=========================================="
echo "Service Status"
echo "=========================================="
for service in "${SERVICE_FILES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo "✓ $service: RUNNING"
    else
        echo "✗ $service: FAILED"
    fi
done
echo ""

# Test connectivity
echo "=========================================="
echo "Testing Connectivity"
echo "=========================================="

# Test Presto
echo -n "Testing Presto (8443)... "
if curl -k -s --max-time 5 https://localhost:8443/v1/info > /dev/null 2>&1; then
    echo "✓ OK"
else
    echo "✗ FAILED"
fi

# Test watsonx.data UI
echo -n "Testing watsonx.data UI (9443)... "
if curl -k -s --max-time 5 https://localhost:9443 > /dev/null 2>&1; then
    echo "✓ OK"
else
    echo "✗ FAILED"
fi

# Test Minio API
echo -n "Testing Minio API (9000)... "
if curl -s --max-time 5 http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    echo "✓ OK"
else
    echo "✗ FAILED"
fi

# Test Minio Console
echo -n "Testing Minio Console (9001)... "
if curl -s --max-time 5 http://localhost:9001 > /dev/null 2>&1; then
    echo "✓ OK"
else
    echo "✗ FAILED"
fi

# Test Metastore
echo -n "Testing Metastore (9083)... "
if nc -z -w5 localhost 9083 > /dev/null 2>&1; then
    echo "✓ OK"
else
    echo "✗ FAILED"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Port forwards are now persistent and will:"
echo "  • Survive system reboots"
echo "  • Auto-restart on failure"
echo "  • Log to journalctl"
echo ""
echo "Useful commands:"
echo "  • Check status: systemctl status presto-port-forward"
echo "  • View logs: journalctl -u presto-port-forward -f"
echo "  • Restart all: systemctl restart presto-port-forward wxd-ui-port-forward minio-api-port-forward minio-console-port-forward metastore-port-forward"
echo "  • Stop all: systemctl stop presto-port-forward wxd-ui-port-forward minio-api-port-forward minio-console-port-forward metastore-port-forward"
echo ""

# Made with Bob
