#!/bin/bash

# Usage: ./approve_commit_iotcc.sh <PACKAGE_ID>
# Example: ./approve_commit_iotcc.sh iotcc_1.0:dca162a05fd7beda9cb28177cd4ebf8563b66fd789d2268a0a1aae469b64b272

if [ -z "$1" ]; then
    echo "❌ No package ID provided."
    echo "Usage: ./approve_commit_iotcc.sh <PACKAGE_ID>"
    echo "Get your package ID by running: peer lifecycle chaincode queryinstalled"
    exit 1
fi

CC_PACKAGE_ID=$1

export FABRIC_CFG_PATH=$HOME/testingmultpeers/fabric-samples/config
export PATH=$HOME/testingmultpeers/fabric-samples/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH

NETWORK_DIR=$HOME/testingmultpeers/fabric-samples/test-network
source $NETWORK_DIR/scripts/envVar.sh

ORDERER_CA=$NETWORK_DIR/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem
ORG1_TLS=$NETWORK_DIR/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
ORG2_TLS=$NETWORK_DIR/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt
ORG3_TLS=$NETWORK_DIR/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt

echo "============================================"
echo "  Approving and Committing iotcc"
echo "  Package ID: $CC_PACKAGE_ID"
echo "============================================"

# Approve for Org1
echo ""
echo "[1/3] Approving for Org1..."
setGlobals 1
export CORE_PEER_ADDRESS=localhost:7051
peer lifecycle chaincode approveformyorg \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --channelID mychannel \
    --name iotcc \
    --version 1.0 \
    --package-id $CC_PACKAGE_ID \
    --sequence 1 \
    --tls \
    --cafile $ORDERER_CA
if [ $? -eq 0 ]; then echo "✅ Org1 approved"; else echo "❌ Org1 approval failed"; exit 1; fi

# Approve for Org2
echo ""
echo "[2/3] Approving for Org2..."
setGlobals 2
export CORE_PEER_ADDRESS=localhost:9051
peer lifecycle chaincode approveformyorg \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --channelID mychannel \
    --name iotcc \
    --version 1.0 \
    --package-id $CC_PACKAGE_ID \
    --sequence 1 \
    --tls \
    --cafile $ORDERER_CA
if [ $? -eq 0 ]; then echo "✅ Org2 approved"; else echo "❌ Org2 approval failed"; exit 1; fi

# Approve for Org3
echo ""
echo "[3/3] Approving for Org3..."
setGlobals 3
export CORE_PEER_ADDRESS=localhost:11051
peer lifecycle chaincode approveformyorg \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --channelID mychannel \
    --name iotcc \
    --version 1.0 \
    --package-id $CC_PACKAGE_ID \
    --sequence 1 \
    --tls \
    --cafile $ORDERER_CA
if [ $? -eq 0 ]; then echo "✅ Org3 approved"; else echo "❌ Org3 approval failed"; exit 1; fi

# Check commit readiness
echo ""
echo "============================================"
echo "  Checking commit readiness..."
echo "============================================"
setGlobals 1
peer lifecycle chaincode checkcommitreadiness \
    --channelID mychannel \
    --name iotcc \
    --version 1.0 \
    --sequence 1 \
    --tls \
    --cafile $ORDERER_CA \
    --output json

# Commit
echo ""
echo "============================================"
echo "  Committing chaincode..."
echo "============================================"
setGlobals 1
peer lifecycle chaincode commit \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --channelID mychannel \
    --name iotcc \
    --version 1.0 \
    --sequence 1 \
    --tls \
    --cafile $ORDERER_CA \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS
if [ $? -eq 0 ]; then echo "✅ Chaincode committed"; else echo "❌ Commit failed"; exit 1; fi

# Verify
echo ""
echo "============================================"
echo "  Verifying commit..."
echo "============================================"
peer lifecycle chaincode querycommitted --channelID mychannel --name iotcc

# Quick test
echo ""
echo "============================================"
echo "  Submitting test record..."
echo "============================================"
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"SubmitRecord","Args":["TX001","device-001","edge-cluster-1","abc123hash","confirmed"]}'

sleep 3

echo ""
echo "Querying all records..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetAllRecords","Args":[]}'

echo ""
echo "============================================"
echo "  All done!"
echo "============================================"