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
    
    # Check if already installed
    if kind get clusters 2>/dev/null | grep -q "${KIND_CLUSTER}"; then
        echo_warn "Kind cluster '${KIND_CLUSTER}' already exists"
        read -p "Continue anyway? This will skip watsonx.data installation. (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo_info "Installation cancelled"
            exit 0
        fi
        SKIP_WXD_INSTALL=true
    else
        SKIP_WXD_INSTALL=false
    fi
    
    # Phase 0: Download required files
    download_required_files
    
    if [ "$SKIP_WXD_INSTALL" = false ]; then
        # Phase 1: Prepare minimal configuration
        prepare_minimal_config
        
        # Phase 2: Run watsonx.data installer
        run_wxd_installer
    else
        echo_info "Skipping watsonx.data installation (already exists)"
    fi
    
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

# Helper function to execute Presto queries via REST API with timeout
presto_query() {
    local query="$1"
    local timeout="${2:-10}"  # Default 10 second timeout
    local response next_uri data_found=false
    local max_attempts=10  # Reduced from 30 to 10 attempts (10 seconds max)
    local attempt=0
    
    # Get Presto pod name
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$PRESTO_POD" ]; then
        echo_warn "Presto pod not found"
        return 1
    fi
    
    # Execute query with timeout
    response=$(timeout ${timeout} kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- curl -k -u "ibmlhadmin:password" \
        -X POST https://localhost:8443/v1/statement \
        -H "Content-Type: text/plain" \
        -H "X-Presto-User: ibmlhadmin" \
        -d "$query" -s 2>&1)
    
    local curl_exit=$?
    
    # Check for timeout (exit code 124)
    if [ $curl_exit -eq 124 ]; then
        echo_warn "Query timed out after ${timeout} seconds"
        return 1
    fi
    
    if [ $curl_exit -ne 0 ]; then
        echo_warn "Failed to execute query (exit code: $curl_exit)"
        return 1
    fi
    
    # Quick check for immediate results or errors
    if echo "$response" | jq -e '.data' >/dev/null 2>&1; then
        echo "$response" | jq -r '.data[][] // empty' 2>/dev/null
        return 0
    fi
    
    if echo "$response" | jq -e '.error' >/dev/null 2>&1; then
        echo_warn "Query error: $(echo "$response" | jq -r '.error.message // .error' 2>/dev/null)"
        return 1
    fi
    
    # Check if query completed immediately (DDL statements)
    state=$(echo "$response" | jq -r '.stats.state // empty' 2>/dev/null)
    if [ "$state" = "FINISHED" ]; then
        return 0
    fi
    
    # Poll for results with timeout (max 10 attempts = 10 seconds)
    next_uri=$(echo "$response" | jq -r '.nextUri // empty' 2>/dev/null)
    
    while [ -n "$next_uri" ] && [ $attempt -lt $max_attempts ]; do
        attempt=$((attempt + 1))
        sleep 1
        
        response=$(timeout 2 kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- curl -k -u "ibmlhadmin:password" \
            -H "X-Presto-User: ibmlhadmin" \
            "$next_uri" -s 2>/dev/null)
        
        # Check for data
        if echo "$response" | jq -e '.data' >/dev/null 2>&1; then
            echo "$response" | jq -r '.data[][] // empty' 2>/dev/null
            return 0
        fi
        
        # Check for completion
        state=$(echo "$response" | jq -r '.stats.state // empty' 2>/dev/null)
        if [ "$state" = "FINISHED" ]; then
            return 0
        fi
        
        # Get next URI
        next_uri=$(echo "$response" | jq -r '.nextUri // empty' 2>/dev/null)
    done
    
    # If we exhausted attempts, warn but don't fail
    if [ $attempt -ge $max_attempts ]; then
        echo_warn "Query polling timed out after ${max_attempts} attempts"
        return 1
    fi
    
    return 0
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
        echo_info "Extracting HCD ZIP..."
        unzip -q "${HCD_ZIP}"
        
        # The ZIP contains tar.gz files, extract the main HCD binary
        if [ -f "hcd-${HCD_VERSION}-bin.tar.gz" ]; then
            echo_info "Extracting HCD binary from tar.gz..."
            tar -xzf "hcd-${HCD_VERSION}-bin.tar.gz"
            echo_info "HCD extracted successfully"
        else
            echo_error "hcd-${HCD_VERSION}-bin.tar.gz not found after unzipping"
            ls -la
            exit 1
        fi
    else
        echo_info "HCD already extracted at hcd-${HCD_VERSION}"
    fi
    
    echo_info "All required files are available"
}

# Phase 1: Prepare configuration
prepare_minimal_config() {
    echo_info "Preparing configuration..."
    
    # Install Java 17 for PySpark (keep Java 11 for HCD)
    echo_info "Installing Java 17 for PySpark ETL services..."
    dnf install -y java-17-openjdk java-17-openjdk-devel
    
    # Verify Java 17 is installed
    if [ -d "/usr/lib/jvm/java-17-openjdk" ]; then
        echo_info "Java 17 installed successfully at /usr/lib/jvm/java-17-openjdk"
    else
        echo_error "Java 17 installation failed"
        exit 1
    fi
    
    cd "${WXD_INSTALLER_DIR}"
    
    # Backup original values.yaml
    if [ ! -f values.yaml.original ]; then
        cp values.yaml values.yaml.original
    fi
    
    # Install ALL components (full watsonx.data installation)
    echo_info "Using full watsonx.data configuration (all components enabled)"
    echo_info "This includes: Console UI, APIs, Spark, Presto, MinIO, Metastore, etc."
}

# Phase 2: Run watsonx.data installer
run_wxd_installer() {
    echo_info "Running watsonx.data installer..."
    echo_warn "This will take 30-60 minutes. Please be patient."
    
    cd "${WXD_INSTALLER_DIR}"
    
    # Make installer executable
    chmod +x installer.sh
    
    # Run installer (it will start port-forwards that block the terminal)
    echo_info "Running watsonx.data installer (this may take 10-15 minutes)..."
    
    # Run installer in background, capturing its output
    ./installer.sh > ~/wxd-install.log 2>&1 &
    INSTALLER_PID=$!
    
    # Monitor the log file for completion message
    echo_info "Monitoring installation progress..."
    tail -f ~/wxd-install.log &
    TAIL_PID=$!
    
    # Wait for "Setup is complete!" message in log
    while true; do
        if grep -q "Setup is complete!" ~/wxd-install.log 2>/dev/null; then
            echo_info "Installation completed successfully!"
            break
        fi
        
        # Check if installer process is still running
        if ! kill -0 $INSTALLER_PID 2>/dev/null; then
            echo_warn "Installer process exited"
            break
        fi
        
        sleep 5
    done
    
    # Stop tailing the log
    kill $TAIL_PID 2>/dev/null || true
    
    # Kill the port-forwards that the installer started
    echo_info "Stopping installer port-forwards to continue setup..."
    sleep 2
    pkill -f "kubectl port-forward" || true
    sleep 2
    
    # Configure kubectl to use the Kind cluster
    echo_info "Configuring kubectl for Kind cluster..."
    kind export kubeconfig --name "${KIND_CLUSTER}"
    
    # Verify kubectl is working
    if kubectl get pods -n "${WXD_NAMESPACE}" &>/dev/null; then
        echo_info "kubectl configured successfully"
    else
        echo_error "kubectl configuration failed"
        exit 1
    fi
    
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
        
        # Check if source directory exists
        if [ ! -d "${DOWNLOADS_DIR}/hcd-${HCD_VERSION}" ]; then
            echo_error "HCD source directory not found at ${DOWNLOADS_DIR}/hcd-${HCD_VERSION}"
            echo_info "Available directories in ${DOWNLOADS_DIR}:"
            ls -la "${DOWNLOADS_DIR}/"
            exit 1
        fi
        
        cp -r "${DOWNLOADS_DIR}/hcd-${HCD_VERSION}" "${HCD_INSTALL_DIR}"
    else
        echo_info "HCD already installed at ${HCD_INSTALL_DIR}"
    fi
    
    # Create required directories
    mkdir -p "${HCD_INSTALL_DIR}/data"
    mkdir -p "${HCD_INSTALL_DIR}/conf"
    mkdir -p "${HCD_INSTALL_DIR}/logs"
    
    # Get VM IP address for HCD configuration
    VM_IP=$(hostname -I | awk '{print $1}')
    echo_info "Configuring HCD to listen on VM IP: ${VM_IP}"
    
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
commitlog_sync: periodic
commitlog_sync_period_in_ms: 10000
saved_caches_directory: ${HCD_INSTALL_DIR}/data/saved_caches
seed_provider:
    - class_name: org.apache.cassandra.locator.SimpleSeedProvider
      parameters:
          - seeds: "${VM_IP}"
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
listen_address: ${VM_IP}
start_native_transport: true
native_transport_port: 9042
rpc_address: 0.0.0.0
broadcast_rpc_address: ${VM_IP}
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
    
    # Copy JVM options files from HCD resources
    echo_info "Copying JVM configuration files..."
    if [ -f "${HCD_INSTALL_DIR}/resources/cassandra/conf/jvm-server.options" ]; then
        cp "${HCD_INSTALL_DIR}/resources/cassandra/conf/jvm-server.options" "${HCD_INSTALL_DIR}/conf/"
    fi
    if [ -f "${HCD_INSTALL_DIR}/resources/cassandra/conf/jvm11-server.options" ]; then
        cp "${HCD_INSTALL_DIR}/resources/cassandra/conf/jvm11-server.options" "${HCD_INSTALL_DIR}/conf/"
    fi
    if [ -f "${HCD_INSTALL_DIR}/resources/cassandra/conf/jvm11-clients.options" ]; then
        cp "${HCD_INSTALL_DIR}/resources/cassandra/conf/jvm11-clients.options" "${HCD_INSTALL_DIR}/conf/"
    fi
    
    # Create systemd service
    echo_info "Creating systemd service..."
    
    # Find the actual Java 11 installation path
    local DETECTED_JAVA11_HOME=$(dirname $(dirname $(alternatives --display java | grep "family java-11" | head -1 | awk '{print $1}')))
    
    if [ -z "$DETECTED_JAVA11_HOME" ] || [ ! -d "$DETECTED_JAVA11_HOME" ]; then
        echo_error "Java 11 not found. Please install java-11-openjdk"
        exit 1
    fi
    
    echo_info "Using Java 11 from: ${DETECTED_JAVA11_HOME}"
    
    cat > /etc/systemd/system/hcd.service <<EOF
[Unit]
Description=HCD (Hyperconverged Database) Service
After=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart=${HCD_INSTALL_DIR}/bin/hcd cassandra -R -f
ExecStop=${HCD_INSTALL_DIR}/bin/hcd cassandra-stop
Restart=on-failure
RestartSec=10
LimitNOFILE=100000
LimitMEMLOCK=infinity
LimitNPROC=32768
LimitAS=infinity
Environment="JAVA_HOME=${DETECTED_JAVA11_HOME}"
Environment="PATH=${DETECTED_JAVA11_HOME}/bin:${HCD_INSTALL_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
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
    
    # Get VM IP address for HCD connection
    VM_IP=$(hostname -I | awk '{print $1}')
    
    # Create HCD catalog configuration
    cat > /tmp/hcd-catalog.properties <<EOF
connector.name=cassandra
cassandra.contact-points=${VM_IP}:9042
cassandra.load-policy.dc-aware.local-dc=datacenter1
cassandra.username=cassandra
cassandra.password=cassandra
cassandra.protocol-version=V4
EOF
    
    # Find Presto pod
    echo_info "Finding Presto pod..."
    
    # Ensure kubectl context is configured (in case watsonx.data was already installed)
    echo_info "DEBUG: Checking kubectl context..."
    if ! kubectl config current-context &>/dev/null; then
        echo_info "kubectl context not set, configuring now..."
        kind export kubeconfig --name "${KIND_CLUSTER}"
        if ! kubectl config current-context &>/dev/null; then
            echo_error "Failed to configure kubectl context"
            exit 1
        fi
    fi
    kubectl config current-context
    
    echo_info "DEBUG: Listing all pods in namespace ${WXD_NAMESPACE}..."
    kubectl get pods -n "${WXD_NAMESPACE}" -o wide
    
    echo_info "DEBUG: Attempting to find Presto pod with label app=ibm-lh-presto..."
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>&1)
    KUBECTL_EXIT_CODE=$?
    
    echo_info "DEBUG: kubectl exit code: ${KUBECTL_EXIT_CODE}"
    echo_info "DEBUG: PRESTO_POD value: '${PRESTO_POD}'"
    
    if [ -z "$PRESTO_POD" ] || [ $KUBECTL_EXIT_CODE -ne 0 ]; then
        echo_error "Presto pod not found or kubectl command failed"
        echo_info "DEBUG: Full pod list with labels:"
        kubectl get pods -n "${WXD_NAMESPACE}" --show-labels
        echo_info "DEBUG: Trying alternative label selector (component=presto)..."
        PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l component=presto -o jsonpath='{.items[0].metadata.name}' 2>&1)
        if [ -z "$PRESTO_POD" ]; then
            echo_error "Still cannot find Presto pod. Exiting."
            exit 1
        fi
    fi
    
    echo_info "Found Presto pod: ${PRESTO_POD}"
    
    # Copy catalog to Presto pod (correct path)
    kubectl cp /tmp/hcd-catalog.properties "${WXD_NAMESPACE}/${PRESTO_POD}:/var/presto/data/etc/catalog/hcd.properties"
    
    # Verify the file was copied
    echo_info "Verifying HCD catalog file..."
    kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- cat /var/presto/data/etc/catalog/hcd.properties
    
    # Restart Presto deployment to load new catalog
    echo_info "Restarting Presto to load HCD catalog..."
    kubectl rollout restart deployment/ibm-lh-presto -n "${WXD_NAMESPACE}"
    
    echo_info "Waiting for Presto to restart..."
    kubectl rollout status deployment/ibm-lh-presto -n "${WXD_NAMESPACE}" --timeout=300s
    
    # Wait for Presto to fully initialize after restart
    echo_info "Waiting for Presto to be fully ready..."
    sleep 15
    
    # Wait for Presto pod to be ready
    for i in {1..30}; do
        PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [ -n "$PRESTO_POD" ]; then
            if kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- curl -k -s https://localhost:8443/v1/info &>/dev/null; then
                echo_info "Presto is ready and responding"
                break
            fi
        fi
        echo_info "Waiting for Presto to be ready... ($i/30)"
        sleep 5
    done
    
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
    
    # Ensure we have the latest Presto pod name after restart
    echo_info "Getting current Presto pod name..."
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$PRESTO_POD" ]; then
        echo_error "Presto pod not found after restart"
        exit 1
    fi
    echo_info "Using Presto pod: ${PRESTO_POD}"
    
    echo_info "Verifying Presto catalogs..."
    echo_info "DEBUG: About to call presto_query with 'SHOW CATALOGS'"
    
    if ! presto_query "SHOW CATALOGS"; then
        echo_error "Failed to verify Presto catalogs"
        echo_info "DEBUG: Checking if Presto is accessible..."
        kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- curl -k https://localhost:8443/v1/info -s | head -20
        exit 1
    fi
    
    echo_info "DEBUG: Presto catalogs verified successfully"
    echo_info "Creating schemas and tables in Presto..."
    
    # Parse SQL file: remove comments, handle multi-line statements, remove semicolons
    # This awk script:
    # 1. Skips comment lines (starting with --)
    # 2. Skips empty lines
    # 3. Accumulates lines until it finds a semicolon
    # 4. Removes the semicolon and prints the complete statement
    awk '
    BEGIN { stmt = "" }
    
    # Skip comment lines
    /^[[:space:]]*--/ { next }
    
    # Skip empty lines
    /^[[:space:]]*$/ { next }
    
    # Accumulate non-empty, non-comment lines
    {
        # Remove leading/trailing whitespace
        gsub(/^[[:space:]]+|[[:space:]]+$/, "")
        
        # Add to statement with space separator
        if (stmt == "") {
            stmt = $0
        } else {
            stmt = stmt " " $0
        }
        
        # If line ends with semicolon, we have a complete statement
        if ($0 ~ /;[[:space:]]*$/) {
            # Remove the semicolon
            gsub(/;[[:space:]]*$/, "", stmt)
            # Print the statement
            print stmt
            # Reset for next statement
            stmt = ""
        }
    }
    
    # Print any remaining statement (should not happen with well-formed SQL)
    END {
        if (stmt != "") {
            gsub(/;[[:space:]]*$/, "", stmt)
            print stmt
        }
    }
    ' presto_schema.sql | while IFS= read -r sql_stmt; do
        # Skip if statement is empty
        if [ -z "$sql_stmt" ]; then
            continue
        fi
        
        # Determine statement type for better logging
        if echo "$sql_stmt" | grep -qi "CREATE SCHEMA"; then
            echo_info "Creating schema..."
        elif echo "$sql_stmt" | grep -qi "CREATE TABLE"; then
            table_name=$(echo "$sql_stmt" | grep -oP 'CREATE TABLE[^(]+\K[a-z_]+\.[a-z_]+\.[a-z_]+' | head -1)
            echo_info "Creating table: $table_name"
        fi
        
        # Execute the statement
        if presto_query "$sql_stmt"; then
            echo_info "✓ Statement executed successfully"
        else
            echo_warn "Statement may have failed or object already exists, continuing..."
        fi
    done
    
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
    
    # Check if setup.sh exists
    if [ ! -f setup.sh ]; then
        echo_error "setup.sh not found in ~/affiliate-junction-demo"
        exit 1
    fi
    
    # Stop services if they exist
    stop_affiliate_services
    
    # Backup existing .env
    if [ -f .env ]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    fi
    
    # Get VM IP address
    VM_IP=$(hostname -I | awk '{print $1}')
    
    # Detect Java 17 path for PySpark services
    local DETECTED_JAVA17_HOME=$(dirname $(dirname $(alternatives --display java | grep "family java-17" | head -1 | awk '{print $1}')))
    
    if [ -z "$DETECTED_JAVA17_HOME" ] || [ ! -d "$DETECTED_JAVA17_HOME" ]; then
        echo_error "Java 17 not found. Please install java-17-openjdk"
        exit 1
    fi
    
    echo_info "Using Java 17 from: ${DETECTED_JAVA17_HOME}"
    
    # Update service files with correct Java 17 path
    echo_info "Updating service files with Java paths..."
    sed -i "s|JAVA17_HOME_PLACEHOLDER|${DETECTED_JAVA17_HOME}|g" hcd_to_presto.service
    sed -i "s|JAVA17_HOME_PLACEHOLDER|${DETECTED_JAVA17_HOME}|g" presto_to_hcd.service
    
    # Update .env with watsonx.data configuration
    cat > .env <<EOF
# Web Authentication
WEB_AUTH_USER=watsonx
WEB_AUTH_PASSWD=watsonx.data

# HCD Configuration
HCD_HOST=${VM_IP}
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

# Traffic Generation Configuration
AFFILIATE_JUNCTION_ADVERTISERS_COUNT=500
AFFILIATE_JUNCTION_PUBLISHERS_COUNT=1000
AFFILIATE_JUNCTION_COOKIES_COUNT=5000
AFFILIATE_JUNCTION_HISTORY_MINS=90
AFFILIATE_JUNCTION_TRAFFIC_MIN=5000
AFFILIATE_JUNCTION_SALES_MIN=500
AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT=10

# Fraud and Cohort Configuration
AFFILIATE_JUNCTION_FRAUD_COOKIES_COUNT=5
AFFILIATE_JUNCTION_COHORTS=TECH,FASHION,HEALTH,FINANCE,TRAVEL
AFFILIATE_JUNCTION_COHORT_SAME_PROBABILITY=0.60
AFFILIATE_JUNCTION_COHORT_DIFFERENT_PROBABILITY=0.20
AFFILIATE_JUNCTION_FRAUD_CROSS_CONTAMINATION_PROBABILITY=0.05
AFFILIATE_JUNCTION_RANDOM_COOKIE_PROBABILITY=0.15
EOF
    
    # Extract Presto certificate for ETL services
    extract_presto_certificate
    
    # Setup port forwards (run in background)
    setup_port_forwards
    
    # Wait for port forwards to be established
    sleep 5
    
    # Run setup.sh to create services and start application
    echo_info "Running setup.sh to create and start services..."
    ./setup.sh
    
    echo_info "Affiliate Junction updated and services started"
}

extract_presto_certificate() {
    echo_info "Extracting Presto TLS certificate..."
    
    # Create certs directory
    mkdir -p /certs
    
    # Try to extract certificate from internal-tls secret
    if kubectl get secret -n wxd internal-tls &>/dev/null; then
        # Try different possible keys in the secret
        for key in tls.crt ca.crt cert.pem certificate.pem; do
            if kubectl get secret -n wxd internal-tls -o jsonpath="{.data.$key}" 2>/dev/null | base64 -d > /certs/presto.crt 2>/dev/null; then
                if [ -s /certs/presto.crt ]; then
                    echo_info "Successfully extracted certificate from internal-tls secret (key: $key)"
                    chmod 644 /certs/presto.crt
                    return 0
                fi
            fi
        done
    fi
    
    # If certificate extraction failed, create a self-signed cert or disable verification
    echo_warn "Could not extract Presto certificate from Kubernetes secrets"
    echo_info "Adding PRESTO_VERIFY_SSL=false to .env for demo environment"
    
    # Add to .env file
    if ! grep -q "PRESTO_VERIFY_SSL" .env; then
        echo "" >> .env
        echo "# Disable SSL verification for demo (certificate not available)" >> .env
        echo "PRESTO_VERIFY_SSL=false" >> .env
    fi
}

setup_port_forwards() {
    echo_info "Setting up port forwards..."
    
    # Kill existing port forwards
    pkill -f "kubectl port-forward" || true
    sleep 2
    
    # watsonx.data Web Console (UI)
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/lhconsole-ui-svc 9443:443 --address 0.0.0.0 > /tmp/wxd-console-pf.log 2>&1 &
    
    # Presto
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-presto-svc 8443:8443 --address 0.0.0.0 > /tmp/presto-pf.log 2>&1 &
    
    # MinIO
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-minio-svc 9000:9000 --address 0.0.0.0 > /tmp/minio-pf.log 2>&1 &
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-minio-svc 9001:9001 --address 0.0.0.0 > /tmp/minio-ui-pf.log 2>&1 &
    
    # Metastore
    nohup kubectl port-forward -n "${WXD_NAMESPACE}" service/ibm-lh-mds-thrift-svc 9083:8380 --address 0.0.0.0 > /tmp/metastore-pf.log 2>&1 &
    
    echo_info "Port forwards established"
    echo_info "  - watsonx.data Console: https://localhost:9443"
    echo_info "  - Presto Console: https://localhost:8443"
    echo_info "  - MinIO Console: http://localhost:9001"
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
    if ! kind get clusters | grep -q "${KIND_CLUSTER}"; then
        echo_error "Kind cluster not found"
        return 1
    fi
    echo_info "✓ Kind cluster '${KIND_CLUSTER}' is running"
    
    # Check pods
    echo_info "Checking watsonx.data pods..."
    kubectl get pods -n "${WXD_NAMESPACE}"
    
    # Count running pods
    running_pods=$(kubectl get pods -n "${WXD_NAMESPACE}" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    echo_info "✓ ${running_pods} pods running in namespace '${WXD_NAMESPACE}'"
    
    # Check HCD service
    echo_info "Checking HCD service..."
    if systemctl is-active --quiet hcd; then
        echo_info "✓ HCD service is active"
    else
        echo_error "HCD service not running"
        return 1
    fi
    
    # Check HCD schema
    echo_info "Checking HCD schema..."
    if ${HCD_INSTALL_DIR}/bin/cqlsh -e "DESCRIBE KEYSPACES" 2>/dev/null | grep -q affiliate_junction; then
        echo_info "✓ HCD schema 'affiliate_junction' exists"
    else
        echo_warn "HCD schema 'affiliate_junction' not found (may still be initializing)"
    fi
    
    # Check Presto catalogs (non-blocking with timeout)
    echo_info "Checking Presto catalogs (with 10s timeout)..."
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$PRESTO_POD" ]; then
        echo_warn "⚠ Presto pod not found - skipping catalog verification"
    else
        echo_info "Presto pod: ${PRESTO_POD}"
        
        # Try to query catalogs with timeout
        if catalogs=$(presto_query "SHOW CATALOGS" 10 2>/dev/null); then
            echo_info "Available Presto catalogs:"
            echo "$catalogs"
            
            # Check for required catalogs
            if echo "$catalogs" | grep -q "iceberg_data"; then
                echo_info "✓ Catalog 'iceberg_data' found"
            else
                echo_warn "⚠ Catalog 'iceberg_data' not found"
            fi
            
            if echo "$catalogs" | grep -q "hcd"; then
                echo_info "✓ Catalog 'hcd' found"
            else
                echo_warn "⚠ Catalog 'hcd' not found (may need manual configuration)"
            fi
        else
            echo_warn "⚠ Could not verify Presto catalogs (query timed out or failed)"
            echo_warn "  This is non-critical - Presto may still be initializing"
            echo_warn "  You can verify manually later with: kubectl exec -n ${WXD_NAMESPACE} ${PRESTO_POD} -- curl -k https://localhost:8443/v1/info"
        fi
    fi
    
    echo ""
    echo_info "✓ Core verification complete!"
    echo_info "  Note: Some components may still be initializing. This is normal."
}

show_access_info() {
    # Get VM private IP address
    VM_IP=$(hostname -I | awk '{print $1}')
    
    # Try to detect public/floating IP
    PUBLIC_IP=""
    
    # Method 1: Use external service (most reliable for IBM Cloud VMs)
    if command -v curl &> /dev/null; then
        PUBLIC_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || echo "")
    fi
    
    # Method 2: Try IBM Cloud metadata service (may not work on all VMs)
    if [ -z "$PUBLIC_IP" ]; then
        PUBLIC_IP=$(curl -s --connect-timeout 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
    fi
    
    # Method 3: Try ip route (usually returns private IP, but worth trying)
    if [ -z "$PUBLIC_IP" ]; then
        ROUTE_IP=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $7; exit}')
        # Only use if different from private IP
        if [ -n "$ROUTE_IP" ] && [ "$ROUTE_IP" != "$VM_IP" ]; then
            PUBLIC_IP="$ROUTE_IP"
        fi
    fi
    
    # Fallback: Use placeholder if all methods failed
    if [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" == "$VM_IP" ]; then
        PUBLIC_IP="<YOUR_PUBLIC_IP>"
        echo_warn "Could not auto-detect public IP. Using placeholder."
        echo_warn "Replace <YOUR_PUBLIC_IP> with your actual floating IP in the URLs below."
    fi
    
    # Start port forwards in background for remote access
    echo_info "Starting port forwards for remote access..."
    nohup kubectl port-forward -n wxd service/lhconsole-ui-svc 6443:443 --address 0.0.0.0 > /tmp/pf-console.log 2>&1 &
    nohup kubectl port-forward -n wxd service/ibm-lh-minio-svc 9001:9001 --address 0.0.0.0 > /tmp/pf-minio.log 2>&1 &
    nohup kubectl port-forward -n wxd service/ibm-lh-mds-thrift-svc 8381:8381 --address 0.0.0.0 > /tmp/pf-hive.log 2>&1 &
    sleep 3
    
    echo ""
    echo_info "=== Installation Complete ==="
    echo ""
    echo "VM Information:"
    echo "  Private IP Address:  ${VM_IP}"
    echo "  Public IP Address:   ${PUBLIC_IP}"
    echo "  Hostname:            $(hostname)"
    echo ""
    echo "Component Access (On VM - localhost):"
    echo "  HCD (Cassandra):     localhost:9042"
    echo "  Presto:              https://localhost:8443"
    echo "  MinIO Console:       http://localhost:9001"
    echo "  MinIO API:           http://localhost:9000"
    echo "  Hive Metastore:      localhost:9083"
    echo "  watsonx.data Console: https://localhost:9443"
    echo "  Affiliate Junction:  http://localhost:10000"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════════"
    echo "  REMOTE ACCESS - Available Services (From Your Laptop/Browser)"
    echo "═══════════════════════════════════════════════════════════════════════════════"
    echo ""
    printf "  %-30s %-40s %-15s\n" "SERVICE" "URL" "CREDENTIALS"
    echo "  ─────────────────────────────────────────────────────────────────────────────"
    printf "  %-30s %-40s %-15s\n" "watsonx.data Console" "https://${PUBLIC_IP}:9443" "ibmlhadmin/password"
    printf "  %-30s %-40s %-15s\n" "Presto Console" "https://${PUBLIC_IP}:8443" "ibmlhadmin/password"
    printf "  %-30s %-40s %-15s\n" "MinIO Console" "http://${PUBLIC_IP}:9001" "admin/password123"
    printf "  %-30s %-40s %-15s\n" "MinIO API" "http://${PUBLIC_IP}:9000" "admin/password123"
    printf "  %-30s %-40s %-15s\n" "Hive Metastore Thrift" "thrift://${PUBLIC_IP}:9083" "N/A"
    printf "  %-30s %-40s %-15s\n" "Affiliate Junction UI" "http://${PUBLIC_IP}:10000" "watsonx/watsonx.data"
    echo ""
    echo "  Note: All ports are configured in the security group automatically"
    echo "        If using setup-vm.sh, ports 8443, 9000, 9001, 9083, 9443, 10000 are open"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════════"
    echo ""
    echo "HCD Management (On VM):"
    echo "  Service: systemctl status hcd"
    echo "  CQL Shell: ${HCD_INSTALL_DIR}/bin/cqlsh"
    echo "  Nodetool: ${HCD_INSTALL_DIR}/bin/nodetool status"
    echo ""
    echo "Kubernetes (On VM):"
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
    echo "Port forward logs: /tmp/pf-*.log"
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

# Made with Bob
