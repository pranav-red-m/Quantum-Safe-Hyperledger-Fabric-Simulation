# 🚀 Hyperledger Fabric Setup Guide

This guide walks through setting up the Hyperledger Fabric network, adding the required organizations, deploying the IoT chaincode, and querying the blockchain.

---

## 1️⃣ Start the Hyperledger Fabric Network

Navigate to:

```text
fabric-samples/test-network
```

Start the network and create the channel:

```bash
./network.sh up createChannel
```

---

## 2️⃣ Configure the Environment

Set the required environment variables:

```bash
export PATH=/workspaces/Quantum-Safe-Hyperledger-Fabric-Simulation/fabric-samples/bin:$PATH
export FABRIC_CFG_PATH=/workspaces/Quantum-Safe-Hyperledger-Fabric-Simulation/fabric-samples/config/
source ./scripts/envVar.sh
```

Add peer1.org1 and peer1.org2 to the channel

```bash
./setup.sh
```

Add peer0.org1 to the channel

```bash
cd addOrg3
./addOrg3.sh up
```

Go back to fabric-samples/test-network

```bash
cd ..
```

---

## 3️⃣ Install IoT Chaincode

```bash
./install-iotcc.sh
```

---

## 4️⃣ Deploy the IoT Chaincode with 2/3 approval
Note: Use the package ID provided after running ./install-iotcc.sh

```bash
./deploy-iotcc.sh [PKG_ID]
```


## 5️⃣ Add Organization 3

Open **another terminal**.

Navigate to:

```text
fabric-samples/test-network/addOrg3
```

Run:

```bash
./addOrg3.sh up
```

At this point, the network should consist of:

* ✅ 5 Peers
* ✅ 1 Ordering Service Node
* ✅ 3 Organizations

---

## 6️⃣ Install the IoT Chaincode

Return to the previous directory (`iot-channel`) and install the chaincode:

```bash
./install-iotcc.sh
```

---

## 7️⃣ Deploy the Chaincode

Deploy using the package ID produced by the installation script:

```bash
./deploy-iotcc iot1.0:[PACKAGE ID GIVEN BY INSTALL IOTCC SHELL FILE]
```

This deploys the chaincode with a **2/3 organization consensus policy**.

The blockchain prototype is now fully deployed.

---

# 🛠 Troubleshooting

If any issues occur, begin by checking the Docker logs.

### TLS / MSP Certificate Errors

If persistent TLS or MSP certificate issues occur, completely reset the Fabric network using the following commands:

```bash
./network.sh down

docker rm -f $(docker ps -aq) 2>/dev/null

docker volume prune -f

docker volume ls | grep -E "peer|orderer" | awk '{print $2}' | xargs docker volume rm 2>/dev/null

rm -rf organizations/peerOrganizations
rm -rf organizations/ordererOrganizations
rm -rf channel-artifacts/

./network.sh up
```

---

