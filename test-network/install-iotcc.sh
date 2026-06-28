#!/bin/bash

export FABRIC_CFG_PATH=$HOME/testingmultpeers/fabric-samples/config
export PATH=$HOME/testingmultpeers/fabric-samples/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH

NETWORK_DIR=$HOME/testingmultpeers/fabric-samples/test-network
CHAINCODE_PKG=$NETWORK_DIR/iotcc.tar.gz

source $NETWORK_DIR/scripts/envVar.sh

echo "============================================"
echo "  IoT Chaincode Installation Script"
echo "============================================"

# Check package exists
if [ ! -f "$CHAINCODE_PKG" ]; then
    echo "❌ iotcc.tar.gz not found. Packaging first..."
    peer lifecycle chaincode package $CHAINCODE_PKG \
        --path $HOME/testingmultpeers/fabric-samples/iot-channel/chaincode-go \
        --lang golang \
        --label iotcc_1.0
    if [ $? -ne 0 ]; then
        echo "❌ Packaging failed. Exiting."
        exit 1
    fi
    echo "✅ Packaged successfully"
else
    echo "✅ Found existing package: $CHAINCODE_PKG"
fi

echo ""

# Install on Org1 peer0
echo "[1/5] Installing on Org1 peer0 (7051)..."
setGlobals 1
export CORE_PEER_ADDRESS=localhost:7051
peer lifecycle chaincode install $CHAINCODE_PKG
if [ $? -eq 0 ]; then echo "✅ Org1 peer0 done"; else echo "❌ Org1 peer0 failed"; fi

echo ""

# Install on Org1 peer1
echo "[2/5] Installing on Org1 peer1 (8051)..."
setGlobals 1
export CORE_PEER_ADDRESS=localhost:8051
peer lifecycle chaincode install $CHAINCODE_PKG
if [ $? -eq 0 ]; then echo "✅ Org1 peer1 done"; else echo "❌ Org1 peer1 failed"; fi

echo ""

# Install on Org2 peer0
echo "[3/5] Installing on Org2 peer0 (9051)..."
setGlobals 2
export CORE_PEER_ADDRESS=localhost:9051
peer lifecycle chaincode install $CHAINCODE_PKG
if [ $? -eq 0 ]; then echo "✅ Org2 peer0 done"; else echo "❌ Org2 peer0 failed"; fi

echo ""

# Install on Org2 peer1
echo "[4/5] Installing on Org2 peer1 (10051)..."
setGlobals 2
export CORE_PEER_ADDRESS=localhost:10051
peer lifecycle chaincode install $CHAINCODE_PKG
if [ $? -eq 0 ]; then echo "✅ Org2 peer1 done"; else echo "❌ Org2 peer1 failed"; fi

echo ""

# Install on Org3 peer0
echo "[5/5] Installing on Org3 peer0 (11051)..."
setGlobals 3
export CORE_PEER_ADDRESS=localhost:11051
peer lifecycle chaincode install $CHAINCODE_PKG
if [ $? -eq 0 ]; then echo "✅ Org3 peer0 done"; else echo "❌ Org3 peer0 failed"; fi

echo ""
echo "============================================"
echo "  Verifying installations..."
echo "============================================"

echo ""
echo "--- Org1 peer0 (7051) ---"
setGlobals 1
export CORE_PEER_ADDRESS=localhost:7051
peer lifecycle chaincode queryinstalled

echo ""
echo "--- Org1 peer1 (8051) ---"
export CORE_PEER_ADDRESS=localhost:8051
peer lifecycle chaincode queryinstalled

echo ""
echo "--- Org2 peer0 (9051) ---"
setGlobals 2
export CORE_PEER_ADDRESS=localhost:9051
peer lifecycle chaincode queryinstalled

echo ""
echo "--- Org2 peer1 (10051) ---"
export CORE_PEER_ADDRESS=localhost:10051
peer lifecycle chaincode queryinstalled

echo ""
echo "--- Org3 peer0 (11051) ---"
setGlobals 3
export CORE_PEER_ADDRESS=localhost:11051
peer lifecycle chaincode queryinstalled

echo ""
echo "============================================"
echo "  Installation complete!"
echo "  Next: approve and commit the chaincode"
echo "============================================"