#!/bin/bash

# =============================================================================
# Hyperledger Fabric - 3 Org IoT Edge Network Setup Script
# =============================================================================
# Run this from anywhere. It will install fabric, bring up the network,
# add Org3, and deploy the eventcc chaincode across all 3 orgs.
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --------------------------------------------------------------------------
# CONFIG  change these if needed
# --------------------------------------------------------------------------
BASE_DIR="$HOME/thisbetterwork"
FABRIC_VERSION="2.5.16"
CA_VERSION="1.5.17"
CHANNEL_NAME="mychannel"
CC_NAME="eventcc"
CC_VERSION="1.0"

# --------------------------------------------------------------------------
# STEP 1  Install Fabric if not already installed
# --------------------------------------------------------------------------
log "Checking Fabric installation..."

if [ ! -d "$BASE_DIR/fabric-samples" ]; then
  log "Fabric not found. Installing to $BASE_DIR..."
  mkdir -p "$BASE_DIR"
  cd "$BASE_DIR"
  curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh | bash -s -- --fabric-version $FABRIC_VERSION --ca-version $CA_VERSION docker binary samples
else
  log "Fabric samples already found at $BASE_DIR/fabric-samples"
fi

FABRIC_SAMPLES="$BASE_DIR/fabric-samples"
TEST_NETWORK="$FABRIC_SAMPLES/test-network"

# --------------------------------------------------------------------------
# STEP 2  Set PATH
# --------------------------------------------------------------------------
export PATH="$FABRIC_SAMPLES/bin:$PATH"
export FABRIC_CFG_PATH="$FABRIC_SAMPLES/config/"

if ! command -v peer &> /dev/null; then
  error "peer binary not found. Check $FABRIC_SAMPLES/bin"
fi
log "peer binary found: $(peer version | head -1)"

# --------------------------------------------------------------------------
# STEP 3  Bring down any existing network
# --------------------------------------------------------------------------
log "Tearing down any existing network..."
cd "$TEST_NETWORK"
./network.sh down 2>/dev/null || true
docker volume prune -f > /dev/null 2>&1 || true

# --------------------------------------------------------------------------
# STEP 4  Start network and create channel
# --------------------------------------------------------------------------
log "Starting network and creating channel '$CHANNEL_NAME'..."
./network.sh up createChannel -c $CHANNEL_NAME

# --------------------------------------------------------------------------
# STEP 5  Deploy chaincode on Org1 + Org2
# --------------------------------------------------------------------------
log "Deploying chaincode '$CC_NAME' on Org1 and Org2..."
./network.sh deployCC \
  -ccn $CC_NAME \
  -ccp ../asset-transfer-events/chaincode-go \
  -ccl go \
  -c $CHANNEL_NAME

# --------------------------------------------------------------------------
# STEP 6  Add Org3
# --------------------------------------------------------------------------
log "Adding Org3 to channel..."
cd "$TEST_NETWORK/addOrg3"
./addOrg3.sh up -c $CHANNEL_NAME

cd "$TEST_NETWORK"

# --------------------------------------------------------------------------
# STEP 7  Get current sequence number
# --------------------------------------------------------------------------
log "Getting current chaincode sequence..."

export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
export CORE_PEER_ADDRESS="localhost:7051"

CURRENT_SEQ=$(peer lifecycle chaincode querycommitted --channelID $CHANNEL_NAME --name $CC_NAME --output json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['sequence'])" 2>/dev/null || echo "0")
NEW_SEQ=$((CURRENT_SEQ + 1))
log "Current sequence: $CURRENT_SEQ → New sequence: $NEW_SEQ"

# --------------------------------------------------------------------------
# STEP 8  Install chaincode on Org3 and get package ID
# --------------------------------------------------------------------------
log "Installing chaincode on Org3..."

export CORE_PEER_LOCALMSPID="Org3MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp"
export CORE_PEER_ADDRESS="localhost:11051"

peer lifecycle chaincode install "$TEST_NETWORK/eventcc.tar.gz"

ORG3_PKG_ID=$(peer lifecycle chaincode queryinstalled --output json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cc in data.get('installed_chaincodes', []):
    if cc['label'] == '${CC_NAME}_${CC_VERSION}':
        print(cc['package_id'])
        break
")

log "Org3 Package ID: $ORG3_PKG_ID"

# --------------------------------------------------------------------------
# STEP 9  Get Org1 and Org2 package IDs
# --------------------------------------------------------------------------
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
export CORE_PEER_ADDRESS="localhost:7051"

ORG1_PKG_ID=$(peer lifecycle chaincode queryinstalled --output json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cc in data.get('installed_chaincodes', []):
    if cc['label'] == '${CC_NAME}_${CC_VERSION}':
        print(cc['package_id'])
        break
")
log "Org1 Package ID: $ORG1_PKG_ID"

export CORE_PEER_LOCALMSPID="Org2MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
export CORE_PEER_ADDRESS="localhost:9051"

ORG2_PKG_ID=$(peer lifecycle chaincode queryinstalled --output json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cc in data.get('installed_chaincodes', []):
    if cc['label'] == '${CC_NAME}_${CC_VERSION}':
        print(cc['package_id'])
        break
")
log "Org2 Package ID: $ORG2_PKG_ID"

ORDERER_CA="${TEST_NETWORK}/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem"

# --------------------------------------------------------------------------
# STEP 10  Approve for all 3 orgs
# --------------------------------------------------------------------------
log "Approving chaincode for Org1..."
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
export CORE_PEER_ADDRESS="localhost:7051"

peer lifecycle chaincode approveformyorg \
  -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "$ORDERER_CA" \
  --channelID $CHANNEL_NAME --name $CC_NAME \
  --version $CC_VERSION --sequence $NEW_SEQ \
  --package-id "$ORG1_PKG_ID"

log "Approving chaincode for Org2..."
export CORE_PEER_LOCALMSPID="Org2MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
export CORE_PEER_ADDRESS="localhost:9051"

peer lifecycle chaincode approveformyorg \
  -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "$ORDERER_CA" \
  --channelID $CHANNEL_NAME --name $CC_NAME \
  --version $CC_VERSION --sequence $NEW_SEQ \
  --package-id "$ORG2_PKG_ID"

log "Approving chaincode for Org3..."
export CORE_PEER_LOCALMSPID="Org3MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp"
export CORE_PEER_ADDRESS="localhost:11051"

peer lifecycle chaincode approveformyorg \
  -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "$ORDERER_CA" \
  --channelID $CHANNEL_NAME --name $CC_NAME \
  --version $CC_VERSION --sequence $NEW_SEQ \
  --package-id "$ORG3_PKG_ID"

# --------------------------------------------------------------------------
# STEP 11  Check commit readiness
# --------------------------------------------------------------------------
log "Checking commit readiness..."
peer lifecycle chaincode checkcommitreadiness \
  --channelID $CHANNEL_NAME --name $CC_NAME \
  --version $CC_VERSION --sequence $NEW_SEQ --output json

# --------------------------------------------------------------------------
# STEP 12  Commit chaincode
# --------------------------------------------------------------------------
log "Committing chaincode across all 3 orgs..."
peer lifecycle chaincode commit \
  -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "$ORDERER_CA" \
  --channelID $CHANNEL_NAME --name $CC_NAME \
  --version $CC_VERSION --sequence $NEW_SEQ \
  --peerAddresses localhost:7051 \
  --tlsRootCertFiles "${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem" \
  --peerAddresses localhost:9051 \
  --tlsRootCertFiles "${TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem" \
  --peerAddresses localhost:11051 \
  --tlsRootCertFiles "${TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/tlsca/tlsca.org3.example.com-cert.pem"

# --------------------------------------------------------------------------
# STEP 13  Verify
# --------------------------------------------------------------------------
log "Verifying deployment..."
peer lifecycle chaincode querycommitted --channelID $CHANNEL_NAME --name $CC_NAME --output json

# --------------------------------------------------------------------------
# DONE
# --------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Network is up and chaincode is deployed!  ${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Org1 peer: localhost:7051"
echo "  Org2 peer: localhost:9051"
echo "  Org3 peer: localhost:11051"
echo "  Channel:   $CHANNEL_NAME"
echo "  Chaincode: $CC_NAME"
echo ""
echo "To tear down: cd $TEST_NETWORK && ./network.sh down"
echo ""

# Save env vars to a file for easy sourcing later
cat > "$BASE_DIR/env.sh" << EOF
export PATH="$FABRIC_SAMPLES/bin:\$PATH"
export FABRIC_CFG_PATH="$FABRIC_SAMPLES/config/"
export ORDERER_CA="$ORDERER_CA"
export TEST_NETWORK="$TEST_NETWORK"
export CHANNEL_NAME="$CHANNEL_NAME"
export CC_NAME="$CC_NAME"

setOrg1() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org1MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="$TEST_NETWORK/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="$TEST_NETWORK/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
  export CORE_PEER_ADDRESS="localhost:7051"
  echo "Switched to Org1"
}

setOrg2() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org2MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="$TEST_NETWORK/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="$TEST_NETWORK/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
  export CORE_PEER_ADDRESS="localhost:9051"
  echo "Switched to Org2"
}

setOrg3() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org3MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="$TEST_NETWORK/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="$TEST_NETWORK/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp"
  export CORE_PEER_ADDRESS="localhost:11051"
  echo "Switched to Org3"
}
EOF

log "Env helpers saved to $BASE_DIR/env.sh"
log "Run: source $BASE_DIR/env.sh  then use setOrg1/setOrg2/setOrg3 to switch orgs"