# Deployment Guide - Affiliate Junction Demo

Complete guide for deploying the Affiliate Junction demo with watsonx.data Developer Edition and HCD on IBM Cloud.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Detailed Installation Steps](#detailed-installation-steps)
4. [Verification](#verification)
5. [Troubleshooting](#troubleshooting)
6. [Architecture Overview](#architecture-overview)

---

## Prerequisites

### Required Tools

- **IBM Cloud CLI** - [Installation Guide](https://cloud.ibm.com/docs/cli?topic=cli-getting-started)
- **jq** - JSON processor (`brew install jq` on macOS)
- **Git** - Version control
- **SSH client** - For VM access

### IBM Cloud Account Requirements

- Active IBM Cloud account with VPC access
- Sufficient quota for:
  - 1 VPC instance (bx2-8x32 profile: 8 vCPUs, 32GB RAM)
  - 1 Floating IP
  - 1 Security Group
  - 1 Subnet

### Minimum VM Specifications

- **CPU**: 8 vCPUs
- **RAM**: 32GB (minimum 16GB)
- **Disk**: 100GB
- **OS**: RHEL 9

---

## Quick Start

> **⚠️ IMPORTANT FOR WORKSHOPS**: Always specify your assigned IBM Cloud region using `--region <region-code>`.
>
> Common regions: `us-south`, `us-east`, `eu-de`, `eu-gb`, `jp-tok`, `au-syd`
>
> Example: `./setup-vm.sh --auto-install --region eu-de`

For experienced users who want to deploy quickly:

### Option 1: Fully Automated (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/aldrineeinsteen/affiliate-junction-demo.git
cd affiliate-junction-demo

# 2. Provision VM with auto-install (90-120 minutes total)
# Replace eu-de with your assigned region
./setup-vm.sh --auto-install --region eu-de

# 3. Monitor installation progress
# SSH into VM (use IP from previous step)
ssh -i ~/.ssh/affiliate-junction-demo-key root@<FLOATING_IP>

# Check cloud-init status
cloud-init status

# Monitor installation log
tail -f /root/install.log

# Configure kubectl to monitor watsonx.data pods (optional)
kind export kubeconfig --name kind-wxd
kubectl get pods -n wxd

# 4. Access web UI when complete
# Open browser: http://<FLOATING_IP>:10000
```

### Option 2: Manual Installation

```bash
# 1. Clone repository
git clone https://github.com/aldrineeinsteen/affiliate-junction-demo.git
cd affiliate-junction-demo

# 2. Provision VM on IBM Cloud
# Replace eu-de with your assigned region
./setup-vm.sh --region eu-de

# 3. SSH into VM (use IP from previous step)
ssh -i ~/.ssh/affiliate-junction-demo-key root@<FLOATING_IP>

# 4. Clone repository on VM
git clone https://github.com/aldrineeinsteen/affiliate-junction-demo.git
cd affiliate-junction-demo

# 5. Run automated installation (60-90 minutes)
./setup-infra.sh install

# 6. Access web UI
# Open browser: http://<FLOATING_IP>:10000
```

---

## Detailed Installation Steps

### Step 1: Provision IBM Cloud VM

The `setup-vm.sh` script automates VM provisioning on IBM Cloud VPC.

#### Option A: With Auto-Install (Recommended)

```bash
# Clone the repository
git clone https://github.com/aldrineeinsteen/affiliate-junction-demo.git
cd affiliate-junction-demo

# Run VM provisioning with auto-install
# Replace eu-de with your assigned region
./setup-vm.sh --auto-install --region eu-de
```

**What it does:**
- Creates VPC, subnet, and security group in specified region
- Provisions RHEL 9 VM (bx2-8x32 profile)
- Installs base packages via cloud-init:
  - Python 3.9
  - Java 11 (for HCD)
  - Java 17 (for PySpark)
  - Git, wget, curl, unzip, jq
- Assigns floating IP for external access
- Generates SSH key pair (`~/.ssh/affiliate-junction-demo-key`)
- **Automatically clones repository and starts installation**

**Monitoring auto-install:**
```bash
# SSH into VM (use the IP shown in setup-vm.sh output)
ssh -i ~/.ssh/affiliate-junction-demo-key root@<FLOATING_IP>

# Monitor installation progress
tail -f /root/install.log

# Check if auto-install started
cat /root/auto-install-started.txt

# Configure kubectl to monitor watsonx.data pods (optional)
kind export kubeconfig --name kind-wxd
kubectl get pods -n wxd -w
```

#### Option B: Manual Installation

```bash
# Clone the repository
git clone https://github.com/aldrineeinsteen/affiliate-junction-demo.git
cd affiliate-junction-demo

# Run VM provisioning script (without auto-install)
# Replace eu-de with your assigned region
./setup-vm.sh --region eu-de
```

**What it does:**
- Creates VPC, subnet, and security group
- Provisions RHEL 9 VM (bx2-8x32 profile)
- Installs base packages via cloud-init:
  - Python 3.9
  - Java 11 (for HCD)
  - Java 17 (for PySpark)
  - Git, wget, curl, unzip, jq
- Assigns floating IP for external access
- Generates SSH key pair

**Expected output:**
```
✓ VM created successfully
✓ Floating IP: 52.116.xxx.xxx
✓ SSH command: ssh -i ~/.ssh/affiliate-junction-key root@52.116.xxx.xxx
```

**Time required:** 5-10 minutes

---

### Step 2: Connect to VM

```bash
# Use the SSH command from previous step
ssh -i ~/.ssh/affiliate-junction-demo-key root@<FLOATING_IP>

# Verify cloud-init completed
cat /root/cloud-init-complete.txt

# If using auto-install, check installation progress
tail -f /root/install.log
```

---

### Step 3: Clone Repository on VM

```bash
# Clone repository
git clone https://github.com/aldrineeinsteen/affiliate-junction-demo.git
cd affiliate-junction-demo

# Verify files
ls -la
```

---

### Step 4: Run Automated Installation

The `setup-infra.sh` script performs the complete installation.

```bash
./setup-infra.sh
```

**Installation phases:**

#### Phase 0: Download watsonx.data Installer (5-10 min)
- Downloads watsonx.data Developer Edition installer (~2GB)
- Extracts to `/root/ibm-lh-dev/`

#### Phase 1: Prepare Configuration (2-3 min)
- Installs Java 17 for PySpark
- Prepares watsonx.data configuration

#### Phase 2: Install watsonx.data (30-45 min)
- Installs Kind (Kubernetes in Docker)
- Deploys watsonx.data via Helm
- Starts all components:
  - Presto query engine
  - MinIO object storage
  - Hive Metastore
  - Console UI
  - Spark engine
- Waits for all pods to be ready

#### Phase 3: Install HCD (5-10 min)
- Downloads HCD 1.2.5
- Configures Cassandra for demo workload
- Creates systemd service
- Starts HCD daemon

#### Phase 4: Configure Presto HCD Catalog (2-3 min)
- Adds HCD as Presto data source
- Restarts Presto to load catalog
- Verifies catalog availability

#### Phase 5: Initialize Schemas (2-3 min)
- Creates HCD keyspace and tables
- Creates Presto/Iceberg schema and tables
- Verifies schema creation

#### Phase 6: Deploy Affiliate Junction (5-10 min)
- Extracts Presto TLS certificate
- Configures environment variables
- Creates Python virtual environment
- Installs dependencies
- Creates systemd services:
  - `generate_traffic` - Synthetic data generation
  - `hcd_to_presto` - ETL: HCD → Iceberg
  - `presto_to_hcd` - ETL: Iceberg → HCD
  - `presto_insights` - Analytics processing
  - `presto_cleanup` - Data cleanup
  - `uvicorn` - Web UI server
- Starts all services

**Total time:** 60-90 minutes

**Progress monitoring:**
```bash
# In another terminal, monitor installation
tail -f ~/wxd-install.log

# Check Kubernetes pods
kubectl get pods -n wxd

# Check services
systemctl status generate_traffic hcd_to_presto presto_to_hcd uvicorn
```

---

## Verification

### 1. Check All Services

```bash
# Check service status
for service in hcd generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn; do
    echo "=== $service ==="
    systemctl is-active $service
done
```

**Expected output:** All services should show `active`

### 2. Verify Data Flow

```bash
# Check generate_traffic logs
journalctl -u generate_traffic -n 20 --no-pager

# Should show:
# - "Successfully inserted all data"
# - Impression and conversion counts

# Check ETL services
journalctl -u hcd_to_presto -n 20 --no-pager
journalctl -u presto_to_hcd -n 20 --no-pager

# Should show:
# - "Processing completed"
# - No Java errors
```

### 3. Access Web UI

```bash
# Get VM IP
hostname -I | awk '{print $1}'
```

Open browser: `http://<VM_IP>:10000`

**Expected:**
- Login page loads
- After login, see publisher and advertiser dropdowns populated
- Charts display data
- Query panel shows database operations

### 4. Verify Data in Tables

```bash
# Check HCD tables
cd ~/affiliate-junction-demo
source .venv/bin/activate
python3 << EOF
from affiliate_common import CassandraConnection
conn = CassandraConnection()
session = conn.connect()

# Check publishers
result = session.execute("SELECT COUNT(*) FROM affiliate_junction.publishers")
print(f"Publishers: {result.one()[0]}")

# Check advertisers  
result = session.execute("SELECT COUNT(*) FROM affiliate_junction.advertisers")
print(f"Advertisers: {result.one()[0]}")

conn.close()
EOF
```

**Expected output:**
```
Publishers: 50
Advertisers: 10
```

---

## Troubleshooting

### Issue: ETL Services Failing with Java Error

**Symptom:**
```
java.lang.UnsupportedClassVersionError: class file version 61.0
```

**Solution:**
```bash
# Verify Java 17 is installed
ls -la /usr/lib/jvm/ | grep java-17

# If missing, install it
dnf install -y java-17-openjdk java-17-openjdk-devel

# Restart services
systemctl restart hcd_to_presto presto_to_hcd
```

### Issue: HCD Connection Refused

**Symptom:**
```
ConnectionRefusedError: [Errno 111] Connection refused to 127.0.0.1:9042
```

**Solution:**
```bash
# Check HCD is running
systemctl status hcd

# Check HCD is listening on correct IP
netstat -tlnp | grep 9042

# Update .env with correct IP
cd ~/affiliate-junction-demo
VM_IP=$(hostname -I | awk '{print $1}')
sed -i "s/HCD_HOST=.*/HCD_HOST=${VM_IP}/" .env

# Restart services
systemctl restart uvicorn hcd_to_presto presto_to_hcd
```

### Issue: Presto Certificate Error

**Symptom:**
```
OSError: Could not find a suitable TLS CA certificate bundle, invalid path: /certs/presto.crt
```

**Solution:**
```bash
# Add SSL verification bypass
cd ~/affiliate-junction-demo
echo "PRESTO_VERIFY_SSL=false" >> .env

# Restart ETL services
systemctl restart hcd_to_presto presto_to_hcd
```

### Issue: Batch Size Too Large

**Symptom:**
```
Batch is of size 276kB, exceeding specified failure threshold 50kB
```

**Solution:**
This is already fixed in the latest code (batch size = 100). If you see this:
```bash
cd ~/affiliate-junction-demo
git pull
systemctl restart generate_traffic
```

### Issue: No Data in Publishers/Advertisers Tables

**Symptom:**
Web UI shows "No publishers available" and "No advertisers available"

**Root cause:** ETL services not running or failing

**Solution:**
```bash
# Check ETL service logs
journalctl -u presto_to_hcd -n 50 --no-pager

# Common fixes:
# 1. Restart ETL services
systemctl restart hcd_to_presto presto_to_hcd

# 2. Wait 2-3 minutes for data pipeline
sleep 180

# 3. Verify data flow
journalctl -u presto_to_hcd -n 20 --no-pager | grep "processed"
```

### Issue: kubectl Cannot Connect to Cluster

**Symptom:**
```
The connection to the server localhost:8080 was refused
```

**Solution:**
```bash
# Export the Kind cluster kubeconfig
kind export kubeconfig --name kind-wxd

# Verify kubectl is configured
kubectl config get-contexts

# Now you can check pods
kubectl get pods -n wxd
```

### Issue: Kubernetes Pods Not Ready

**Symptom:**
```
Waiting for pods to be ready... (attempt X/60)
```

**Solution:**
```bash
# First, configure kubectl (see above)
kind export kubeconfig --name kind-wxd

# Check pod status
kubectl get pods -n wxd

# Check pod logs for errors
kubectl logs -n wxd <pod-name>

# Common issues:
# - Insufficient memory: Increase VM RAM
# - Image pull errors: Check internet connectivity
# - Timeout: Wait longer (up to 45 minutes)
```

### Issue: HCD Service Fails to Start

**Symptom:**
```
systemctl status hcd shows "failed" or "activating (auto-restart)"
```

**Solution:**
```bash
# Check if Java 11 is being used
journalctl -u hcd -n 50 --no-pager | grep -i java

# Verify Java 11 is installed
ls -la /usr/lib/jvm/ | grep java-11

# If HCD service file is incorrect, update it
cat > /etc/systemd/system/hcd.service <<'EOF'
[Unit]
Description=HCD (Hyperconverged Database) Service
After=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart=/opt/hcd-1.2.5/bin/hcd cassandra -R -f
ExecStop=/opt/hcd-1.2.5/bin/hcd cassandra-stop
Restart=on-failure
RestartSec=10
LimitNOFILE=100000
LimitMEMLOCK=infinity
LimitNPROC=32768
LimitAS=infinity
Environment="JAVA_HOME=/usr/lib/jvm/java-11-openjdk"
Environment="PATH=/usr/lib/jvm/java-11-openjdk/bin:/opt/hcd-1.2.5/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
Environment="CASSANDRA_HOME=/opt/hcd-1.2.5"
Environment="CASSANDRA_CONF=/opt/hcd-1.2.5/conf"
WorkingDirectory=/opt/hcd-1.2.5

[Install]
WantedBy=multi-user.target
EOF

# Reload and restart
systemctl daemon-reload
systemctl restart hcd
systemctl status hcd
```

### Issue: Port Already in Use

**Symptom:**
```
Error: port 9042 already in use
```

**Solution:**
```bash
# Find process using port
lsof -i :9042

# Kill the process
kill -9 <PID>

# Restart service
systemctl restart hcd
```

---

## Architecture Overview

### Component Stack

```
┌─────────────────────────────────────────────────────────┐
│                     Web UI (Port 10000)                  │
│                    FastAPI + Jinja2                      │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                   Data Layer (Dual)                      │
├──────────────────────────┬──────────────────────────────┤
│   HCD (Cassandra)        │   Presto + Iceberg           │
│   Port: 9042             │   Port: 8443                 │
│   - Operational data     │   - Analytical data          │
│   - Real-time writes     │   - Historical queries       │
│   - 5-10 min TTL         │   - Federated queries        │
└──────────────────────────┴──────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    ETL Services                          │
├─────────────────────────────────────────────────────────┤
│  generate_traffic  │  Synthetic data generation         │
│  hcd_to_presto     │  HCD → Iceberg ETL                 │
│  presto_to_hcd     │  Iceberg → HCD aggregation         │
│  presto_insights   │  Analytics processing              │
│  presto_cleanup    │  Data lifecycle management         │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. generate_traffic
   ↓ Writes to HCD
   - impression_tracking
   - impressions_by_minute
   - conversion_tracking
   - conversions_by_minute

2. hcd_to_presto (ETL)
   ↓ Reads from HCD, writes to Iceberg
   - impressions (Iceberg table)
   - conversions (Iceberg table)

3. presto_to_hcd (ETL)
   ↓ Queries Iceberg, aggregates, writes to HCD
   - publishers (HCD table) ← Web UI reads
   - advertisers (HCD table) ← Web UI reads

4. Web UI
   ↓ Reads from HCD
   - Displays publishers and advertisers
   - Shows metrics and charts
```

### Service Dependencies

```
hcd.service
  └─ generate_traffic.service
       └─ hcd_to_presto.service
            └─ presto_to_hcd.service
                 └─ uvicorn.service
```

### Network Ports

| Port  | Service              | Protocol | Access       |
|-------|---------------------|----------|--------------|
| 8443  | Presto              | HTTPS    | Internal     |
| 9000  | MinIO API           | HTTP     | Internal     |
| 9001  | MinIO Console       | HTTP     | Internal     |
| 9042  | HCD (Cassandra)     | TCP      | Internal     |
| 9083  | Hive Metastore      | TCP      | Internal     |
| 10000 | Web UI              | HTTP     | External     |

---

## Additional Resources

- **Demo Script**: See [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- **Developer Guide**: See [DEVELOPER.md](DEVELOPER.md)
- **Credentials**: See [CREDENTIALS.md](CREDENTIALS.md)
- **GitHub Repository**: https://github.com/aldrineeinsteen/affiliate-junction-demo

---

## Support

For issues or questions:
1. Check [Troubleshooting](#troubleshooting) section
2. Review service logs: `journalctl -u <service-name> -n 100`
3. Check GitHub Issues: https://github.com/aldrineeinsteen/affiliate-junction-demo/issues

---

**Last Updated**: 2026-05-02
**Version**: 1.3