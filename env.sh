export PATH="/home/pranav/thisbetterwork/fabric-samples/bin:$PATH"
export FABRIC_CFG_PATH="/home/pranav/thisbetterwork/fabric-samples/config/"
export ORDERER_CA="/home/pranav/thisbetterwork/fabric-samples/test-network/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem"
export TEST_NETWORK="/home/pranav/thisbetterwork/fabric-samples/test-network"
export CHANNEL_NAME="mychannel"
export CC_NAME="eventcc"

setOrg1() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org1MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="/home/pranav/thisbetterwork/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="/home/pranav/thisbetterwork/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
  export CORE_PEER_ADDRESS="localhost:7051"
  echo "Switched to Org1"
}

setOrg2() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org2MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="/home/pranav/thisbetterwork/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="/home/pranav/thisbetterwork/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
  export CORE_PEER_ADDRESS="localhost:9051"
  echo "Switched to Org2"
}

setOrg3() {
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="Org3MSP"
  export CORE_PEER_TLS_ROOTCERT_FILE="/home/pranav/thisbetterwork/fabric-samples/test-network/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="/home/pranav/thisbetterwork/fabric-samples/test-network/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp"
  export CORE_PEER_ADDRESS="localhost:11051"
  echo "Switched to Org3"
}
