#!/bin/bash
set -e

# Run this from ~/testingmultpeers/fabric-samples/test-network
# Make sure ORDERER_CA and other test-network env vars are already exported
# (source the usual setOrgEnv / export block you use before invoking manually)

NUM_WORKERS=10
EDGE_CLUSTER="edge-cluster-1"
ORG_MSP="Org1MSP"
DEVICE_TYPE="gps-sensor"

for i in $(seq 0 $((NUM_WORKERS - 1))); do
  DEVICE_ID="bench-caliper-device-${i}"
  echo "=== Registering ${DEVICE_ID} ==="

  peer chaincode invoke -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls --cafile "$ORDERER_CA" \
    -C mychannel -n iotcc \
    --peerAddresses localhost:7051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt" \
    --peerAddresses localhost:9051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt" \
    -c "{\"function\":\"RegisterDevice\",\"Args\":[\"${DEVICE_ID}\",\"${DEVICE_TYPE}\",\"${EDGE_CLUSTER}\",\"${ORG_MSP}\"]}"
done

echo "Done registering ${NUM_WORKERS} devices."