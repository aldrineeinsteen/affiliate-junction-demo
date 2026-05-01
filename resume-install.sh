#!/bin/bash
# Resume installation after fixing issues
# This script continues from Phase 3 (HCD installation)

set -e

# Source the main script's functions
source ./setup-infra.sh

echo_info "=== Resuming Installation from Phase 3 ==="
echo ""
echo "This will:"
echo "  1. Kill blocking port-forward processes"
echo "  2. Continue with HCD installation"
echo "  3. Configure Presto HCD catalog"
echo "  4. Initialize schemas"
echo "  5. Update Affiliate Junction"
echo ""
read -p "Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

# Kill port forwards that are blocking
echo_info "Killing blocking port-forward processes..."
pkill -f "kubectl port-forward" || true
sleep 2

# Continue from Phase 3
echo_info "Phase 3: Installing HCD as native daemon..."
install_hcd_daemon
init_hcd_schema

echo_info "Phase 4: Configuring Presto for HCD..."
configure_presto_hcd_catalog

echo_info "Phase 5: Initializing schemas..."
init_presto_schema

echo_info "Phase 6: Updating Affiliate Junction..."
update_affiliate_junction

echo_info "Verifying installation..."
verify_installation

echo_info "Displaying access information..."
show_access_info

echo_info "=== Installation Complete ==="

# Made with Bob
