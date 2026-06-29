- **3 Organisations** — Org1, Org2, Org3
- **5 Peers** — Org1 (peer0:7051, peer1:8051), Org2 (peer0:9051, peer1:10051), Org3 (peer0:11051)
- **1 Channel** — `mychannel`
- **Endorsement Policy** — 2 of 3 organisations must endorse every transaction
- **Chaincode** — `iotcc` (Go) deployed on all peers

---

## Prerequisites

- Docker Desktop running
- WSL2 (Ubuntu) or Linux
- Hyperledger Fabric binaries in `~/testingmultpeers/fabric-samples/bin`
- Python 3 (for benchmarking and IDS bridge)

---

## Quick Start

**1. Start the network:**
```bash
cd test-network
./network.sh up createChannel -ca
```

**2. Add Org3:**
```bash
cd addOrg3
./addOrg3.sh up -c mychannel
cd ..
```

**3. Install chaincode on all peers:**
```bash
./install_iotcc.sh
```

**4. Deploy with 2/3 endorsement policy:**
```bash
./deploy_iotcc.sh <PACKAGE_ID>
```

Get your package ID from:
```bash
setGlobals 1
peer lifecycle chaincode queryinstalled
```

**5. Verify deployment:**
```bash
peer lifecycle chaincode querycommitted --channelID mychannel --name iotcc
```

---

## Environment Setup

Always run before any peer command:
```bash
source ~/testingmultpeers/fabric-samples/test-network/scripts/envVar.sh
export FABRIC_CFG_PATH=$HOME/testingmultpeers/fabric-samples/config
export PATH=$HOME/testingmultpeers/fabric-samples/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH
```

Switch between peers:
```bash
setGlobals 1 && export CORE_PEER_ADDRESS=localhost:7051   # Org1 peer0
setGlobals 1 && export CORE_PEER_ADDRESS=localhost:8051   # Org1 peer1
setGlobals 2 && export CORE_PEER_ADDRESS=localhost:9051   # Org2 peer0
setGlobals 2 && export CORE_PEER_ADDRESS=localhost:10051  # Org2 peer1
setGlobals 3 && export CORE_PEER_ADDRESS=localhost:11051  # Org3 peer0
```

---

## Chaincode — iotcc

Located at `iot-channel/chaincode-go/chaincode/smartcontract.go`

### Data Layer
| Function | Description |
|----------|-------------|
| `SubmitRecord` | Submit a single IoT record — checks device is registered before writing |
| `SubmitBatch` | Submit multiple IoT records in one transaction (edge node batching) |
| `GetRecord` | Retrieve a single record by transaction ID |
| `GetAllRecords` | Retrieve all records on the ledger |
| `VerifyHash` | Verify a record's data hash has not been tampered with |
| `GetRecordHistory` | Full immutable audit trail of every state change to a record |

### Access Control
| Function | Description |
|----------|-------------|
| `RegisterDevice` | Register an IoT device on-chain — unregistered devices are rejected |
| `DeactivateDevice` | Deactivate a malicious device — called by IDS when anomaly detected |
| `GetDevice` | Query a registered device by ID |
| `GetAllDevices` | List all registered devices |

### Security / IDS Integration
| Function | Description |
|----------|-------------|
| `RaiseAlert` | IDS writes anomaly alert immutably on-chain, auto-flags the record |
| `GetAlertsForDevice` | Query all alerts raised for a specific device |

### Governance
| Function | Description |
|----------|-------------|
| `UpdateRecordStatus` | Enforces state machine: `confirmed → validated → approved/flagged → resolved → archived` |
| `ChallengeRecord` | Any org can dispute another org's record — permanently on-chain, cannot be deleted |
| `ResolveChallenge` | Close a dispute with a resolution |
| `GetChallengesForRecord` | Get all challenges raised against a specific record |
| `GetAllChallenges` | Full audit trail of all disputes across all records |

---

## Scripts

| Script | Usage | Description |
|--------|-------|-------------|
| `install_iotcc.sh` | `./install_iotcc.sh` | Packages and installs chaincode on all 5 peers |
| `deploy_iotcc.sh` | `./deploy_iotcc.sh <PACKAGE_ID>` | Approves for all 3 orgs and commits with 2/3 endorsement policy |

---

## IDS Integration

The AI-driven Isolation Forest IDS connects to the blockchain via `fabric_bridge.py`.

Drop `fabric_bridge.py` next to your IDS Python code and import:

```python
from fabric_bridge import submit_record, submit_batch, raise_alert

# Normal flow — edge node batches IoT records
submit_batch([
    {"txId": "TX001", "deviceId": "dev-001", "edgeCluster": "edge-1", "dataHash": "abc123", "status": "confirmed"},
    {"txId": "TX002", "deviceId": "dev-002", "edgeCluster": "edge-1", "dataHash": "def456", "status": "confirmed"},
])

# IDS detects anomaly — raise alert on blockchain
raise_alert(
    device_id="dev-003",
    tx_id="TX003",
    severity="HIGH",
    description=f"Isolation Forest anomaly score: 0.87",
    flagged_by="edge-cluster-1"
)
```

---

## Benchmarking

Run from `test-network` directory:

```bash
# Basic tests — single latency, query latency, concurrent load
python3 benchmark.py

# Full tests — includes batch, alerts, state machine, challenges, device registry, history
python3 benchmark.py --full
```

### Benchmark Results Summary

| Test | Result |
|------|--------|
| Single record latency (mean) | 2088.09 ms |
| Query latency — GetRecord (mean) | 44.57 ms |
| Query latency — GetAllRecords (mean) | 48.14 ms |
| Throughput — 10 devices | 65.19 tx/s |
| Throughput — 50 devices | 84.48 tx/s |
| Throughput — 100 devices | 84.25 tx/s |
| Batch vs single speedup (10 records) | 9.97x |
| Alert write latency (mean) | 2093.64 ms |
| State machine transitions | 10/10 ✅ |
| Invalid transition rejection | ✅ Correctly rejected |
| Cross-org challenge | 10/10 ✅ |
| Unregistered device rejection | ✅ Correctly rejected |

---

## End-to-End Test

Test the full flow — IoT data → edge → IDS → blockchain:

```bash
# 1. Register a device
peer chaincode invoke ... -c '{"function":"RegisterDevice","Args":["dev-001","temperature-sensor","edge-1","Org1MSP"]}'

# 2. Submit IoT data
peer chaincode invoke ... -c '{"function":"SubmitRecord","Args":["TX001","dev-001","edge-1","abc123hash","confirmed"]}'

# 3. IDS flags it — raise alert
peer chaincode invoke ... -c '{"function":"RaiseAlert","Args":["ALERT001","TX001","dev-001","HIGH","Anomaly detected","edge-1"]}'

# 4. Check record is now flagged
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetRecord","Args":["TX001"]}'

# 5. Challenge from another org
peer chaincode invoke ... -c '{"function":"ChallengeRecord","Args":["CH001","TX001","Reading inconsistent with cluster baseline"]}'

# 6. View full history
peer chaincode query -C mychannel -n iotcc -c '{"function":"GetRecordHistory","Args":["TX001"]}'
```

---

## Project Structure
