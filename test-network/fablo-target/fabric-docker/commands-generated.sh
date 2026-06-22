#!/usr/bin/env bash

generateArtifacts() {
  printHeadline "Generating basic configs" "U1F913"

  printItalics "Generating crypto material for Orderer" "U1F512"
  certsGenerate "$FABLO_NETWORK_ROOT/fabric-config" "crypto-config-orderer.yaml" "peerOrganizations/orderer.example.com" "$FABLO_NETWORK_ROOT/fabric-config/crypto-config/"

  printItalics "Generating crypto material for Org1" "U1F512"
  certsGenerate "$FABLO_NETWORK_ROOT/fabric-config" "crypto-config-org1.yaml" "peerOrganizations/org1.example.com" "$FABLO_NETWORK_ROOT/fabric-config/crypto-config/"

  printItalics "Generating crypto material for Org2" "U1F512"
  certsGenerate "$FABLO_NETWORK_ROOT/fabric-config" "crypto-config-org2.yaml" "peerOrganizations/org2.example.com" "$FABLO_NETWORK_ROOT/fabric-config/crypto-config/"

  printItalics "Generating crypto material for Org3" "U1F512"
  certsGenerate "$FABLO_NETWORK_ROOT/fabric-config" "crypto-config-org3.yaml" "peerOrganizations/org3.example.com" "$FABLO_NETWORK_ROOT/fabric-config/crypto-config/"

  # Create directories to avoid permission errors on linux
  mkdir -p "$FABLO_NETWORK_ROOT/fabric-config/chaincode-packages"
  mkdir -p "$FABLO_NETWORK_ROOT/fabric-config/config"
}

startNetwork() {
  printHeadline "Starting network" "U1F680"
  (cd "$FABLO_NETWORK_ROOT"/fabric-docker && docker compose up -d)
  sleep 4
}

generateChannelsArtifacts() {
  printHeadline "Generating config for 'my-channel1'" "U1F913"
  createChannelTx "my-channel1" "$FABLO_NETWORK_ROOT/fabric-config" "MyChannel1" "$FABLO_NETWORK_ROOT/fabric-config/config"
}

installChannels() {
  docker exec -i cli.orderer.example.com bash -c "source scripts/channel_fns.sh; createChannelAndJoinTls 'my-channel1' 'OrdererMSP' 'orderer0.group1.orderer.example.com:7053' 'crypto/users/Admin@orderer.example.com/tls/client.crt' 'crypto/users/Admin@orderer.example.com/tls/client.key' 'crypto-orderer/tlsca.orderer.example.com-cert.pem';"
  printHeadline "Creating 'my-channel1' on Org1/peer0" "U1F63B"
  docker exec -i cli.org1.example.com bash -c "source scripts/channel_fns.sh; fetchChannelAndJoinTls 'my-channel1' 'Org1MSP' 'peer0.org1.example.com:7041' 'crypto/users/Admin@org1.example.com/msp' 'crypto/users/Admin@org1.example.com/tls' 'crypto-orderer/tlsca.orderer.example.com-cert.pem' 'orderer0.group1.orderer.example.com:7030';"

  printItalics "Joining 'my-channel1' on Org2/peer0" "U1F638"
  docker exec -i cli.org2.example.com bash -c "source scripts/channel_fns.sh; fetchChannelAndJoinTls 'my-channel1' 'Org2MSP' 'peer0.org2.example.com:7061' 'crypto/users/Admin@org2.example.com/msp' 'crypto/users/Admin@org2.example.com/tls' 'crypto-orderer/tlsca.orderer.example.com-cert.pem' 'orderer0.group1.orderer.example.com:7030';"
  printItalics "Joining 'my-channel1' on Org3/peer0" "U1F638"
  docker exec -i cli.org3.example.com bash -c "source scripts/channel_fns.sh; fetchChannelAndJoinTls 'my-channel1' 'Org3MSP' 'peer0.org3.example.com:7081' 'crypto/users/Admin@org3.example.com/msp' 'crypto/users/Admin@org3.example.com/tls' 'crypto-orderer/tlsca.orderer.example.com-cert.pem' 'orderer0.group1.orderer.example.com:7030';"

}

installChaincodes() {
  if [ -n "$(ls "$CHAINCODES_BASE_DIR/../event-ledger")" ]; then
    local version="1.0"
    printHeadline "Packaging chaincode 'eventcc'" "U1F60E"
    chaincodeBuild "eventcc" "golang" "$CHAINCODES_BASE_DIR/../event-ledger" "16"
    chaincodePackage "cli.org1.example.com" "peer0.org1.example.com:7041" "eventcc" "$version" "golang" "my-channel1"
    printHeadline "Installing 'eventcc' for Org1" "U1F60E"
    chaincodeInstall "cli.org1.example.com" "peer0.org1.example.com:7041" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
    chaincodeApprove "cli.org1.example.com" "peer0.org1.example.com:7041" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
    printHeadline "Installing 'eventcc' for Org2" "U1F60E"
    chaincodeInstall "cli.org2.example.com" "peer0.org2.example.com:7061" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
    chaincodeApprove "cli.org2.example.com" "peer0.org2.example.com:7061" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
    printHeadline "Installing 'eventcc' for Org3" "U1F60E"
    chaincodeInstall "cli.org3.example.com" "peer0.org3.example.com:7081" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
    chaincodeApprove "cli.org3.example.com" "peer0.org3.example.com:7081" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
    printItalics "Committing chaincode 'eventcc' on channel 'my-channel1' as 'Org1'" "U1F618"
    chaincodeCommit "cli.org1.example.com" "peer0.org1.example.com:7041" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "peer0.org1.example.com:7041,peer0.org2.example.com:7061,peer0.org3.example.com:7081" "crypto-peer/peer0.org1.example.com/tls/ca.crt,crypto-peer/peer0.org2.example.com/tls/ca.crt,crypto-peer/peer0.org3.example.com/tls/ca.crt" ""
  else
    echo "Warning! Skipping chaincode 'eventcc' installation. Chaincode directory is empty."
    echo "Looked in dir: '$CHAINCODES_BASE_DIR/../event-ledger'"
  fi

}

installChaincode() {
  local chaincodeName="$1"
  if [ -z "$chaincodeName" ]; then
    echo "Error: chaincode name is not provided"
    exit 1
  fi

  local version="$2"
  if [ -z "$version" ]; then
    echo "Error: chaincode version is not provided"
    exit 1
  fi

  if [ "$chaincodeName" = "eventcc" ]; then
    if [ -n "$(ls "$CHAINCODES_BASE_DIR/../event-ledger")" ]; then
      printHeadline "Packaging chaincode 'eventcc'" "U1F60E"
      chaincodeBuild "eventcc" "golang" "$CHAINCODES_BASE_DIR/../event-ledger" "16"
      chaincodePackage "cli.org1.example.com" "peer0.org1.example.com:7041" "eventcc" "$version" "golang" "my-channel1"
      printHeadline "Installing 'eventcc' for Org1" "U1F60E"
      chaincodeInstall "cli.org1.example.com" "peer0.org1.example.com:7041" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
      chaincodeApprove "cli.org1.example.com" "peer0.org1.example.com:7041" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
      printHeadline "Installing 'eventcc' for Org2" "U1F60E"
      chaincodeInstall "cli.org2.example.com" "peer0.org2.example.com:7061" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
      chaincodeApprove "cli.org2.example.com" "peer0.org2.example.com:7061" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
      printHeadline "Installing 'eventcc' for Org3" "U1F60E"
      chaincodeInstall "cli.org3.example.com" "peer0.org3.example.com:7081" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
      chaincodeApprove "cli.org3.example.com" "peer0.org3.example.com:7081" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
      printItalics "Committing chaincode 'eventcc' on channel 'my-channel1' as 'Org1'" "U1F618"
      chaincodeCommit "cli.org1.example.com" "peer0.org1.example.com:7041" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "peer0.org1.example.com:7041,peer0.org2.example.com:7061,peer0.org3.example.com:7081" "crypto-peer/peer0.org1.example.com/tls/ca.crt,crypto-peer/peer0.org2.example.com/tls/ca.crt,crypto-peer/peer0.org3.example.com/tls/ca.crt" ""

    else
      echo "Warning! Skipping chaincode 'eventcc' install. Chaincode directory is empty."
      echo "Looked in dir: '$CHAINCODES_BASE_DIR/../event-ledger'"
    fi
  fi
}

runDevModeChaincode() {
  echo "Running chaincode in dev mode is supported by Fablo only for V2 channel capabilities"
  exit 1
}

upgradeChaincode() {
  local chaincodeName="$1"
  if [ -z "$chaincodeName" ]; then
    echo "Error: chaincode name is not provided"
    exit 1
  fi

  local version="$2"
  if [ -z "$version" ]; then
    echo "Error: chaincode version is not provided"
    exit 1
  fi

  if [ "$chaincodeName" = "eventcc" ]; then
    if [ -n "$(ls "$CHAINCODES_BASE_DIR/../event-ledger")" ]; then
      printHeadline "Packaging chaincode 'eventcc'" "U1F60E"
      chaincodeBuild "eventcc" "golang" "$CHAINCODES_BASE_DIR/../event-ledger" "16"
      chaincodePackage "cli.org1.example.com" "peer0.org1.example.com:7041" "eventcc" "$version" "golang" "my-channel1"
      printHeadline "Installing 'eventcc' for Org1" "U1F60E"
      chaincodeInstall "cli.org1.example.com" "peer0.org1.example.com:7041" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
      chaincodeApprove "cli.org1.example.com" "peer0.org1.example.com:7041" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
      printHeadline "Installing 'eventcc' for Org2" "U1F60E"
      chaincodeInstall "cli.org2.example.com" "peer0.org2.example.com:7061" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
      chaincodeApprove "cli.org2.example.com" "peer0.org2.example.com:7061" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
      printHeadline "Installing 'eventcc' for Org3" "U1F60E"
      chaincodeInstall "cli.org3.example.com" "peer0.org3.example.com:7081" "eventcc" "$version" "my-channel1" "crypto-orderer/tlsca.orderer.example.com-cert.pem"
      chaincodeApprove "cli.org3.example.com" "peer0.org3.example.com:7081" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "" "golang" ""
      printItalics "Committing chaincode 'eventcc' on channel 'my-channel1' as 'Org1'" "U1F618"
      chaincodeCommit "cli.org1.example.com" "peer0.org1.example.com:7041" "my-channel1" "eventcc" "$version" "orderer0.group1.orderer.example.com:7030" "AND ('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member')" "" "crypto-orderer/tlsca.orderer.example.com-cert.pem" "peer0.org1.example.com:7041,peer0.org2.example.com:7061,peer0.org3.example.com:7081" "crypto-peer/peer0.org1.example.com/tls/ca.crt,crypto-peer/peer0.org2.example.com/tls/ca.crt,crypto-peer/peer0.org3.example.com/tls/ca.crt" ""

    else
      echo "Warning! Skipping chaincode 'eventcc' upgrade. Chaincode directory is empty."
      echo "Looked in dir: '$CHAINCODES_BASE_DIR/../event-ledger'"
    fi
  fi
}

notifyOrgsAboutChannels() {

  echo ""

}

printStartSuccessInfo() {
  printHeadline "Done! Enjoy your fresh network" "U1F984"
}

stopNetwork() {
  printHeadline "Stopping network" "U1F68F"
  (cd "$FABLO_NETWORK_ROOT"/fabric-docker && docker compose stop)
  sleep 4
}

networkDown() {
  printf "Removing chaincode containers & images... \U1F5D1 \n"
  for container in $(docker ps -a | grep "peer0.org1.example.com.*eventcc" | awk '{print $1}'); do
    echo "Removing container $container..."
    docker rm -f "$container" || echo "docker rm of $container failed. Check if all fabric dockers properly was deleted"
  done
  for image in $(docker images "peer0.org1.example.com.*eventcc*" -q); do
    echo "Removing image $image..."
    docker rmi "$image" || echo "docker rmi of $image failed. Check if all fabric dockers properly was deleted"
  done
  for container in $(docker ps -a | grep "peer0.org2.example.com.*eventcc" | awk '{print $1}'); do
    echo "Removing container $container..."
    docker rm -f "$container" || echo "docker rm of $container failed. Check if all fabric dockers properly was deleted"
  done
  for image in $(docker images "peer0.org2.example.com.*eventcc*" -q); do
    echo "Removing image $image..."
    docker rmi "$image" || echo "docker rmi of $image failed. Check if all fabric dockers properly was deleted"
  done
  for container in $(docker ps -a | grep "peer0.org3.example.com.*eventcc" | awk '{print $1}'); do
    echo "Removing container $container..."
    docker rm -f "$container" || echo "docker rm of $container failed. Check if all fabric dockers properly was deleted"
  done
  for image in $(docker images "peer0.org3.example.com.*eventcc*" -q); do
    echo "Removing image $image..."
    docker rmi "$image" || echo "docker rmi of $image failed. Check if all fabric dockers properly was deleted"
  done

  printHeadline "Destroying network" "U1F916"
  (cd "$FABLO_NETWORK_ROOT"/fabric-docker && docker compose down)

  printf "Removing generated configs... \U1F5D1 \n"
  rm -rf "$FABLO_NETWORK_ROOT/fabric-config/config"
  rm -rf "$FABLO_NETWORK_ROOT/fabric-config/crypto-config"
  rm -rf "$FABLO_NETWORK_ROOT/fabric-config/chaincode-packages"

  printHeadline "Done! Network was purged" "U1F5D1"
}
