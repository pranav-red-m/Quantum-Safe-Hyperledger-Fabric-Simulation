import subprocess
from datetime import datetime
import random
import time
import os
import sys
import hashlib
import json

BLOCK_SIZE   = 10
EVENT_BUFFER = []
BLOCK_NUMBER = 1
PREV_HASH    = "GENESIS"

#Network config (Cahnge if org/peers ports change)
ORDERER_ADDRESS  = "orderer0.group1.orderer.example.com:7030"
ORDERER_HOSTNAME = "orderer0.group1.orderer.example.com"
CHANNEL          = "my-channel1"
CHAINCODE        = "eventcc"
ORG1_PEER        = "peer0.org1.example.com:7041"
ORG2_PEER        = "peer0.org2.example.com:7061"
 
FABLO_CRYPTO = os.path.join(os.getcwd(), "fablo-target/fabric-config/crypto-config/peerOrganizations")

required_vars = ["ORDERER_CA", "ORG1_CA", "ORG2_CA"]
missing = [var for var in required_vars if var not in os.environ]
if missing:
    print("\nERROR: Fabric environment variables are not initialized.")
    print("Missing variables:", ", ".join(missing))
    print("\nRun the following commands before starting this script:\n")
    print(f"export ORDERER_CA=${{PWD}}/fablo-target/fabric-config/crypto-config/peerOrganizations/orderer.example.com/tlsca/tlsca.orderer.example.com-cert.pem")
    print(f"export ORG1_CA=${{PWD}}/fablo-target/fabric-config/crypto-config/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem")
    print(f"export ORG2_CA=${{PWD}}/fablo-target/fabric-config/crypto-config/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem")
    print(f"\nexport CORE_PEER_TLS_ENABLED=true")
    print(f"export CORE_PEER_LOCALMSPID=Org1MSP")
    print(f"export CORE_PEER_ADDRESS=localhost:7041")
    print(f"export CORE_PEER_MSPCONFIGPATH=${{PWD}}/fablo-target/fabric-config/crypto-config/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp")
    print(f"export CORE_PEER_TLS_ROOTCERT_FILE=${{PWD}}/fablo-target/fabric-config/crypto-config/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem")
    sys.exit(1)
 
ORDERER_CA = os.environ["ORDERER_CA"]
ORG1_CA    = os.environ["ORG1_CA"]
ORG2_CA    = os.environ["ORG2_CA"]
 
ATTACK_TYPES = [
    "AI_ALERT",
    "DDoS",
    "BOTNET",
    "PORT_SCAN",
    "MALWARE"
]

# replace create_event for receive_event when we are able to link the iot device
def create_event(event_id):
    event_type = random.choice(ATTACK_TYPES)
    device_id  = f"iot_{random.randint(1,10)}"
    timestamp  = datetime.now().isoformat()
    risk_score = str(round(random.uniform(0.7, 0.99), 2))
    decision   = "BLOCK"
    signature  = "sig123" #right now signature is just sig123, however we need to replace this with CRYSTALS Dilithium
    data_hash  = "hash123" #sha3 hopefully
 
    event = {
        "eventID":   event_id,
        "eventType": event_type,
        "sourceID":  device_id,
        "timestamp": timestamp,
        "riskScore": risk_score,
        "decision":  decision,
        "signature": signature,
        "dataHash":  data_hash
    }
 
    # debugging — remove in deployment
    print("\n==============================")
    print("IoT Device Generated Event")
    print("==============================")
    print(f"Event ID   : {event_id}")
    print(f"Event Type : {event_type}")
    print(f"Device ID  : {device_id}")
    print(f"Timestamp  : {timestamp}")
    print(f"Risk Score : {risk_score}")
    print(f"Decision   : {decision}")
 
    cmd = [
        "peer", "chaincode", "invoke",
        "-o", ORDERER_ADDRESS,
        "--ordererTLSHostnameOverride", ORDERER_HOSTNAME,
        "--tls",
        "--cafile", ORDERER_CA,
        "-C", CHANNEL,
        "-n", CHAINCODE,
        "--peerAddresses", ORG1_PEER,
        "--tlsRootCertFiles", ORG1_CA,
        "--peerAddresses", ORG2_PEER,
        "--tlsRootCertFiles", ORG2_CA,
        "-c",
        f'{{"Args":["CreateEvent","{event_id}","{event_type}","{device_id}","{timestamp}","{risk_score}","{decision}","{signature}","{data_hash}"]}}'
    ]
 
    result = subprocess.run(cmd, capture_output=True, text=True)
 
    if result.returncode == 0:
        print("Event submitted successfully.")
    else:
        print("Event submission failed:")
        print(result.stderr)
 
    return event
for i in range(1, 101):
    event = create_event(f"E{i}")
    EVENT_BUFFER.append(event)
 
    if len(EVENT_BUFFER) == BLOCK_SIZE:
        serialized = json.dumps(
            {"prevHash": PREV_HASH, "events": EVENT_BUFFER},
            sort_keys=True
        ).encode()
 
        # SHA3 as per the research paper
        block_hash = hashlib.sha3_256(serialized).hexdigest()
 
        partial_block = {
            "blockID":    f"PB{BLOCK_NUMBER}",
            "prevHash":   PREV_HASH,
            "timestamp":  datetime.now().isoformat(),
            "eventCount": len(EVENT_BUFFER),
            "blockHash":  block_hash,
            "events":     EVENT_BUFFER,
        }
 
        # debugging — remove in production
        print("\n The Partial Block is ----------")
        print(json.dumps(partial_block, indent=4))
 
        events_json = json.dumps(partial_block["events"])
 
        cmd = [
            "peer", "chaincode", "invoke",
            "-o", ORDERER_ADDRESS,
            "--ordererTLSHostnameOverride", ORDERER_HOSTNAME,
            "--tls",
            "--cafile", ORDERER_CA,
            "-C", CHANNEL,
            "-n", CHAINCODE,
            "--peerAddresses", ORG1_PEER,
            "--tlsRootCertFiles", ORG1_CA,
            "--peerAddresses", ORG2_PEER,
            "--tlsRootCertFiles", ORG2_CA,
            "-c",
            json.dumps({
                "Args": [
                    "CreatePartialBlock",
                    partial_block["blockID"],
                    PREV_HASH,
                    partial_block["timestamp"],
                    partial_block["blockHash"],
                    events_json
                ]
            })
        ]
 
        result = subprocess.run(cmd, capture_output=True, text=True)
 
        if result.returncode == 0:
            print(f"Successfully committed {partial_block['blockID']}")
            PREV_HASH = partial_block["blockHash"]
        else:
            print(f"Failed to commit {partial_block['blockID']}")
            print(result.stderr)
 
        EVENT_BUFFER.clear()
        BLOCK_NUMBER += 1