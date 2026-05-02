#!/bin/bash

set -e  # Exit on error

# Parse command-line arguments
TEARDOWN=false
FORCE=false
AUTO_INSTALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --auto-install)
            AUTO_INSTALL=true
            shift
            ;;
        --region)
            VM_REGION="$2"
            shift 2
            ;;
        --zone)
            VM_ZONE="$2"
            shift 2
            ;;
        --name)
            VM_NAME="$2"
            shift 2
            ;;
        --profile)
            VM_PROFILE="$2"
            shift 2
            ;;
        --resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        --image)
            VM_IMAGE="$2"
            shift 2
            ;;
        --teardown)
            TEARDOWN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --region REGION              IBM Cloud region (default: us-south)"
            echo "  --zone ZONE                  Availability zone (default: us-south-1)"
            echo "  --name NAME                  VM name (default: affiliate-junction-demo)"
            echo "  --profile PROFILE            VM profile (default: bx2-8x32)"
            echo "  --resource-group GROUP       Resource group (default: Default)"
            echo "  --image IMAGE                OS image (default: auto-detect)"
            echo "  --auto-install               Automatically run setup-infra.sh after VM creation"
            echo "  --teardown                   Delete all resources (VM, floating IP, security group, etc.)"
            echo "  --force                      Force recreate VM if it exists"
            echo "  --help, -h                   Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --region eu-de --zone eu-de-1"
            echo "  $0 --name my-vm --profile bx2-4x16"
            echo "  $0 --auto-install            # Fully automated deployment"
            echo "  $0 --force --region eu-de    # Recreate VM with new settings"
            echo "  $0 --teardown --region eu-de # Delete all resources"
            echo "  VM_REGION=eu-de $0"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Configuration (with defaults)
VM_NAME="${VM_NAME:-affiliate-junction-demo}"
VM_PROFILE="${VM_PROFILE:-bx2-8x32}"  # 8 vCPUs, 32GB RAM
VM_IMAGE="${VM_IMAGE:-}"  # Will be auto-detected if not specified
VM_REGION="${VM_REGION:-us-south}"
VM_ZONE="${VM_ZONE:-${VM_REGION}-1}"  # Default zone based on region
RESOURCE_GROUP="${RESOURCE_GROUP:-Default}"
SSH_KEY_NAME="${SSH_KEY_NAME:-${VM_NAME}-key}"
SSH_KEY_PATH="${HOME}/.ssh/${SSH_KEY_NAME}"
SECURITY_GROUP_NAME="${SECURITY_GROUP_NAME:-${VM_NAME}-sg}"
VPC_NAME="${VPC_NAME:-${VM_NAME}-vpc}"
SUBNET_NAME="${SUBNET_NAME:-${VM_NAME}-subnet}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Teardown function
teardown_resources() {
    echo_info "=========================================="
    echo_info "Tearing Down Resources"
    echo_info "=========================================="
    
    # Get instance ID
    INSTANCE_ID=$(ibmcloud is instances --output json 2>/dev/null | jq -r ".[] | select(.name==\"${VM_NAME}\") | .id" | head -n1)
    
    if [ -n "${INSTANCE_ID}" ] && [ "${INSTANCE_ID}" != "null" ]; then
        echo_info "Deleting VM instance: ${VM_NAME} (${INSTANCE_ID})"
        ibmcloud is instance-delete "${INSTANCE_ID}" -f
        echo_info "Waiting for instance deletion..."
        sleep 10
    else
        echo_warn "No VM instance found with name: ${VM_NAME}"
    fi
    
    # Delete floating IP
    FIP_NAME="${VM_NAME}-fip"
    if ibmcloud is floating-ips --output json 2>/dev/null | jq -e ".[] | select(.name==\"${FIP_NAME}\")" > /dev/null 2>&1; then
        echo_info "Deleting floating IP: ${FIP_NAME}"
        ibmcloud is floating-ip-release "${FIP_NAME}" -f
    fi
    
    # Delete security group
    SG_ID=$(ibmcloud is security-groups --output json 2>/dev/null | jq -r ".[] | select(.name==\"${SECURITY_GROUP_NAME}\") | .id" | head -n1)
    if [ -n "${SG_ID}" ] && [ "${SG_ID}" != "null" ]; then
        echo_info "Deleting security group: ${SECURITY_GROUP_NAME}"
        ibmcloud is security-group-delete "${SG_ID}" -f
    fi
    
    # Delete subnet
    SUBNET_ID=$(ibmcloud is subnets --output json 2>/dev/null | jq -r ".[] | select(.name==\"${SUBNET_NAME}\") | .id" | head -n1)
    if [ -n "${SUBNET_ID}" ] && [ "${SUBNET_ID}" != "null" ]; then
        echo_info "Deleting subnet: ${SUBNET_NAME}"
        ibmcloud is subnet-delete "${SUBNET_ID}" -f
    fi
    
    # Delete VPC
    VPC_ID=$(ibmcloud is vpcs --output json 2>/dev/null | jq -r ".[] | select(.name==\"${VPC_NAME}\") | .id" | head -n1)
    if [ -n "${VPC_ID}" ] && [ "${VPC_ID}" != "null" ]; then
        echo_info "Deleting VPC: ${VPC_NAME}"
        ibmcloud is vpc-delete "${VPC_ID}" -f
    fi
    
    # Delete SSH key
    SSH_KEY_ID=$(ibmcloud is keys --output json 2>/dev/null | jq -r ".[] | select(.name==\"${SSH_KEY_NAME}\") | .id" | head -n1)
    if [ -n "${SSH_KEY_ID}" ] && [ "${SSH_KEY_ID}" != "null" ]; then
        echo_info "Deleting SSH key from IBM Cloud: ${SSH_KEY_NAME}"
        ibmcloud is key-delete "${SSH_KEY_ID}" -f
    fi
    
    # Remove SSH config entry
    if grep -q "Host ${VM_NAME}" ~/.ssh/config 2>/dev/null; then
        echo_info "Removing SSH config entry"
        sed -i.bak "/^Host ${VM_NAME}$/,/^$/d" ~/.ssh/config
    fi
    
    # Remove connection info file
    CONNECTION_FILE="${HOME}/.ssh/${VM_NAME}-connection.txt"
    if [ -f "${CONNECTION_FILE}" ]; then
        echo_info "Removing connection info file"
        rm -f "${CONNECTION_FILE}"
    fi
    
    echo_info "=========================================="
    echo_info "Teardown Complete!"
    echo_info "=========================================="
    echo_info "Note: Local SSH key files were NOT deleted: ${SSH_KEY_PATH}"
    echo_info "To delete them manually: rm -f ${SSH_KEY_PATH}*"
    
    exit 0
}

# Check if ibmcloud CLI is installed
if ! command -v ibmcloud &> /dev/null; then
    echo_error "ibmcloud CLI is not installed. Please install it first:"
    echo "  curl -fsSL https://clis.cloud.ibm.com/install/linux | sh"
    exit 1
fi

# Handle teardown mode
if [ "$TEARDOWN" = true ]; then
    teardown_resources
fi

# Check if already logged in
CURRENT_ACCOUNT=$(ibmcloud account show 2>/dev/null | grep "Account:" | awk '{print $2}')
if [ -n "${CURRENT_ACCOUNT}" ]; then
    echo_info "Already logged in to IBM Cloud (Account: ${CURRENT_ACCOUNT})"
    
    # Check if we need to switch region
    CURRENT_REGION=$(ibmcloud target --output json 2>/dev/null | jq -r '.region.name // empty')
    if [ "${CURRENT_REGION}" != "${VM_REGION}" ]; then
        echo_info "Switching to region ${VM_REGION}..."
        ibmcloud target -r "${VM_REGION}"
    else
        echo_info "Already in region ${VM_REGION}"
    fi
else
    # Login with SSO
    echo_info "Logging in to IBM Cloud with SSO (region: ${VM_REGION})..."
    if ! ibmcloud login --sso -r "${VM_REGION}"; then
        echo_error "Failed to login to IBM Cloud"
        exit 1
    fi
fi

# Get available resource groups and let user select if needed
echo_info "Checking available resource groups..."
AVAILABLE_RGS=$(ibmcloud resource groups --output json 2>/dev/null || echo "[]")

if [ "$(echo "${AVAILABLE_RGS}" | jq '. | length')" -eq 0 ]; then
    echo_error "No resource groups available. Please check your account permissions."
    exit 1
fi

# Try to find the specified resource group
RG_ID=$(echo "${AVAILABLE_RGS}" | jq -r ".[] | select(.name==\"${RESOURCE_GROUP}\") | .id" | head -n1)

if [ -z "${RG_ID}" ] || [ "${RG_ID}" == "null" ]; then
    echo_warn "Resource group '${RESOURCE_GROUP}' not found. Available resource groups:"
    echo "${AVAILABLE_RGS}" | jq -r '.[].name'
    
    # Use the first available resource group
    RESOURCE_GROUP=$(echo "${AVAILABLE_RGS}" | jq -r '.[0].name')
    RG_ID=$(echo "${AVAILABLE_RGS}" | jq -r '.[0].id')
    echo_info "Using resource group: ${RESOURCE_GROUP}"
fi

# Target the VPC infrastructure service with resource group
echo_info "Targeting VPC infrastructure service..."
ibmcloud target -r "${VM_REGION}" -g "${RESOURCE_GROUP}"

# Check if vpc-infrastructure plugin is installed
if ! ibmcloud plugin list | grep -q vpc-infrastructure; then
    echo_info "Installing vpc-infrastructure plugin..."
    ibmcloud plugin install vpc-infrastructure -f
else
    echo_info "vpc-infrastructure plugin already installed"
fi

# Generate SSH key if it doesn't exist
if [ ! -f "${SSH_KEY_PATH}" ]; then
    echo_info "Generating SSH key pair at ${SSH_KEY_PATH}..."
    ssh-keygen -t rsa -b 4096 -f "${SSH_KEY_PATH}" -N "" -C "${SSH_KEY_NAME}"
    chmod 600 "${SSH_KEY_PATH}"
    chmod 644 "${SSH_KEY_PATH}.pub"
    echo_info "SSH key generated successfully"
else
    echo_warn "SSH key already exists at ${SSH_KEY_PATH}"
fi

# Upload SSH key to IBM Cloud if not already present
echo_info "Checking if SSH key exists in IBM Cloud..."
SSH_KEY_ID=$(ibmcloud is keys --output json 2>/dev/null | jq -r ".[] | select(.name==\"${SSH_KEY_NAME}\") | .id" | head -n1)

if [ -n "${SSH_KEY_ID}" ] && [ "${SSH_KEY_ID}" != "null" ]; then
    echo_warn "SSH key '${SSH_KEY_NAME}' already exists in IBM Cloud (ID: ${SSH_KEY_ID})"
else
    echo_info "Uploading SSH key to IBM Cloud..."
    SSH_KEY_OUTPUT=$(ibmcloud is key-create "${SSH_KEY_NAME}" @"${SSH_KEY_PATH}.pub" --resource-group-name "${RESOURCE_GROUP}" --output json)
    SSH_KEY_ID=$(echo "${SSH_KEY_OUTPUT}" | jq -r '.id')
    echo_info "SSH key uploaded with ID: ${SSH_KEY_ID}"
fi

# Create VPC if it doesn't exist
echo_info "Checking if VPC exists..."
VPC_ID=$(ibmcloud is vpcs --output json 2>/dev/null | jq -r ".[] | select(.name==\"${VPC_NAME}\") | .id" | head -n1)

if [ -n "${VPC_ID}" ] && [ "${VPC_ID}" != "null" ]; then
    echo_warn "VPC '${VPC_NAME}' already exists (ID: ${VPC_ID})"
else
    echo_info "Creating VPC..."
    VPC_ID=$(ibmcloud is vpc-create "${VPC_NAME}" --resource-group-name "${RESOURCE_GROUP}" --output json | jq -r '.id')
    echo_info "VPC created with ID: ${VPC_ID}"
fi

# Create subnet if it doesn't exist
echo_info "Checking if subnet exists..."
SUBNET_ID=$(ibmcloud is subnets --output json 2>/dev/null | jq -r ".[] | select(.name==\"${SUBNET_NAME}\" and .vpc.id==\"${VPC_ID}\") | .id" | head -n1)

if [ -n "${SUBNET_ID}" ] && [ "${SUBNET_ID}" != "null" ]; then
    echo_warn "Subnet '${SUBNET_NAME}' already exists (ID: ${SUBNET_ID})"
else
    echo_info "Creating subnet..."
    SUBNET_ID=$(ibmcloud is subnet-create "${SUBNET_NAME}" "${VPC_ID}" --zone "${VM_ZONE}" --ipv4-address-count 256 --resource-group-name "${RESOURCE_GROUP}" --output json | jq -r '.id')
    echo_info "Subnet created with ID: ${SUBNET_ID}"
fi

# Create security group if it doesn't exist
echo_info "Checking if security group exists..."
SG_ID=$(ibmcloud is security-groups --output json 2>/dev/null | jq -r ".[] | select(.name==\"${SECURITY_GROUP_NAME}\" and .vpc.id==\"${VPC_ID}\") | .id" | head -n1)

if [ -n "${SG_ID}" ] && [ "${SG_ID}" != "null" ]; then
    echo_warn "Security group '${SECURITY_GROUP_NAME}' already exists (ID: ${SG_ID})"
    
    # Verify required ports are open
    echo_info "Verifying security group rules..."
    # All ports used by the application:
    # 22: SSH, 8443: Presto Console, 9000: MinIO API, 9001: MinIO Console
    # 9083: Hive Metastore, 9443: watsonx.data Console, 10000: Affiliate Junction UI
    REQUIRED_PORTS=(22 8443 9000 9001 9083 9443 10000)
    MISSING_PORTS=()
    
    for port in "${REQUIRED_PORTS[@]}"; do
        if ! ibmcloud is security-group-rules "${SG_ID}" --output json 2>/dev/null | jq -e ".[] | select(.direction==\"inbound\" and .protocol==\"tcp\" and .port_min==${port} and .port_max==${port})" > /dev/null 2>&1; then
            MISSING_PORTS+=($port)
        fi
    done
    
    if [ ${#MISSING_PORTS[@]} -gt 0 ]; then
        echo_warn "Missing security group rules for ports: ${MISSING_PORTS[*]}"
        echo_info "Adding missing rules..."
        for port in "${MISSING_PORTS[@]}"; do
            ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min ${port} --port-max ${port}
        done
    else
        echo_info "All required security group rules are present"
    fi
else
    echo_info "Creating security group..."
    SG_ID=$(ibmcloud is security-group-create "${SECURITY_GROUP_NAME}" "${VPC_ID}" --resource-group-name "${RESOURCE_GROUP}" --output json | jq -r '.id')
    
    # Add rules for all application ports
    echo_info "Adding security group rules for all application ports..."
    ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min 22 --port-max 22      # SSH
    ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min 8443 --port-max 8443  # Presto Console
    ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min 9000 --port-max 9000  # MinIO API
    ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min 9001 --port-max 9001  # MinIO Console
    ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min 9083 --port-max 9083  # Hive Metastore
    ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min 9443 --port-max 9443  # watsonx.data Console
    ibmcloud is security-group-rule-add "${SG_ID}" inbound tcp --port-min 10000 --port-max 10000 # Affiliate Junction UI
    ibmcloud is security-group-rule-add "${SG_ID}" outbound all
    echo_info "Security group created with ID: ${SG_ID}"
fi

# Auto-detect image if not specified
if [ -z "${VM_IMAGE}" ]; then
    echo_info "Auto-detecting available Red Hat image..."
    VM_IMAGE=$(ibmcloud is images --output json 2>/dev/null | jq -r '.[] | select(.operating_system.name | contains("red")) | select(.status=="available") | select(.visibility=="public") | .name' | grep -i "redhat\|rhel" | head -n1)
    
    if [ -z "${VM_IMAGE}" ] || [ "${VM_IMAGE}" == "null" ]; then
        echo_warn "No Red Hat image found, trying Ubuntu..."
        VM_IMAGE=$(ibmcloud is images --output json 2>/dev/null | jq -r '.[] | select(.operating_system.name | contains("ubuntu")) | select(.status=="available") | select(.visibility=="public") | .name' | head -n1)
    fi
    
    if [ -z "${VM_IMAGE}" ] || [ "${VM_IMAGE}" == "null" ]; then
        echo_error "No suitable image found. Please specify an image with --image or VM_IMAGE environment variable"
        echo_info "Available images:"
        ibmcloud is images --output json 2>/dev/null | jq -r '.[] | select(.status=="available") | select(.visibility=="public") | .name' | head -n 10
        exit 1
    fi
    
    echo_info "Using image: ${VM_IMAGE}"
fi

# Create VM instance
echo_info "Checking if VM instance exists..."
INSTANCE_ID=$(ibmcloud is instances --output json 2>/dev/null | jq -r ".[] | select(.name==\"${VM_NAME}\") | .id" | head -n1)

if [ -n "${INSTANCE_ID}" ] && [ "${INSTANCE_ID}" != "null" ]; then
    if [ "$FORCE" = true ]; then
        echo_warn "VM instance '${VM_NAME}' exists. Force flag set - deleting and recreating..."
        
        # Delete floating IP first
        FIP_NAME="${VM_NAME}-fip"
        if ibmcloud is floating-ips --output json 2>/dev/null | jq -e ".[] | select(.name==\"${FIP_NAME}\")" > /dev/null 2>&1; then
            echo_info "Deleting floating IP: ${FIP_NAME}"
            ibmcloud is floating-ip-release "${FIP_NAME}" -f
        fi
        
        # Delete instance
        echo_info "Deleting existing instance: ${INSTANCE_ID}"
        ibmcloud is instance-delete "${INSTANCE_ID}" -f
        echo_info "Waiting for deletion to complete..."
        sleep 15
        
        # Clear instance ID to trigger recreation
        INSTANCE_ID=""
    else
        echo_warn "VM instance '${VM_NAME}' already exists (ID: ${INSTANCE_ID})"
        echo_info "Use --force to recreate or --teardown to delete all resources"
        
        # Check instance status
        INSTANCE_STATUS=$(ibmcloud is instance "${INSTANCE_ID}" --output json | jq -r '.status')
        echo_info "Instance status: ${INSTANCE_STATUS}"
        
        if [ "${INSTANCE_STATUS}" != "running" ]; then
            echo_info "Waiting for instance to be running..."
            for i in {1..30}; do
                sleep 10
                INSTANCE_STATUS=$(ibmcloud is instance "${INSTANCE_ID}" --output json | jq -r '.status')
                echo_info "Status check ${i}/30: ${INSTANCE_STATUS}"
                if [ "${INSTANCE_STATUS}" == "running" ]; then
                    break
                fi
            done
        fi
    fi
fi

if [ -z "${INSTANCE_ID}" ] || [ "${INSTANCE_ID}" == "null" ]; then
    echo_info "Creating VM instance (this may take 2-3 minutes)..."
    echo_info "Note: Using cloud-init to inject SSH key (IBM Cloud CLI workaround)"
    
    # Get the public key content for cloud-init
    SSH_PUBLIC_KEY=$(cat "${SSH_KEY_PATH}.pub")
    
    # Debug: Show first 50 chars of SSH key
    echo_info "SSH Public Key (first 50 chars): ${SSH_PUBLIC_KEY:0:50}..."
    
    # Create cloud-init user-data to inject SSH key
    # Build the base cloud-init config
    # Note: read returns non-zero when reaching EOF, so we use || true
    read -r -d '' USER_DATA <<'EOF' || true
#cloud-config
users:
  - name: root
    ssh_authorized_keys:
      - SSH_KEY_PLACEHOLDER

packages:
  - git
  - python39
  - python39-pip
  - python39-devel
  - wget
  - curl
  - unzip
  - java-11-openjdk
  - java-17-openjdk
  - java-17-openjdk-devel
  - jq

runcmd:
  - echo "Cloud-init complete" > /root/cloud-init-complete.txt
  - echo "SSH key from cloud-init:" >> /root/cloud-init-debug.log
  - cat /root/.ssh/authorized_keys >> /root/cloud-init-debug.log 2>&1 || echo "No authorized_keys file" >> /root/cloud-init-debug.log
EOF
    
    # Replace SSH key placeholder with actual key
    USER_DATA="${USER_DATA//SSH_KEY_PLACEHOLDER/$SSH_PUBLIC_KEY}"
    
    # Add auto-install commands if flag is set
    if [ "$AUTO_INSTALL" = true ]; then
        # Append auto-install commands to runcmd section (proper YAML indentation)
        # Note: The last line must be quoted to prevent YAML from parsing the colon as a key-value separator
        USER_DATA="${USER_DATA}
  - echo \"Starting automated installation...\" >> /root/install.log
  - cd /root
  - git clone https://github.com/aldrineeinsteen/affiliate-junction-demo.git >> /root/install.log 2>&1
  - cd affiliate-junction-demo
  - nohup ./setup-infra.sh install >> /root/install.log 2>&1 &
  - 'echo \"Installation started. Monitor with: tail -f /root/install.log\" > /root/auto-install-started.txt'"
    fi
    
    # Debug: Save user-data to file for inspection
    echo "${USER_DATA}" > /tmp/cloud-init-user-data.txt
    echo_info "Cloud-init user-data saved to /tmp/cloud-init-user-data.txt for inspection"
    
    echo_info "Command: ibmcloud is instance-create ${VM_NAME} ${VPC_ID} ${VM_ZONE} ${VM_PROFILE} ${SUBNET_ID} --image ${VM_IMAGE} --keys ${SSH_KEY_ID} --sgs ${SG_ID} --user-data <cloud-init> --resource-group-name ${RESOURCE_GROUP}"
    
    # Create instance and capture output
    set +e  # Temporarily disable exit on error
    INSTANCE_OUTPUT=$(ibmcloud is instance-create "${VM_NAME}" "${VPC_ID}" "${VM_ZONE}" "${VM_PROFILE}" "${SUBNET_ID}" \
        --image "${VM_IMAGE}" \
        --keys "${SSH_KEY_ID}" \
        --sgs "${SG_ID}" \
        --user-data "${USER_DATA}" \
        --resource-group-name "${RESOURCE_GROUP}" \
        --output json 2>&1)
    EXIT_CODE=$?
    set -e  # Re-enable exit on error
    
    if [ ${EXIT_CODE} -ne 0 ]; then
        echo_error "VM creation failed with exit code ${EXIT_CODE}"
        echo "${INSTANCE_OUTPUT}"
        
        # Check if instance was created anyway
        echo_info "Checking if instance was created despite error..."
        sleep 5
        INSTANCE_ID=$(ibmcloud is instances --output json 2>/dev/null | jq -r ".[] | select(.name==\"${VM_NAME}\") | .id" | head -n1)
        if [ -n "${INSTANCE_ID}" ] && [ "${INSTANCE_ID}" != "null" ]; then
            echo_warn "Instance was created despite error. ID: ${INSTANCE_ID}"
        else
            echo_error "Instance was not created. Please check the error above."
            exit 1
        fi
    else
        # Check if output is valid JSON
        if echo "${INSTANCE_OUTPUT}" | jq empty 2>/dev/null; then
            INSTANCE_ID=$(echo "${INSTANCE_OUTPUT}" | jq -r '.id')
            if [ -z "${INSTANCE_ID}" ] || [ "${INSTANCE_ID}" == "null" ]; then
                echo_error "Failed to get instance ID from response"
                echo "${INSTANCE_OUTPUT}"
                exit 1
            fi
            echo_info "VM instance created with ID: ${INSTANCE_ID}"
        else
            echo_error "Failed to create VM instance. Output:"
            echo "${INSTANCE_OUTPUT}"
            exit 1
        fi
    fi
    
    echo_info "Waiting for VM to be running..."
    for i in {1..30}; do
        sleep 10
        INSTANCE_STATUS=$(ibmcloud is instance "${INSTANCE_ID}" --output json 2>/dev/null | jq -r '.status')
        echo_info "Status check ${i}/30: ${INSTANCE_STATUS}"
        if [ "${INSTANCE_STATUS}" == "running" ]; then
            break
        fi
    done
fi

# Get VM details
echo_info "Retrieving VM details..."
VM_DETAILS=$(ibmcloud is instance "${INSTANCE_ID}" --output json)

# Try to get primary network attachment first (newer VPC instances)
PRIMARY_NAC=$(echo "${VM_DETAILS}" | jq -r '.primary_network_attachment // empty')
if [ -n "${PRIMARY_NAC}" ] && [ "${PRIMARY_NAC}" != "null" ]; then
    echo_info "Instance uses network attachments (newer VPC feature)"
    VM_IP=$(echo "${VM_DETAILS}" | jq -r '.primary_network_attachment.virtual_network_interface.primary_ip.address')
    VNI_ID=$(echo "${VM_DETAILS}" | jq -r '.primary_network_attachment.virtual_network_interface.id')
    
    # Check if floating IP already exists for this VNI
    FLOATING_IP=$(ibmcloud is floating-ips --output json 2>/dev/null | jq -r ".[] | select(.target.id==\"${VNI_ID}\") | .address" | head -n1)
    
    if [ -n "${FLOATING_IP}" ] && [ "${FLOATING_IP}" != "null" ]; then
        echo_warn "Floating IP already exists: ${FLOATING_IP}"
    else
        echo_info "Creating floating IP for virtual network interface..."
        set +e  # Temporarily disable exit on error
        FLOATING_IP_OUTPUT=$(ibmcloud is floating-ip-reserve "${VM_NAME}-fip" --vni "${VNI_ID}" --resource-group-name "${RESOURCE_GROUP}" --output json 2>&1)
        FIP_EXIT_CODE=$?
        set -e  # Re-enable exit on error
        
        if [ ${FIP_EXIT_CODE} -eq 0 ] && echo "${FLOATING_IP_OUTPUT}" | jq empty 2>/dev/null; then
            FLOATING_IP=$(echo "${FLOATING_IP_OUTPUT}" | jq -r '.address')
            echo_info "Floating IP created: ${FLOATING_IP}"
        else
            echo_error "Failed to create floating IP (exit code: ${FIP_EXIT_CODE})"
            echo "${FLOATING_IP_OUTPUT}"
            echo_warn "You can manually assign a floating IP from the IBM Cloud console"
            FLOATING_IP=""
        fi
    fi
else
    # Fallback to primary network interface (older VPC instances)
    echo_info "Instance uses network interface (legacy VPC feature)"
    VM_IP=$(echo "${VM_DETAILS}" | jq -r '.primary_network_interface.primary_ip.address')
    NIC_ID=$(echo "${VM_DETAILS}" | jq -r '.primary_network_interface.id')
    
    # Check if floating IP already exists for this NIC
    FLOATING_IP=$(ibmcloud is floating-ips --output json 2>/dev/null | jq -r ".[] | select(.target.id==\"${NIC_ID}\") | .address" | head -n1)
    
    if [ -n "${FLOATING_IP}" ] && [ "${FLOATING_IP}" != "null" ]; then
        echo_warn "Floating IP already exists: ${FLOATING_IP}"
    else
        echo_info "Creating floating IP for network interface..."
        set +e  # Temporarily disable exit on error
        FLOATING_IP_OUTPUT=$(ibmcloud is floating-ip-reserve "${VM_NAME}-fip" --nic "${NIC_ID}" --resource-group-name "${RESOURCE_GROUP}" --output json 2>&1)
        FIP_EXIT_CODE=$?
        set -e  # Re-enable exit on error
        
        if [ ${FIP_EXIT_CODE} -eq 0 ] && echo "${FLOATING_IP_OUTPUT}" | jq empty 2>/dev/null; then
            FLOATING_IP=$(echo "${FLOATING_IP_OUTPUT}" | jq -r '.address')
            echo_info "Floating IP created: ${FLOATING_IP}"
        else
            echo_error "Failed to create floating IP (exit code: ${FIP_EXIT_CODE})"
            echo "${FLOATING_IP_OUTPUT}"
            echo_warn "You can manually assign a floating IP from the IBM Cloud console"
            FLOATING_IP=""
        fi
    fi
fi

# Validate floating IP
if [ -z "${FLOATING_IP}" ] || [ "${FLOATING_IP}" == "null" ]; then
    echo_warn "No floating IP assigned. VM is only accessible via private IP: ${VM_IP}"
    echo_warn "You can manually assign a floating IP from the IBM Cloud console"
    FLOATING_IP="<not-assigned>"
fi

# Save connection details
CONNECTION_FILE="${HOME}/.ssh/${VM_NAME}-connection.txt"
cat > "${CONNECTION_FILE}" << EOF
# ${VM_NAME} Connection Details
# Generated: $(date)

VM Name: ${VM_NAME}
VM ID: ${INSTANCE_ID}
Private IP: ${VM_IP}
Public IP: ${FLOATING_IP}
SSH Key: ${SSH_KEY_PATH}
Zone: ${VM_ZONE}

# SSH Connection Command:
ssh -i ${SSH_KEY_PATH} root@${FLOATING_IP}

# SCP Example (upload):
scp -i ${SSH_KEY_PATH} local-file root@${FLOATING_IP}:/remote/path/

# SCP Example (download):
scp -i ${SSH_KEY_PATH} root@${FLOATING_IP}:/remote/path/file local-path/

# Web UI Access:
http://${FLOATING_IP}:10000

# To delete this VM and all resources:
# ibmcloud is instance-delete ${INSTANCE_ID} -f
# ibmcloud is floating-ip-release ${VM_NAME}-fip -f
# ibmcloud is security-group-delete ${SG_ID} -f
# ibmcloud is subnet-delete ${SUBNET_ID} -f
# ibmcloud is vpc-delete ${VPC_ID} -f
# ibmcloud is key-delete ${SSH_KEY_NAME} -f
EOF

chmod 600 "${CONNECTION_FILE}"

# Add SSH config entry only if we have a valid floating IP
SSH_CONFIG="${HOME}/.ssh/config"
if [ "${FLOATING_IP}" != "<not-assigned>" ] && [ -n "${FLOATING_IP}" ]; then
    if ! grep -q "Host ${VM_NAME}" "${SSH_CONFIG}" 2>/dev/null; then
        echo_info "Adding SSH config entry..."
        cat >> "${SSH_CONFIG}" << EOF

# ${VM_NAME} - Auto-generated by setup-vm.sh
Host ${VM_NAME}
    HostName ${FLOATING_IP}
    User root
    IdentityFile ${SSH_KEY_PATH}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF
        chmod 600 "${SSH_CONFIG}"
        echo_info "SSH config entry added. You can now connect with: ssh ${VM_NAME}"
    else
        echo_warn "SSH config entry already exists for ${VM_NAME}"
    fi
else
    echo_warn "Skipping SSH config entry (no floating IP assigned)"
fi

# Summary
echo ""
echo_info "=========================================="
echo_info "VM Provisioning Complete!"
echo_info "=========================================="
echo_info "VM Name: ${VM_NAME}"
echo_info "VM ID: ${INSTANCE_ID}"
echo_info "Public IP: ${FLOATING_IP}"
echo_info "Private IP: ${VM_IP}"
echo_info "Resource Group: ${RESOURCE_GROUP}"
echo_info "Region: ${VM_REGION}"
echo_info "Zone: ${VM_ZONE}"
echo_info "SSH Key: ${SSH_KEY_PATH}"
echo_info "Connection details saved to: ${CONNECTION_FILE}"
echo ""
if [ "${FLOATING_IP}" != "<not-assigned>" ] && [ -n "${FLOATING_IP}" ]; then
    echo_info "Connect to your VM:"
    echo "  ssh ${VM_NAME}"
    echo "  OR"
    echo "  ssh -i ${SSH_KEY_PATH} root@${FLOATING_IP}"
    echo ""
    echo_info "Access Web UI (after running setup.sh on VM):"
    echo "  http://${FLOATING_IP}:10000"
    echo ""
    echo_info "To deploy the application, run on the VM:"
    echo "  git clone <your-repo-url>"
    echo "  cd affiliate-junction-demo"
    echo "  ./setup.sh"
    echo ""
    echo_warn "Note: Wait a few minutes for the VM to fully boot before connecting"
    echo_info "Test SSH connection: ssh -i ${SSH_KEY_PATH} root@${FLOATING_IP} 'echo Connection successful!'"
else
    echo_warn "VM created but no floating IP assigned!"
    echo_info "Private IP: ${VM_IP}"
    echo ""
    echo_info "To assign a floating IP manually:"
    echo "  1. Go to IBM Cloud Console > VPC Infrastructure > Virtual server instances"
    echo "  2. Click on '${VM_NAME}'"
    echo "  3. In the Network interfaces section, click 'Reserve' next to Floating IP"
    echo "  4. Once assigned, update your SSH config with the floating IP"
    echo ""
    echo_info "Or use the IBM Cloud CLI:"
    echo "  ibmcloud is floating-ip-reserve ${VM_NAME}-fip --target <VNI_ID>"
fi

# Made with Bob
