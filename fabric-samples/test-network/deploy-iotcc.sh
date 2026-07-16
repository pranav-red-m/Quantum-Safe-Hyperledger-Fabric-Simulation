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
echo "  Verifying commit..."
echo "============================================"
peer lifecycle chaincode querycommitted --channelID mychannel --name iotcc
 
echo ""
echo "  Waiting for chaincode container to come up..."
sleep 8
 
echo ""
echo "  Checking chaincode container status (informational only)..."
docker ps -a --filter "name=iotcc" --format "{{.ID}}  {{.Names}}  {{.Status}}" 2>/dev/null || \
    echo "  (docker CLI not available in this shell / different host from peers -- skip)"
 
echo ""
echo "============================================"
echo "  InitLedger"
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
    -c '{"function":"InitLedger","Args":[]}'
INIT_STATUS=$?
if [ $INIT_STATUS -ne 0 ]; then
    echo ""
    echo "❌ InitLedger failed. This usually means the chaincode container failed to start."
    echo "   Run: docker ps -a --filter \"name=iotcc\""
    echo "   Then: docker logs <container_id>"
    echo "   Aborting rest of smoke test."
    exit 1
fi
 
sleep 3
 
echo ""
echo "Querying chain meta (expect height 0, tip GENESIS)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetChainMeta","Args":[]}'
 
echo ""
echo "============================================"
echo "  Partial block -> Full block smoke test"
echo "============================================"
 
echo ""
echo "Submitting partial block PB001..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"SubmitPartialBlock","Args":["PB001","owner-001","deadbeef","cafebabe","feedface","edge-cluster-1","device-001"]}'
 
sleep 3
 
echo ""
echo "Querying PB001 (expect status PENDING)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetPartialBlock","Args":["PB001"]}'
 
echo ""
echo "Attempting duplicate SubmitPartialBlock for PB001 (should FAIL)..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"SubmitPartialBlock","Args":["PB001","owner-001","deadbeef","cafebabe","feedface","edge-cluster-1","device-001"]}' \
    || echo "(expected failure above - PB001 already exists)"
 
sleep 3
 
echo ""
echo "Finalizing full block FB001 from PB001 (signatureVerified=true)..."
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
echo "Querying full block FB001 (expect ConsensusStatus=PROPOSED, Hash empty)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetFullBlock","Args":["FB001"]}'
 
echo ""
echo "Querying PB001 again (expect status SEALED, fullBlockId=FB001)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetPartialBlock","Args":["PB001"]}'
 
echo ""
echo "Attempting to finalize PB001 again into FB999 (should FAIL - already sealed)..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"FinalizeFullBlock","Args":["FB999","PB001","111111","true"]}' \
    || echo "(expected failure above - PB001 already sealed)"
 
sleep 3
 
echo ""
echo "============================================"
echo "  Consensus / commit"
echo "============================================"
 
echo ""
echo "Committing full block FB001..."
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
echo "Querying full block FB001 (expect ConsensusStatus=COMMITTED, Hash set, PreviousHash=genesis)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetFullBlock","Args":["FB001"]}'
 
echo ""
echo "Querying chain meta (expect height 1, tip FB001)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetChainMeta","Args":[]}'
 
echo ""
echo "Attempting to commit FB001 again (should FAIL - already committed)..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"CommitFullBlock","Args":["FB001"]}' \
    || echo "(expected failure above - FB001 already committed)"
 
sleep 3
 
echo ""
echo "============================================"
echo "  Reject-path smoke test (separate block)"
echo "============================================"
 
echo ""
echo "Submitting partial block PB002..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"SubmitPartialBlock","Args":["PB002","owner-002","deadbeef02","cafebabe02","feedface02","edge-cluster-2","device-002"]}'
 
sleep 3
 
echo ""
echo "Finalizing full block FB002 from PB002..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"FinalizeFullBlock","Args":["FB002","PB002","222222","true"]}'
 
sleep 3
 
echo ""
echo "Rejecting FB002..."
peer chaincode invoke \
    -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls \
    --cafile $ORDERER_CA \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles $ORG1_TLS \
    --peerAddresses localhost:9051 --tlsRootCertFiles $ORG2_TLS \
    --peerAddresses localhost:11051 --tlsRootCertFiles $ORG3_TLS \
    -c '{"function":"RejectFullBlock","Args":["FB002"]}'
 
sleep 3
 
echo ""
echo "Querying FB002 (expect ConsensusStatus=REJECTED)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetFullBlock","Args":["FB002"]}'
 
echo ""
echo "Chain meta should be unaffected by rejection (still height 1, tip FB001)..."
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetChainMeta","Args":[]}'
 
echo ""
echo "============================================"
echo "  Final: list all full blocks"
echo "============================================"
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetAllFullBlocks","Args":[]}'
 
echo ""
echo "============================================"
echo "  Done!"
echo "============================================"
 