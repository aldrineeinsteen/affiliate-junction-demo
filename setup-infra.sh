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

# Helper function to execute Presto queries via REST API
presto_query() {
    local query="$1"
    local response next_uri data_found=false
    local max_attempts=30
    
    # Get Presto pod name
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$PRESTO_POD" ]; then
        echo_error "Presto pod not found"
        return 1
    fi
    
    # Execute query
    response=$(kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- curl -k -u "ibmlhadmin:password" \
        -X POST https://localhost:8443/v1/statement \
        -H "Content-Type: text/plain" \
        -H "X-Presto-User: ibmlhadmin" \
        -d "$query" -s 2>/dev/null)
    
    # Poll for results (max 30 seconds)
    for i in $(seq 1 $max_attempts); do
        # Check if we have data
        if echo "$response" | jq -e '.data' >/dev/null 2>&1; then
            echo "$response" | jq -r '.data[][] // empty' 2>/dev/null
            data_found=true
            break
        fi
        
        # Check for errors
        if echo "$response" | jq -e '.error' >/dev/null 2>&1; then
            echo_error "Query failed: $(echo "$response" | jq -r '.error.message // .error')"
            return 1
        fi
        
        # Get nextUri for polling
        next_uri=$(echo "$response" | jq -r '.nextUri // empty' 2>/dev/null)
        
        # If no nextUri and no data, query might be complete (DDL statements)
        if [ -z "$next_uri" ]; then
            # Check if query state is finished
            state=$(echo "$response" | jq -r '.stats.state // empty' 2>/dev/null)
            if [ "$state" = "FINISHED" ]; then
                return 0
            fi
            break
        fi
        
        # Fetch next result
        sleep 1
        response=$(kubectl exec -n "${WXD_NAMESPACE}" "${PRESTO_POD}" -- curl -k -u "ibmlhadmin:password" \
            -H "X-Presto-User: ibmlhadmin" \
            "$next_uri" -s 2>/dev/null)
    done
    
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
    PRESTO_POD=$(kubectl get pods -n "${WXD_NAMESPACE}" -l app=ibm-lh-presto -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$PRESTO_POD" ]; then
        echo_error "Presto pod not found. Checking all pods:"
        kubectl get pods -n "${WXD_NAMESPACE}"
        exit 1
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
    
    # Wait a bit more for Presto to fully initialize
    sleep 10
    
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
    
    echo_info "Verifying Presto catalogs..."
    presto_query "SHOW CATALOGS"
    
    echo_info "Creating schemas in Presto..."
    
    # Read and execute each CREATE SCHEMA statement from presto_schema.sql
    # Extract CREATE SCHEMA statements and execute them one by one
    grep -i "CREATE SCHEMA" presto_schema.sql | while read -r line; do
        if [ -n "$line" ]; then
            echo_info "Executing: $line"
            presto_query "$line" || echo_warn "Schema may already exist, continuing..."
        fi
    done
    
    # Execute CREATE TABLE statements
    echo_info "Creating tables in Presto..."
    
    # Extract and execute CREATE TABLE statements
    awk '/CREATE TABLE/,/;/' presto_schema.sql | while IFS= read -r line; do
        # Accumulate lines until we hit a semicolon
        if [ -z "$table_stmt" ]; then
            table_stmt="$line"
        else
            table_stmt="$table_stmt $line"
        fi
        
        # When we hit a semicolon, execute the statement
        if echo "$line" | grep -q ";"; then
            if [ -n "$table_stmt" ]; then
                echo_info "Executing table creation..."
                presto_query "$table_stmt" || echo_warn "Table may already exist, continuing..."
                table_stmt=""
            fi
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
    
    echo_info "Available Presto catalogs:"
    presto_query "SHOW CATALOGS"
    
    # Verify required catalogs exist
    catalogs=$(presto_query "SHOW CATALOGS")
    if echo "$catalogs" | grep -q "iceberg_data" && echo "$catalogs" | grep -q "hcd"; then
        echo_info "✓ Required catalogs found: iceberg_data, hcd"
    else
        echo_warn "Some catalogs may be missing. Available catalogs:"
        echo "$catalogs"
    fi
    
    echo_info "Verification complete!"
}

show_access_info() {
    # Get VM IP address
    VM_IP=$(hostname -I | awk '{print $1}')
    
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
    echo "  VM IP Address:       ${VM_IP}"
    echo "  Hostname:            $(hostname)"
    echo ""
    echo "Component Access (On VM):"
    echo "  HCD (Cassandra):     localhost:9042"
    echo "  Presto:              https://localhost:8443"
    echo "  MinIO Console:       http://localhost:9001 (admin/password123)"
    echo "  MinIO API:           http://localhost:9000"
    echo "  Affiliate Junction:  http://localhost:10000"
    echo ""
    echo "Remote Access (From Your Laptop):"
    echo "  Port forwards are now active. Access services directly:"
    echo ""
    echo "  watsonx.data Console:  https://${VM_IP}:6443"
    echo "  MinIO Console:         http://${VM_IP}:9001 (admin/password123)"
    echo "  Affiliate Junction:    http://${VM_IP}:10000"
    echo ""
    echo "  Note: Ensure security group allows ports 6443, 9001, 10000"
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
