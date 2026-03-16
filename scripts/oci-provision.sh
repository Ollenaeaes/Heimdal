#!/bin/bash
# =============================================================================
# Provision Oracle Free Tier ARM VM for Heimdal
# =============================================================================
# Automates: VCN + Subnet + Security List + VM creation + firewall rules
# Requires: OCI CLI configured (~/.oci/config) with API key uploaded
#
# Usage: make oci-provision
# =============================================================================

set -euo pipefail

COMPARTMENT_ID="ocid1.tenancy.oc1..aaaaaaaafeummgc36b6eynotig4u4rnlq5citi2zpey6xsszq7bhojzylgga"
REGION="eu-stockholm-1"
AD="meqH:EU-STOCKHOLM-1-AD-1"
DISPLAY_PREFIX="heimdal"
STATE_FILE=".oci-state.json"
SSH_PUB_KEY_FILE="${SSH_PUB_KEY:-$HOME/.ssh/id_rsa.pub}"

# ARM shape — Oracle Free Tier: up to 4 OCPUs + 24GB RAM
SHAPE="VM.Standard.A1.Flex"
OCPUS=4
MEMORY_GB=24
BOOT_VOLUME_GB=100  # Free tier allows up to 200GB total

echo "=== Heimdal OCI Provisioning ==="
echo "Region:     $REGION"
echo "AD:         $AD"
echo "Shape:      $SHAPE (${OCPUS} OCPUs, ${MEMORY_GB}GB RAM)"
echo "SSH key:    $SSH_PUB_KEY_FILE"
echo ""

if [ ! -f "$SSH_PUB_KEY_FILE" ]; then
    echo "ERROR: SSH public key not found at $SSH_PUB_KEY_FILE"
    echo "Set SSH_PUB_KEY env var or create a key with: ssh-keygen -t ed25519"
    exit 1
fi

SSH_PUB_KEY=$(cat "$SSH_PUB_KEY_FILE")

# Helper: save state so we can resume / reference later
save_state() {
    echo "$1" > "$STATE_FILE"
}

load_state() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo "{}"
    fi
}

get_state() {
    load_state | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$1',''))" 2>/dev/null || echo ""
}

set_state() {
    local current
    current=$(load_state)
    echo "$current" | python3 -c "
import sys, json
d = json.load(sys.stdin)
d['$1'] = '$2'
json.dump(d, sys.stdout, indent=2)
" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
}

# ---- Step 1: VCN (Virtual Cloud Network) ------------------------------------
VCN_ID=$(get_state "vcn_id")
if [ -z "$VCN_ID" ]; then
    echo "Creating VCN..."
    VCN_ID=$(oci network vcn create \
        --compartment-id "$COMPARTMENT_ID" \
        --display-name "${DISPLAY_PREFIX}-vcn" \
        --cidr-blocks '["10.0.0.0/16"]' \
        --query 'data.id' --raw-output)
    set_state "vcn_id" "$VCN_ID"
    echo "  VCN: $VCN_ID"
else
    echo "VCN exists: $VCN_ID"
fi

# ---- Step 2: Internet Gateway -----------------------------------------------
IGW_ID=$(get_state "igw_id")
if [ -z "$IGW_ID" ]; then
    echo "Creating Internet Gateway..."
    IGW_ID=$(oci network internet-gateway create \
        --compartment-id "$COMPARTMENT_ID" \
        --vcn-id "$VCN_ID" \
        --display-name "${DISPLAY_PREFIX}-igw" \
        --is-enabled true \
        --query 'data.id' --raw-output)
    set_state "igw_id" "$IGW_ID"
    echo "  IGW: $IGW_ID"
else
    echo "IGW exists: $IGW_ID"
fi

# ---- Step 3: Route Table (default → internet) -------------------------------
echo "Updating default route table..."
RT_ID=$(oci network vcn get --vcn-id "$VCN_ID" --query 'data."default-route-table-id"' --raw-output)
oci network route-table update \
    --rt-id "$RT_ID" \
    --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW_ID\"}]" \
    --force > /dev/null
set_state "rt_id" "$RT_ID"
echo "  Route table updated: $RT_ID"

# ---- Step 4: Security List (SSH + HTTP + HTTPS) -----------------------------
SL_ID=$(get_state "sl_id")
if [ -z "$SL_ID" ]; then
    echo "Creating Security List..."
    SL_ID=$(oci network security-list create \
        --compartment-id "$COMPARTMENT_ID" \
        --vcn-id "$VCN_ID" \
        --display-name "${DISPLAY_PREFIX}-sl" \
        --ingress-security-rules '[
            {"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},
            {"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":80,"max":80}}},
            {"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":443,"max":443}}},
            {"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":8000,"max":8000}}}
        ]' \
        --egress-security-rules '[
            {"destination":"0.0.0.0/0","protocol":"all"}
        ]' \
        --query 'data.id' --raw-output)
    set_state "sl_id" "$SL_ID"
    echo "  Security List: $SL_ID"
else
    echo "Security List exists: $SL_ID"
fi

# ---- Step 5: Subnet ---------------------------------------------------------
SUBNET_ID=$(get_state "subnet_id")
if [ -z "$SUBNET_ID" ]; then
    echo "Creating Subnet..."
    SUBNET_ID=$(oci network subnet create \
        --compartment-id "$COMPARTMENT_ID" \
        --vcn-id "$VCN_ID" \
        --display-name "${DISPLAY_PREFIX}-subnet" \
        --cidr-block "10.0.0.0/24" \
        --security-list-ids "[\"$SL_ID\"]" \
        --route-table-id "$RT_ID" \
        --query 'data.id' --raw-output)
    set_state "subnet_id" "$SUBNET_ID"
    echo "  Subnet: $SUBNET_ID"
else
    echo "Subnet exists: $SUBNET_ID"
fi

# ---- Step 6: Find ARM image (Oracle Linux or Ubuntu) ------------------------
echo "Finding ARM image..."
IMAGE_ID=$(oci compute image list \
    --compartment-id "$COMPARTMENT_ID" \
    --operating-system "Canonical Ubuntu" \
    --operating-system-version "22.04" \
    --shape "$SHAPE" \
    --sort-by TIMECREATED \
    --sort-order DESC \
    --limit 1 \
    --query 'data[0].id' --raw-output)

if [ -z "$IMAGE_ID" ] || [ "$IMAGE_ID" = "None" ]; then
    echo "Ubuntu 22.04 ARM not found, trying Oracle Linux..."
    IMAGE_ID=$(oci compute image list \
        --compartment-id "$COMPARTMENT_ID" \
        --operating-system "Oracle Linux" \
        --operating-system-version "8" \
        --shape "$SHAPE" \
        --sort-by TIMECREATED \
        --sort-order DESC \
        --limit 1 \
        --query 'data[0].id' --raw-output)
fi
echo "  Image: $IMAGE_ID"

# ---- Step 7: Launch Instance -------------------------------------------------
INSTANCE_ID=$(get_state "instance_id")
if [ -z "$INSTANCE_ID" ]; then
    echo "Launching ARM instance (${OCPUS} OCPUs, ${MEMORY_GB}GB RAM)..."
    INSTANCE_ID=$(oci compute instance launch \
        --compartment-id "$COMPARTMENT_ID" \
        --availability-domain "$AD" \
        --display-name "${DISPLAY_PREFIX}-prod" \
        --shape "$SHAPE" \
        --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEMORY_GB}" \
        --image-id "$IMAGE_ID" \
        --subnet-id "$SUBNET_ID" \
        --assign-public-ip true \
        --boot-volume-size-in-gbs "$BOOT_VOLUME_GB" \
        --metadata "{\"ssh_authorized_keys\":\"$SSH_PUB_KEY\"}" \
        --query 'data.id' --raw-output)
    set_state "instance_id" "$INSTANCE_ID"
    echo "  Instance: $INSTANCE_ID"

    echo "Waiting for instance to be RUNNING..."
    oci compute instance get --instance-id "$INSTANCE_ID" --wait-for-state RUNNING > /dev/null
    echo "  Instance is running!"
else
    echo "Instance exists: $INSTANCE_ID"
fi

# ---- Step 8: Get public IP ---------------------------------------------------
echo "Getting public IP..."
VNIC_ATTACHMENTS=$(oci compute vnic-attachment list \
    --compartment-id "$COMPARTMENT_ID" \
    --instance-id "$INSTANCE_ID" \
    --query 'data[0]."vnic-id"' --raw-output)

PUBLIC_IP=$(oci network vnic get \
    --vnic-id "$VNIC_ATTACHMENTS" \
    --query 'data."public-ip"' --raw-output)

set_state "public_ip" "$PUBLIC_IP"

echo ""
echo "=== Provisioning Complete ==="
echo ""
echo "  Public IP:  $PUBLIC_IP"
echo "  SSH:        ssh ubuntu@$PUBLIC_IP"
echo "  State file: $STATE_FILE"
echo ""
echo "Next steps:"
echo "  1. make oci-setup    # Install Docker + configure the VM"
echo "  2. make oci-deploy   # Deploy Heimdal to the VM"
echo ""
