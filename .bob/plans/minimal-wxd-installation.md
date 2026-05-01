# Minimal watsonx.data Developer Edition Installation Plan

## Objective
Create a `setup-infra.sh` script that uses the existing watsonx.data Helm installer with minimal configuration for the Affiliate Junction demo on an 8-core/32GB VM, with HCD running as a native daemon and complete teardown capability.

## Current State Analysis

### Required Files
Both files should be in `~/downloads/`:
- `watsonx.data-developer-edition-installer.tar` (440KB)
- `HCD_1.2.5_EN.zip` (87.8MB)

If not present, download using:
```bash
curl -L "https://ibm.box.com/shared/static/0rokzqg8usghnxq5qsttzuhkb48izdxj" -o watsonx.data-developer-edition-installer.tar
curl -L "https://ibm.box.com/shared/static/3cn9cj7rh4ninxkfcjpj49j9j8l53l6x" -o HCD_1.2.5_EN.zip
```

### Existing Installer Components
After extracting `watsonx.data-developer-edition-installer.tar`:

**Files:**
- `installer.sh` - Main installation script
- `values.yaml` - Helm configuration (13KB)
- `values-secret.yaml` - Secrets configuration
- `Chart.yaml` - Helm chart metadata
- `templates/` - Kubernetes resource templates

**What installer.sh does:**
1. Installs Docker (required for Kind - Kubernetes in Docker)
2. Installs kubectl
3. Installs Helm
4. Installs Kind (Kubernetes in Docker)
5. Creates Kind cluster: `kind-wxd`
6. Deploys watsonx.data via Helm to `wxd` namespace
7. Sets up port forwarding

**Note:** Docker is still required because Kind (Kubernetes in Docker) runs the entire Kubernetes cluster inside Docker containers. This is different from running HCD in Docker - we're using Docker only for the Kind cluster infrastructure, while HCD runs as a native daemon outside of Docker/Kubernetes.

### What Affiliate Junction Demo Requires

Based on analysis of [`README.md`](../README.md), [`hcd_schema.cql`](../hcd_schema.cql), [`presto_schema.sql`](../presto_schema.sql):

**Required Components:**
1. ✅ **Presto** - SQL query engine (included in installer)
2. ✅ **MinIO** - S3 storage for Iceberg (included in installer)
3. ✅ **Hive Metastore** (MDS) - Metadata catalog (included in installer)
4. ✅ **PostgreSQL** - Backend database (included in installer)
5. ❌ **HCD (Cassandra)** - NOT included in installer, install as native daemon

**NOT Required:**
- ❌ Console UI (demo has custom UI on port 10000)
- ❌ Console APIs (lhconsoleApi, lhamsApi, lhingestionApi)
- ❌ Validator service
- ❌ Spark engine
- ❌ CPG (Control Plane Gateway)

## Installation Strategy: Helm + Native HCD Daemon

### Why Docker is Still Needed

**Docker is required for Kind (Kubernetes in Docker)**, which runs the entire Kubernetes cluster inside Docker containers. This is the infrastructure layer for watsonx.data components (Presto, MinIO, Metastore).

**HCD runs OUTSIDE of Docker/Kubernetes** as a native systemd daemon using `hcd -R`. This gives us:
- Better performance (no container overhead)
- Simpler networking (direct localhost access)
- Easier management (standard systemd service)

### Architecture
```
┌─────────────────────────────────────────────────────┐
│                VM (8 cores, 32GB RAM)                │
├─────────────────────────────────────────────────────┤
│  Docker (Infrastructure Layer)                       │
│  └─ Kind Cluster (Kubernetes in Docker)             │
│     ├─ Namespace: wxd                                │
│     ├─ Presto (ibm-lh-presto-svc:8443)             │
│     ├─ MinIO (ibm-lh-minio-svc:9000/9001)          │
│     ├─ Metastore (ibm-lh-mds-thrift-svc:9083)      │
│     └─ PostgreSQL (wxd-pg-postgres:5432)            │
├─────────────────────────────────────────────────────┤
│  Native HCD Daemon (OUTSIDE Docker/K8s)              │
│  └─ HCD 1.2.5 (localhost:9042)                      │
│     └─ Started with: hcd -R (systemd service)       │
├─────────────────────────────────────────────────────┤
│  Affiliate Junction Services (systemd)               │
│  ├─ generate_traffic.service                        │
│  ├─ hcd_to_presto.service                           │
│  ├─ presto_to_hcd.service                           │
│  ├─ presto_insights.service                         │
│  ├─ presto_cleanup.service                          │
│  └─ uvicorn.service (Web UI on port 10000)         │
└─────────────────────────────────────────────────────┘
```

**Key Point:** Docker is used ONLY for the Kind cluster (watsonx.data infrastructure). HCD is NOT in a Docker container - it runs as a native process managed by systemd.

## Implementation Plan

### Phase 0: Download Required Files

Check for and download missing files:
1. Check if `watsonx.data-developer-edition-installer.tar` exists
2. Check if `HCD_1.2.5_EN.zip` exists
3. Download missing files from Box
4. Verify file sizes (440KB and 87.8MB respectively)
5. Extract both archives

### Phase 1: Prepare Minimal values.yaml

Edit `values.yaml` to disable unnecessary components:

```yaml
deployment:
  replicas:
    lhingestionApi: 0        # ❌ Disable (was 1)
    lhconsoleApi: 0          # ❌ Disable (was 1)
    lhamsApi: 0              # ❌ Disable (was 1)
    minio: 1                 # ✅ Keep
    consoleUI: 0             # ❌ Disable (was 1)
    validator: 0             # ❌ Disable (was 1)
    mdsRest: 1               # ✅ Keep (Metastore REST)
    mdsThrift: 1             # ✅ Keep (Metastore Thrift)
    presto: 1                # ✅ Keep
    cpg: 0                   # ✅ Already disabled
```

### Phase 2: Run watsonx.data Installer

Execute the existing `installer.sh` which will:
1. Install Docker, kubectl, Helm, Kind
2. Create Kind cluster
3. Deploy minimal watsonx.data components
4. Wait for all pods to be ready (~30-60 minutes)

### Phase 3: Install HCD as Native Daemon

1. Extract HCD from `HCD_1.2.5_EN.zip`
2. Install to `/opt/hcd-1.2.5/`
3. Configure HCD (`cassandra.yaml`)
4. Create systemd service for HCD
5. Start HCD daemon with `hcd -R`
6. Wait for HCD to be ready

### Phase 4: Configure Presto for HCD

Add HCD catalog to Presto running in Kind cluster:
1. Create HCD catalog configuration
2. Apply to Presto pod
3. Restart Presto if needed

### Phase 5: Initialize Schemas

1. Run [`hcd_schema.cql`](../hcd_schema.cql) on HCD
2. Run [`presto_schema.sql`](../presto_schema.sql) on Presto

### Phase 6: Update Affiliate Junction

1. Update [`.env`](../env-sample) with Kind service endpoints
2. Setup port forwards for service access
3. Restart Affiliate Junction services
4. Verify connectivity

## Resource Allocation

### Minimal Configuration Resource Usage

| Component | RAM | CPU | Disk |
|-----------|-----|-----|------|
| **Kind Infrastructure** |
| Docker + Kind control plane | 3 GB | 1 core | 5 GB |
| **watsonx.data Pods** |
| Presto (1 replica) | 4-6 GB | 2 cores | 2 GB |
| MinIO (1 replica) | 1 GB | 0.5 core | 10 GB |
| Metastore REST (1 replica) | 1 GB | 0.5 core | 1 GB |
| Metastore Thrift (1 replica) | 1 GB | 0.5 core | 1 GB |
| PostgreSQL | 512 MB | 0.5 core | 2 GB |
| **Standalone Components** |
| HCD (Native Daemon) | 4 GB | 1 core | 5 GB |
| Affiliate Junction | 2 GB | 1 core | 2 GB |
| System overhead | 2 GB | 0.5 core | 5 GB |
| **TOTAL** | **~19 GB** | **~7.5 cores** | **~33 GB** |
| **Available** | **~13 GB** | **~0.5 core** | **Varies** |

✅ **Fits within 32 GB RAM and 8 cores**

## HCD Systemd Service Configuration

Create `/etc/systemd/system/hcd.service`:

```ini
[Unit]
Description=HCD (Hyperconverged Database) Service
After=network.target

[Service]
Type=forking
User=root
Group=root
ExecStart=/opt/hcd-1.2.5/bin/hcd -R
ExecStop=/opt/hcd-1.2.5/bin/nodetool stopdaemon
PIDFile=/opt/hcd-1.2.5/hcd.pid
Restart=on-failure
RestartSec=10
LimitNOFILE=100000
LimitMEMLOCK=infinity
LimitNPROC=32768
LimitAS=infinity

[Install]
WantedBy=multi-user.target
```

## Script Structure: setup-infra.sh

```bash
#!/bin/bash
# Minimal watsonx.data infrastructure setup for Affiliate Junction
# Usage: 
#   ./setup-infra.sh install    # Install all components
#   ./setup-infra.sh teardown   # Remove all components
#   ./setup-infra.sh status     # Show status of all components

set -e

# Configuration
DOWNLOADS_DIR="$HOME/downloads"
WXD_INSTALLER_TAR="watsonx.data-developer-edition-installer.tar"
WXD_INSTALLER_DIR="$DOWNLOADS_DIR/watsonx.data-developer-edition-installer"
HCD_ZIP="HCD_1.2.5_EN.zip"
HCD_VERSION="1.2.5"
HCD_INSTALL_DIR="/opt/hcd-${HCD_VERSION}"

# Download URLs
WXD_BOX_URL="https://ibm.box.com/shared/static/0rokzqg8usghnxq5qsttzuhkb48izdxj"
HCD_BOX_URL="https://ibm.box.com/shared/static/3cn9cj7rh4ninxkfcjpj49j9j8l53l6x"

# Component names
KIND_CLUSTER="kind-wxd"
WXD_NAMESPACE="wxd"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

main() {
    case "${1:-}" in
        install)
            install_all
            ;;
        teardown)
            teardown_all
            ;;
        status)
            show_status
            ;;
        *)
            show_usage
            ;;
    esac
}

install_all() {
    echo_info "=== Starting Minimal watsonx.data Installation ==="
    
    # Phase 0: Download required files
    download_required_files
    
    # Phase 1: Prepare minimal configuration
    prepare_minimal_config
    
    # Phase 2: Run watsonx.data installer
    run_wxd_installer
    
    # Phase 3: Install HCD as native daemon
    install_hcd_daemon
    init_hcd_schema
    
    # Phase 4: Configure Presto for HCD
    configure_presto_hcd_catalog
    
    # Phase 5: Initialize schemas
    init_presto_schema
    
    # Phase 6: Update Affiliate Junction
    update_affiliate_junction
    
    # Verification
    verify_installation
    show_access_info
    
    echo_info "=== Installation Complete ==="
}

teardown_all() {
    echo_info "=== Starting Complete Teardown ==="
    
    # Stop Affiliate Junction services
    stop_affiliate_services
    
    # Kill port forwards
    echo_info "Stopping port forwards..."
    pkill -f "kubectl port-forward" || true
    
    # Stop HCD service
    echo_info "Stopping HCD service..."
    systemctl stop hcd 2>/dev/null || true
    systemctl disable hcd 2>/dev/null || true
    rm -f /etc/systemd/system/hcd.service
    systemctl daemon-reload
    
    # Delete Kind cluster (this removes all watsonx.data components)
    echo_info "Deleting Kind cluster..."
    kind delete cluster --name "${KIND_CLUSTER}" 2>/dev/null || true
    
    # Remove HCD installation (with confirmation)
    echo ""
    read -p "Remove HCD installation at ${HCD_INSTALL_DIR}? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        echo_info "Removing HCD installation..."
        rm -rf "${HCD_INSTALL_DIR}" 2>/dev/null || true
        echo_info "HCD installation removed"
    else
        echo_warn "HCD installation preserved at ${HCD_INSTALL_DIR}"
    fi
    
    # Remove data directories (with confirmation)
    echo ""
    read -p "Remove all data directories in /opt/wxd? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        echo_info "Removing data directories..."
        rm -rf /opt/wxd 2>/dev/null || true
        echo_info "Data directories removed"
    else
        echo_warn "Data directories preserved at /opt/wxd"
    fi
    
    # Remove kube config (with confirmation)
    echo ""
    read -p "Remove kubectl configuration? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        echo_info "Removing kubectl config..."
        rm -rf ~/.kube 2>/dev/null || true
        echo_info "Kubectl config removed"
    else
        echo_warn "Kubectl config preserved"
    fi
    
    # Remove downloads (with confirmation)
    echo ""
    read -p "Remove downloaded files in ~/downloads? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        echo_info "Removing downloads..."
        rm -rf "${DOWNLOADS_DIR}/${HCD_ZIP}" 2>/dev/null || true
        rm -rf "${DOWNLOADS_DIR}/hcd-${HCD_VERSION}" 2>/dev/null || true
        rm -rf "${DOWNLOADS_DIR}/${WXD_INSTALLER_TAR}" 2>/dev/null || true
        rm -rf "${WXD_INSTALLER_DIR}" 2>/dev/null || true
        echo_info "Downloads removed"
    else
        echo_warn "Downloads preserved in ${DOWNLOADS_DIR}"
    fi
    
    echo_info "=== Teardown Complete ==="
}

show_status() {
    echo_info "=== watsonx.data Component Status ==="
    
    # Kind cluster
    echo ""
    echo_info "Kind Cluster:"
    kind get clusters 2>/dev/null || echo "No Kind clusters found"
    
    # Kubernetes pods
    echo ""
    echo_info "Kubernetes Pods (wxd namespace):"
    kubectl get pods -n "${WXD_NAMESPACE}" 2>/dev/null || echo "Cluster not accessible"
    
    # HCD service
    echo ""
    echo_info "HCD Service:"
    systemctl status hcd --no-pager 2>/dev/null || echo "HCD service not found"
    
    # HCD process
    echo ""
    echo_info "HCD Process:"
    ps aux | grep -E "[h]cd.*cassandra" || echo "HCD not running"
    
    # Resource usage
    echo ""
    echo_info "Resource Usage:"
    echo "Kind cluster:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" $(docker ps -q --filter "name=kind") 2>/dev/null || echo "No Kind containers"
    
    # Affiliate Junction services
    echo ""
    echo_info "Affiliate Junction Services:"
    systemctl status generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn --no-pager 2>/dev/null | grep -E "Active:|Loaded:" || echo "Services not found"
    
    # Port forwards
    echo ""
    echo_info "Active Port Forwards:"
    ps aux | grep "kubectl port-forward" | grep -v grep || echo "No port forwards active"
}

# Phase 0: Download required files
download_required_files() {
    echo_info "Checking for required files..."
    
    mkdir -p "${DOWNLOADS_DIR}"
    cd "${DOWNLOADS_DIR}"
    
    # Check and download watsonx.data installer
    if [ ! -f "${WXD_INSTALLER_TAR}" ]; then
        echo_info "Downloading watsonx.data installer..."
        curl -L "${WXD_BOX_URL}" -o "${WXD_INSTALLER_TAR}"
        
        # Verify download (should be ~440KB)
        FILE_SIZE=$(stat -f%z "${WXD_INSTALLER_TAR}" 2>/dev/null || stat -c%s "${WXD_INSTALLER_TAR}")
        if [ "$FILE_SIZE" -lt 100000 ]; then
            echo_error "Downloaded installer is too small ($FILE_SIZE bytes). Check Box URL."
            exit 1
        fi
        echo_info "Installer downloaded successfully ($(($FILE_SIZE / 1024))KB)"
    else
        echo_info "watsonx.data installer already present"
    fi
    
    # Extract installer if not already extracted
    if [ ! -d "${WXD_INSTALLER_DIR}" ]; then
        echo_info "Extracting watsonx.data installer..."
        tar -xf "${WXD_INSTALLER_TAR}"
        echo_info "Installer extracted"
    else
        echo_info "Installer already extracted"
    fi
    
    # Check and download HCD
    if [ ! -f "${HCD_ZIP}" ]; then
        echo_info "Downloading HCD ${HCD_VERSION}..."
        curl -L "${HCD_BOX_URL}" -o "${HCD_ZIP}"
        
        # Verify download (should be ~87MB)
        FILE_SIZE=$(stat -f%z "${HCD_ZIP}" 2>/dev/null || stat -c%s "${HCD_ZIP}")
        if [ "$FILE_SIZE" -lt 10000000 ]; then
            echo_error "Downloaded HCD is too small ($FILE_SIZE bytes). Check Box URL."
            exit 1
        fi
        echo_info "HCD downloaded successfully ($(($FILE_SIZE / 1024 / 1024))MB)"
    else
        echo_info "HCD already present"
    fi
    
    # Extract HCD if not already extracted
    if [ ! -d "hcd-${HCD_VERSION}" ]; then
        echo_info "Extracting HCD..."
        unzip -q "${HCD_ZIP}"
        echo_info "HCD extracted"
    else
        echo_info "HCD already extracted"
    fi
    
    echo_info "All required files are available"
}

# Phase 1: Prepare minimal configuration
prepare_minimal_config() {
    echo_info "Preparing minimal configuration..."
    
    cd "${WXD_INSTALLER_DIR}"
    
    # Backup original values.yaml
    if [ ! -f values.yaml.original ]; then
        cp values.yaml values.yaml.original
    fi
    
    # Use sed to modify values.yaml for minimal deployment
    echo_info "Modifying values.yaml for minimal deployment..."
    sed -i.bak \
        -e 's/lhingestionApi: 1/lhingestionApi: 0/' \
        -e 's/lhconsoleApi: 1/lhconsoleApi: 0/' \
        -e 's/lhamsApi: 1/lhamsApi: 0/' \
        -e 's/consoleUI: 1/consoleUI: 0/' \
        -e 's/validator: 1/validator: 0/' \
        values.yaml
    
    echo_info "Minimal configuration prepared"
    echo_info "Disabled components: lhingestionApi, lhconsoleApi, lhamsApi, consoleUI, validator"
}

# Phase 2: Run watsonx.data installer
run_wxd_installer() {
    echo_info "Running watsonx.data installer..."
    echo_warn "This will take 30-60 minutes. Please be patient."
    
    cd "${WXD_INSTALLER_DIR}"
    
    # Make installer executable
    chmod +x installer.sh
    
    # Run installer
    ./installer.sh 2>&1 | tee ~/wxd-install.log
    
    echo_info "watsonx.data installation complete"
}

# Phase 3: Install HCD as native daemon
install_hcd_daemon() {
    echo_info "Installing HCD as native daemon..."
    
    # Stop existing HCD service if running
    systemctl stop hcd 2>/dev/null || true
    
    # Copy HCD to installation directory
    if [ ! -d "${HCD_INSTALL_DIR}" ]; then
        echo_info "Copying HCD to ${HCD_INSTALL_DIR}..."
        cp -r "${DOWNLOADS_DIR}/hcd-${HCD_VERSION}" "${HCD_INSTALL_DIR}"
    else
        echo_info "HCD already installed at ${HCD_INSTALL_DIR}"
    fi
    
    # Create data directory
    mkdir -p "${HCD_INSTALL_DIR}/data"
    
    # Configure HCD
    echo_info "Configuring HCD..."
    cat > "${HCD_INSTALL_DIR}/conf/cassandra.yaml" <<EOF
cluster_name: 'wxd-cluster'
num_tokens: 256
hinted_handoff_enabled: true
max_hint_window_in_ms: 10800000
hinted_handoff_throttle_in_kb: 1024
max_hints_delivery_threads: 2
hints_directory: ${HCD_INSTALL_DIR}/data/hints
hints_flush_period_in_ms: 10000
max_hints_file_size_in_mb: 128
batchlog_replay_throttle_in_kb: 1024
authenticator: AllowAllAuthenticator
authorizer: AllowAllAuthorizer
role_manager: CassandraRoleManager
roles_validity_in_ms: 2000
permissions_validity_in_ms: 2000
credentials_validity_in_ms: 2000
partitioner: org.apache.cassandra.dht.Murmur3Partitioner
data_file_directories:
    - ${HCD_INSTALL_DIR}/data/data
commitlog_directory: ${HCD_INSTALL_DIR}/data/commitlog
saved_caches_directory: ${HCD_INSTALL_DIR}/data/saved_caches
seed_provider:
    - class_name: org.apache.cassandra.locator.SimpleSeedProvider
      parameters:
          - seeds: "127.0.0.1"
concurrent_reads: 32
concurrent_writes: 32
concurrent_counter_writes: 32
concurrent_materialized_view_writes: 32
memtable_allocation_type: heap_buffers
index_summary_capacity_in_mb:
index_summary_resize_interval_in_minutes: 60
trickle_fsync: false
trickle_fsync_interval_in_kb: 10240
storage_port: 7000
ssl_storage_port: 7001
listen_address: localhost
start_native_transport: true
native_transport_port: 9042
start_rpc: false
rpc_address: localhost
rpc_port: 9160
rpc_keepalive: true
rpc_server_type: sync
thrift_framed_transport_size_in_mb: 15
incremental_backups: false
snapshot_before_compaction: false
auto_snapshot: true
column_index_size_in_kb: 64
column_index_cache_size_in_kb: 2
compaction_throughput_mb_per_sec: 16
sstable_preemptive_open_interval_in_mb: 50
read_request_timeout_in_ms: 5000
range_request_timeout_in_ms: 10000
write_request_timeout_in_ms: 2000
counter_write_request_timeout_in_ms: 5000
cas_contention_timeout_in_ms: 1000
truncate_request_timeout_in_ms: 60000
request_timeout_in_ms: 10000
cross_node_timeout: false
endpoint_snitch: SimpleSnitch
dynamic_snitch_update_interval_in_ms: 100
dynamic_snitch_reset_interval_in_ms: 600000
dynamic_snitch_badness_threshold: 0.1
request_scheduler: org.apache.cassandra.scheduler.NoScheduler
server_encryption_options:
    internode_encryption: none
client_encryption_options:
    enabled: false
internode_compression: dc
inter_dc_tcp_nodelay: false
tracetype_query_ttl: 86400
tracetype_repair_ttl: 604800
enable_user_defined_functions: false
enable_scripted_user_defined_functions: false
windows_timer_interval: 1
transparent_data_encryption_options:
    enabled: false
    chunk_length_kb: 64
    cipher: AES/CBC/PKCS5Padding
    key_alias: testing:1
    key_provider:
      - class_name: org.apache.cassandra.security.JKSKeyProvider
        parameters:
          - keystore: conf/.keystore
            keystore_password: cassandra
            store_type: JCEKS
            key_password: cassandra
tombstone_warn_threshold: 1000
tombstone_failure_threshold: 100000
batch_size_warn_threshold_in_kb: 5
batch_size_fail_threshold_in_kb: 50
unlogged_batch_across_partitions_warn_threshold: 10
compaction_large_partition_warning_threshold_mb: 100
gc_warn_threshold_in_ms: 1000
EOF
    
    # Create systemd service
    echo_info "Creating systemd service..."
    cat > /etc/systemd/system/hcd.service <<EOF
[Unit]
Description=HCD (Hyperconverged Database) Service
After=network.target

[Service]
Type=forking
User=root
Group=root
ExecStart=${HCD_INSTALL_DIR}/bin/hcd -R
ExecStop=${HCD_INSTALL_DIR}/bin/nodetool stopdaemon
PIDFile=${HCD_INSTALL_DIR}/hcd.pid
Restart=on-failure
RestartSec=10
LimitNOFILE=100000
LimitMEMLOCK=infinity
LimitNPROC=32768
LimitAS=infinity
Environment="CASSANDRA_HOME=${HCD_INSTALL_DIR}"
Environment="CASSANDRA_CONF=${HCD_INSTALL_DIR}/conf"
WorkingDirectory=${HCD_INSTALL_DIR}

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and start HCD
    systemctl daemon-reload
    systemctl enable hcd
    systemctl start hcd
    
    echo_info "Waiting for HCD to be ready..."
    sleep 30
    
    # Wait for CQL to be available
    for i in {1..30}; do
        if ${HCD_INSTALL_DIR}/bin/cqlsh -e "DESCRIBE KEYSPACES" &>/dev/null; then
            echo_info "HCD is ready"
            return 0
        fi
        echo_info "Waiting for HCD... ($i/30)"
        sleep 10
    done
    
    echo_error "HCD failed to start"
    systemctl status hcd --no-pager
    exit 1
}

init_hcd_schema() {
    echo_info "Initializing HCD schema..."
    
    if [ ! -f ~/affiliate-junction-demo/hcd_schema.cql ]; then
        echo_error "HCD schema file not found at ~/affiliate-junction-demo/hcd_schema.cql"
        exit 1
    fi
    
    cd ~/affiliate-junction-demo
    ${HCD_INSTALL_DIR}/bin/cqlsh < hcd_schema.cql
    
    echo_info "HCD schema initialized"
}

# Phase 4: Configure Presto for HCD
configure_presto_hcd_catalog() {
    echo_info "Configuring Presto HCD catalog..."
    
    # Create HCD catalog configuration
    cat > /tmp/hcd-catalog.properties <<EOF
connector.name=cassandra
cassandra.contact-points=localhost
cassandra.load-policy.dc-aware.local-dc=datacenter1
cassandra.username=cassandra
cassandra.password=cassandra
EOF
    
    # Find Presto pod
    echo_info "Finding Presto pod..."
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$PRESTO_POD" ]; then
        echo_error "Presto pod not found. Checking all pods:"
        kubectl get pods -n "${WXD_NAMESPACE}"
        exit 1
    fi
    
    echo_info "Found Presto pod: ${PRESTO_POD}"
    
    # Copy catalog to Presto pod
    kubectl cp /tmp/hcd-catalog.properties "${WXD_NAMESPACE}/${PRESTO_POD}:/opt/presto/etc/catalog/hcd.properties"
    
    # Restart Presto pod to load new catalog
    echo_info "Restarting Presto to load HCD catalog..."
    kubectl delete pod -n "${WXD_NAMESPACE}" "${PRESTO_POD}"
    
    echo_info "Waiting for Presto to restart..."
    kubectl wait --for=condition=ready pod -l app=ibm-lh-presto -n "${WXD_NAMESPACE}" --timeout=300s
    
    echo_info "Presto HCD catalog configured"
}

# Phase 5: Initialize schemas
init_presto_schema() {
    echo_info "Initializing Presto schema..."
    
    if [ ! -f ~/affiliate-junction-demo/presto_schema.sql ]; then
        echo_error "Presto schema file not found at ~/affiliate-junction-demo/presto_schema.sql"
        exit 1
    fi
    
    cd ~/affiliate-junction-demo
    
    # Find Presto pod
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}')
    
    # Copy schema file to pod
    kubectl cp presto_schema.sql "${WXD_NAMESPACE}/${PRESTO_POD}:/tmp/presto_schema.sql"
    
    # Execute schema
    kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- presto-cli --catalog iceberg_data --schema default --file /tmp/presto_schema.sql
    
    echo_info "Presto schema initialized"
}

# Phase 6: Update Affiliate Junction
update_affiliate_junction() {
    echo_info "Updating Affiliate Junction configuration..."
    
    if [ ! -d ~/affiliate-junction-demo ]; then
        echo_error "Affiliate Junction directory not found at ~/affiliate-junction-demo"
        exit 1
    fi
    
    cd ~/affiliate-junction-demo
    
    # Stop services
    stop_affiliate_services
    
    # Backup existing .env
    if [ -f .env ]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    fi
    
    # Update .env
    cat > .env <<EOF
# HCD Configuration
HCD_HOST=localhost
HCD_PORT=9042
HCD_DATACENTER=datacenter1
HCD_KEYSPACE=affiliate_junction
HCD_USER=cassandra
HCD_PASSWD=cassandra

# Presto Configuration (via port-forward)
PRESTO_HOST=localhost
PRESTO_PORT=8443
PRESTO_USER=ibmlhadmin
PRESTO_PASSWD=password
PRESTO_CATALOG=iceberg_data
PRESTO_SCHEMA=affiliate_junction

# MinIO Configuration (via port-forward)
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password123
MINIO_BUCKET=iceberg-bucket
EOF
    
    # Setup port forwards (run in background)
    setup_port_forwards
    
    # Wait for port forwards to be established
    sleep 5
    
    # Restart services
    start_affiliate_services
    
    echo_info "Affiliate Junction updated"
}

setup_port_forwards() {
    echo_info "Setting up port forwards..."
    
    # Kill existing port forwards
    pkill -f "kubectl port-forward" || true
    sleep 2
    
    # Presto
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-presto-svc 8443:8443 --address 0.0.0.0 > /tmp/presto-pf.log 2>&1 &
    
    # MinIO
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-minio-svc 9000:9000 --address 0.0.0.0 > /tmp/minio-pf.log 2>&1 &
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-minio-svc 9001:9001 --address 0.0.0.0 > /tmp/minio-ui-pf.log 2>&1 &
    
    # Metastore
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-mds-thrift-svc 9083:8380 --address 0.0.0.0 > /tmp/metastore-pf.log 2>&1 &
    
    echo_info "Port forwards established"
}

stop_affiliate_services() {
    echo_info "Stopping Affiliate Junction services..."
    systemctl stop generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn 2>/dev/null || true
}

start_affiliate_services() {
    echo_info "Starting Affiliate Junction services..."
    systemctl start generate_traffic hcd_to_presto presto_to_hcd presto_insights presto_cleanup uvicorn
}

# Verification
verify_installation() {
    echo_info "Verifying installation..."
    
    # Check Kind cluster
    echo_info "Checking Kind cluster..."
    kind get clusters | grep "${KIND_CLUSTER}" || { echo_error "Kind cluster not found"; exit 1; }
    
    # Check pods
    echo_info "Checking watsonx.data pods..."
    kubectl get pods -n "${WXD_NAMESPACE}"
    
    # Check HCD service
    echo_info "Checking HCD service..."
    systemctl is-active hcd || { echo_error "HCD service not running"; exit 1; }
    
    # Check HCD
    echo_info "Checking HCD schema..."
    ${HCD_INSTALL_DIR}/bin/cqlsh -e "DESCRIBE KEYSPACES" | grep affiliate_junction || { echo_error "HCD schema not found"; exit 1; }
    
    # Check Presto catalogs
    echo_info "Checking Presto catalogs..."
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}')
    kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- presto-cli --execute "SHOW CATALOGS" | grep -E "iceberg_data|hcd" || { echo_error "Presto catalogs not configured"; exit 1; }
    
    echo_info "Verification complete!"
}

show_access_info() {
    echo ""
    echo_info "=== Installation Complete ==="
    echo ""
    echo "Component Access:"
    echo "  HCD (Cassandra):     localhost:9042"
    echo "  Presto:              https://localhost:8443"
    echo "  MinIO Console:       http://localhost:9001 (admin/password123)"
    echo "  MinIO API:           http://localhost:9000"
    echo "  Affiliate Junction:  http://localhost:10000"
    echo ""
    echo "HCD Management:"
    echo "  Service: systemctl status hcd"
    echo "  CQL Shell: ${HCD_INSTALL_DIR}/bin/cqlsh"
    echo "  Nodetool: ${HCD_INSTALL_DIR}/bin/nodetool status"
    echo ""
    echo "Kubernetes:"
    echo "  Cluster: ${KIND_CLUSTER}"
    echo "  Namespace: ${WXD_NAMESPACE}"
    echo "  Context: kind-${KIND_CLUSTER}"
    echo ""
    echo "Useful Commands:"
    echo "  kubectl get pods -n ${WXD_NAMESPACE}              # List pods"
    echo "  kubectl logs -n ${WXD_NAMESPACE} <pod-name>       # View logs"
    echo "  systemctl status hcd                              # HCD status"
    echo "  ${HCD_INSTALL_DIR}/bin/cqlsh                      # HCD shell"
    echo "  ./setup-infra.sh status                           # Check status"
    echo "  ./setup-infra.sh teardown                         # Remove all"
    echo ""
    echo "Installation log saved to: ~/wxd-install.log"
    echo ""
}

show_usage() {
    cat <<EOF
Usage: $0 {install|teardown|status}

Commands:
  install   - Install all watsonx.data components with minimal configuration
  teardown  - Remove all components and optionally data
  status    - Show status of all components

Examples:
  $0 install    # Fresh installation (~60-90 minutes)
  $0 status     # Check component status
  $0 teardown   # Complete removal

Notes:
  - Installation requires ~19GB RAM and 7-8 CPU cores
  - Required files will be downloaded automatically if not present:
    * watsonx.data-developer-edition-installer.tar (440KB)
    * HCD_1.2.5_EN.zip (87.8MB)
  - HCD runs as a native systemd service (not Docker)
  - Installer will configure Docker, Kind, Helm, kubectl
  - Port forwards are automatically set up for service access
  - Installation log saved to ~/wxd-install.log
EOF
}

# Run main function
main "$@"
```

## Testing & Verification

### 1. Component Health Checks
```bash
# Check Kind cluster
kind get clusters

# Check watsonx.data pods
kubectl get pods -n wxd

# Check HCD service
systemctl status hcd

# Check HCD with nodetool
/opt/hcd-1.2.5/bin/nodetool status

# Check HCD schema
/opt/hcd-1.2.5/bin/cqlsh -e "DESCRIBE KEYSPACES"

# Check Presto catalogs
kubectl exec -n wxd $(kubectl get pods -n wxd -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}') -- presto-cli --execute "SHOW CATALOGS"
```

### 2. Federated Query Test
```bash
# Access Presto via port-forward
kubectl port-forward -n wxd service/ibm-lh-presto-svc 8443:8443

# Run federated query
presto-cli --server https://localhost:8443 --catalog hcd --schema affiliate_junction --execute "SELECT COUNT(*) FROM services"
```

### 3. Affiliate Junction Connectivity
```bash
# Check services
systemctl status generate_traffic hcd_to_presto presto_to_hcd

# Check web UI
curl http://localhost:10000
```

## Teardown Modes

### 1. Complete Teardown
```bash
./setup-infra.sh teardown
# Answer "yes" to all prompts
```

This will:
- Stop Affiliate Junction services
- Stop and remove HCD systemd service
- Delete Kind cluster (removes all watsonx.data components)
- Optionally remove HCD installation
- Optionally remove data directories
- Optionally remove kubectl config
- Optionally remove downloaded files

### 2. Preserve Data Teardown
```bash
./setup-infra.sh teardown
# Answer "no" when asked about data directories
```

### 3. Manual Teardown
```bash
# Stop HCD
systemctl stop hcd
systemctl disable hcd
rm /etc/systemd/system/hcd.service
systemctl daemon-reload

# Delete Kind cluster
kind delete cluster --name kind-wxd

# Remove installations
rm -rf /opt/hcd-1.2.5
rm -rf /opt/wxd
rm -rf ~/.kube
```

## Success Criteria

1. ✅ Kind cluster running with watsonx.data pods
2. ✅ HCD running as systemd service
3. ✅ Presto has both `iceberg_data` and `hcd` catalogs
4. ✅ MinIO accessible with required buckets
5. ✅ Federated queries work (HCD + Iceberg)
6. ✅ Affiliate Junction services connect successfully
7. ✅ Total RAM usage < 28 GB
8. ✅ Port forwards active for service access
9. ✅ Teardown completely removes all components
10. ✅ All existing Affiliate Junction functionality preserved

## Timeline Estimate

- Download required files: 5-10 minutes (if not present)
- Prepare minimal configuration: 2 minutes
- Run watsonx.data installer: 30-60 minutes
- Install HCD daemon: 10 minutes
- Configure Presto HCD catalog: 5 minutes
- Initialize schemas: 5 minutes
- Update Affiliate Junction: 5 minutes
- Testing & verification: 5 minutes

**Total:** ~70-100 minutes

## Resource Comparison

| Configuration | RAM | CPU | HCD Type |
|---------------|-----|-----|----------|
| **Full Install** | 15-20 GB | 7-8 cores | N/A |
| **Minimal Install** | 12-15 GB | 6-7 cores | N/A |
| **Our Install** | ~19 GB | ~7.5 cores | Native Daemon |

## Advantages of Native HCD Daemon

1. **Lower overhead** - No Docker container layer
2. **Better performance** - Direct system access
3. **Easier management** - Standard systemd service
4. **Simpler networking** - Direct localhost access
5. **Official method** - Uses `hcd -R` as intended

## Next Steps

1. Review and approve this plan
2. Create `setup-infra.sh` script based on this plan
3. Test installation on VM
4. Document any issues or adjustments
5. Update main README with new setup instructions

## References

- [Affiliate Junction README](../README.md)
- [HCD Schema](../hcd_schema.cql)
- [Presto Schema](../presto_schema.sql)
- [Database Connections](../affiliate_common/database_connections.py)
- [Existing Setup Script](../setup.sh)
- watsonx.data Installer: `~/downloads/watsonx.data-developer-edition-installer/installer.sh`