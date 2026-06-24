#!/bin/bash

# =============================================================================
# deploy_channels.sh - FULLY MANUAL, NO network.sh createChannel
# iot-channel      → Org1, Org2, Org3
# security-channel → Org1, Org2 ONLY (Org3 never touched)
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error(){ echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

BASE="$HOME/thisbetterwork/fabric-samples"
TN="$BASE/test-network"
ORDERER_CA="$TN/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem"
ORDERER="localhost:7050"

IOT_CH="iot-channel"
SEC_CH="security-channel"
IOT_CC="iotcc"
SEC_CC="securitycc"
CC_VER="1.0"

IOT_CC_PATH="$BASE/iot-channel/chaincode-go"
SEC_CC_PATH="$BASE/security-channel/chaincode-go"

ORG1_PEER="localhost:7051"
ORG2_PEER="localhost:9051"
ORG3_PEER="localhost:11051"

ORG1_TLS="$TN/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem"
ORG2_TLS="$TN/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem"
ORG3_TLS="$TN/organizations/peerOrganizations/org3.example.com/tlsca/tlsca.org3.example.com-cert.pem"

export PATH="$BASE/bin:$PATH"
export FABRIC_CFG_PATH="$BASE/config/"

# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------
setOrg1() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org1MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="$TN/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="$TN/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
  export CORE_PEER_ADDRESS="$ORG1_PEER"
}

setOrg2() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org2MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="$TN/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="$TN/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
  export CORE_PEER_ADDRESS="$ORG2_PEER"
}

setOrg3() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org3MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="$TN/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="$TN/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp"
  export CORE_PEER_ADDRESS="$ORG3_PEER"
}

createChannel() {
  local CHANNEL=$1
  log "Creating channel ${CHANNEL}..."
  # Generate genesis block
  configtxgen -profile ChannelUsingRaft \
    -outputBlock "$TN/channel-artifacts/${CHANNEL}.block" \
    -channelID $CHANNEL \
    -configPath "$TN/configtx"

  # Submit to orderer
  setOrg1
  osnadmin channel join \
    --channelID $CHANNEL \
    --config-block "$TN/channel-artifacts/${CHANNEL}.block" \
    -o localhost:7053 \
    --ca-file "$ORDERER_CA" \
    --client-cert "$TN/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.crt" \
    --client-key "$TN/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.key" \
    2>/dev/null || warn "Orderer may already have ${CHANNEL}, continuing..."

  log "Channel ${CHANNEL} created."
}

joinChannel() {
  local ORG=$1
  local CHANNEL=$2

  case $ORG in
    1) setOrg1 ;;
    2) setOrg2 ;;
    3) setOrg3 ;;
  esac

  # Check if already joined
  if peer channel list 2>/dev/null | grep -q "^${CHANNEL}$"; then
    warn "Org${ORG} already on ${CHANNEL}, skipping join."
    return
  fi

  log "Org${ORG} joining ${CHANNEL}..."
  # Always fetch newest block to avoid genesis block conflict
  peer channel fetch newest "$TN/channel-artifacts/${CHANNEL}-org${ORG}.block" \
    -o $ORDERER --ordererTLSHostnameOverride orderer.example.com \
    -c $CHANNEL --tls --cafile "$ORDERER_CA"

  peer channel join -b "$TN/channel-artifacts/${CHANNEL}-org${ORG}.block"
  log "Org${ORG} joined ${CHANNEL}."
}

getPkgId() {
  local LABEL=$1
  peer lifecycle chaincode queryinstalled --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cc in data.get('installed_chaincodes', []):
    if cc['label'] == '${LABEL}':
        print(cc['package_id'])
        break
" 2>/dev/null
}

installCC() {
  local ORG=$1
  local TAR=$2
  local LABEL=$3

  case $ORG in
    1) setOrg1 ;;
    2) setOrg2 ;;
    3) setOrg3 ;;
  esac

  EXISTING=$(getPkgId "$LABEL")
  if [ -n "$EXISTING" ]; then
    warn "Org${ORG} already has ${LABEL}, skipping install."
    echo "$EXISTING"
    return
  fi

  log "Installing ${LABEL} on Org${ORG}..."
  peer lifecycle chaincode install "$TAR"
  getPkgId "$LABEL"
}

approveCC() {
  local ORG=$1
  local CHANNEL=$2
  local CC_NAME=$3
  local SEQ=$4
  local PKG_ID=$5

  case $ORG in
    1) setOrg1 ;;
    2) setOrg2 ;;
    3) setOrg3 ;;
  esac

  log "Org${ORG} approving ${CC_NAME} on ${CHANNEL}..."
  peer lifecycle chaincode approveformyorg \
    -o $ORDERER --ordererTLSHostnameOverride orderer.example.com \
    --tls --cafile "$ORDERER_CA" \
    --channelID $CHANNEL --name $CC_NAME \
    --version $CC_VER --sequence $SEQ \
    --package-id "$PKG_ID"
  log "Org${ORG} approved ${CC_NAME}."
}

# --------------------------------------------------------------------------
# PREFLIGHT
# --------------------------------------------------------------------------
log "Checking network..."
if ! docker ps | grep -q "peer0.org1.example.com"; then
  error "Network not running. Run setup_fabric.sh first."
fi
if ! docker ps | grep -q "peer0.org3.example.com"; then
  error "Org3 not running. Run: cd addOrg3 && ./addOrg3.sh up -c mychannel"
fi
log "Network up with all 3 orgs."

cd "$TN"

# =============================================================================
# IOT-CHANNEL — Org1, Org2, Org3
# =============================================================================
log "========== IOT-CHANNEL (Org1 + Org2 + Org3) =========="

createChannel $IOT_CH

joinChannel 1 $IOT_CH
joinChannel 2 $IOT_CH
joinChannel 3 $IOT_CH

# Package
if [ ! -f "$TN/${IOT_CC}.tar.gz" ]; then
  log "Packaging ${IOT_CC}..."
  setOrg1
  peer lifecycle chaincode package "$TN/${IOT_CC}.tar.gz" \
    --path $IOT_CC_PATH --lang golang --label ${IOT_CC}_${CC_VER}
else
  warn "${IOT_CC}.tar.gz exists, skipping package."
fi

PKG1=$(installCC 1 "$TN/${IOT_CC}.tar.gz" "${IOT_CC}_${CC_VER}")
PKG2=$(installCC 2 "$TN/${IOT_CC}.tar.gz" "${IOT_CC}_${CC_VER}")
PKG3=$(installCC 3 "$TN/${IOT_CC}.tar.gz" "${IOT_CC}_${CC_VER}")
log "Pkg IDs — Org1: $PKG1 | Org2: $PKG2 | Org3: $PKG3"

approveCC 1 $IOT_CH $IOT_CC 1 "$PKG1"
approveCC 2 $IOT_CH $IOT_CC 1 "$PKG2"
approveCC 3 $IOT_CH $IOT_CC 1 "$PKG3"

log "Checking commit readiness..."
setOrg1
peer lifecycle chaincode checkcommitreadiness \
  --channelID $IOT_CH --name $IOT_CC \
  --version $CC_VER --sequence 1 --output json

log "Committing ${IOT_CC} on ${IOT_CH}..."
setOrg1
peer lifecycle chaincode commit \
  -o $ORDERER --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "$ORDERER_CA" \
  --channelID $IOT_CH --name $IOT_CC \
  --version $CC_VER --sequence 1 \
  --peerAddresses $ORG1_PEER --tlsRootCertFiles "$ORG1_TLS" \
  --peerAddresses $ORG2_PEER --tlsRootCertFiles "$ORG2_TLS" \
  --peerAddresses $ORG3_PEER --tlsRootCertFiles "$ORG3_TLS"

log "${IOT_CC} committed on ${IOT_CH} ✓"

# =============================================================================
# SECURITY-CHANNEL — Org1 + Org2 ONLY
# =============================================================================
log "========== SECURITY-CHANNEL (Org1 + Org2 ONLY) =========="

createChannel $SEC_CH

joinChannel 1 $SEC_CH
joinChannel 2 $SEC_CH
# Org3 intentionally excluded

# Package
if [ ! -f "$TN/${SEC_CC}.tar.gz" ]; then
  log "Packaging ${SEC_CC}..."
  setOrg1
  peer lifecycle chaincode package "$TN/${SEC_CC}.tar.gz" \
    --path $SEC_CC_PATH --lang golang --label ${SEC_CC}_${CC_VER}
else
  warn "${SEC_CC}.tar.gz exists, skipping package."
fi

SPKG1=$(installCC 1 "$TN/${SEC_CC}.tar.gz" "${SEC_CC}_${CC_VER}")
SPKG2=$(installCC 2 "$TN/${SEC_CC}.tar.gz" "${SEC_CC}_${CC_VER}")
# Org3 intentionally excluded

log "Pkg IDs — Org1: $SPKG1 | Org2: $SPKG2"

approveCC 1 $SEC_CH $SEC_CC 1 "$SPKG1"
approveCC 2 $SEC_CH $SEC_CC 1 "$SPKG2"
# Org3 intentionally excluded

log "Checking commit readiness..."
setOrg1
peer lifecycle chaincode checkcommitreadiness \
  --channelID $SEC_CH --name $SEC_CC \
  --version $CC_VER --sequence 1 --output json

log "Committing ${SEC_CC} on ${SEC_CH}..."
setOrg1
peer lifecycle chaincode commit \
  -o $ORDERER --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "$ORDERER_CA" \
  --channelID $SEC_CH --name $SEC_CC \
  --version $CC_VER --sequence 1 \
  --peerAddresses $ORG1_PEER --tlsRootCertFiles "$ORG1_TLS" \
  --peerAddresses $ORG2_PEER --tlsRootCertFiles "$ORG2_TLS"
# Org3 intentionally excluded

log "${SEC_CC} committed on ${SEC_CH} (Org1 + Org2 only) ✓"

# =============================================================================
# VERIFY
# =============================================================================
log "========== CHANNEL MEMBERSHIP =========="

setOrg1
echo "Org1: $(peer channel list 2>/dev/null | grep -v 'Channels peers' | tr '\n' ' ')"
setOrg2
echo "Org2: $(peer channel list 2>/dev/null | grep -v 'Channels peers' | tr '\n' ' ')"
setOrg3
echo "Org3: $(peer channel list 2>/dev/null | grep -v 'Channels peers' | tr '\n' ' ')"

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Done!                                        ${NC}"
echo -e "${GREEN}================================================${NC}"
echo "  iot-channel      → iotcc      (Org1, Org2, Org3)"
echo "  security-channel → securitycc (Org1, Org2 ONLY)"
echo ""