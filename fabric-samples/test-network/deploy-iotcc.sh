#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: ./deploy_iotcc.sh <PACKAGE_ID>"
    echo "Get your package ID from: peer lifecycle chaincode queryinstalled"
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
echo "  Approving iotcc v1.0 with 2/3 Endorsement"
echo "  Package ID: $CC_PACKAGE_ID"
echo "============================================"

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
    --signature-policy "OutOf(2, 'Org1MSP.peer', 'Org2MSP.peer', 'Org3MSP.peer')" \
    --tls \
    --cafile $ORDERER_CA
if [ $? -eq 0 ]; then echo "✅ Org1 approved"; else echo "❌ Org1 failed"; exit 1; fi

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
    --signature-policy "OutOf(2, 'Org1MSP.peer', 'Org2MSP.peer', 'Org3MSP.peer')" \
    --tls \
    --cafile $ORDERER_CA
if [ $? -eq 0 ]; then echo "✅ Org2 approved"; else echo "❌ Org2 failed"; exit 1; fi

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
    --signature-policy "OutOf(2, 'Org1MSP.peer', 'Org2MSP.peer', 'Org3MSP.peer')" \
    --tls \
    --cafile $ORDERER_CA
if [ $? -eq 0 ]; then echo "✅ Org3 approved"; else echo "❌ Org3 failed"; exit 1; fi

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
    --signature-policy "OutOf(2, 'Org1MSP.peer', 'Org2MSP.peer', 'Org3MSP.peer')" \
    --tls \
    --cafile $ORDERER_CA \
    --output json

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
    --signature-policy "OutOf(2, 'Org1MSP.peer', 'Org2MSP.peer', 'Org3MSP.peer')" \
    --tls \
    --cafile $ORDERER_CA \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS
if [ $? -eq 0 ]; then echo "✅ Committed successfully"; else echo "❌ Commit failed"; exit 1; fi

echo ""
echo "============================================"
echo "  Verifying..."
echo "============================================"
peer lifecycle chaincode querycommitted --channelID mychannel --name iotcc

sleep 3

echo ""
echo "Initializing ledger..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"InitLedger","Args":[]}'

echo "============================================"
echo "  Partial block -> Full block smoke test"
echo "============================================"

sleep 3

echo "Submitting partial block..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"SubmitPartialBlock","Args":["PB001","edge-cluster-1","deadbeef","cafebabe","feedface","edge-cluster-1","device-001"]}'

sleep 3

echo ""
echo "Finalizing full block from partial block..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"FinalizeFullBlock","Args":["FB001","PB001","123456","true"]}'

sleep 3

echo ""
echo "Querying full block..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetFullBlock","Args":["FB001"]}'

echo ""
echo "Committing full block..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"CommitFullBlock","Args":["FB001"]}'

sleep 3

echo ""
echo "Querying chain meta (should show updated tip + height)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetChainMeta","Args":[]}'

echo ""
echo "============================================"
echo "  Done!"
echo "============================================"