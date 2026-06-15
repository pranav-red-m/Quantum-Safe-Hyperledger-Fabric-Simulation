import subprocess
from datetime import datetime
import random
import time
import os
import sys
import hashlib
import json

BLOCK_SIZE = 10
EVENT_BUFFER = []
BLOCK_NUMBER = 1


#checkenv vars
required_vars = ["ORDERER_CA", "ORG1_CA", "ORG2_CA"]
missing = [var for var in required_vars if var not in os.environ]

if missing:
    print("\nERROR: Fabric environment variables are not initialized.")
    print("Missing variables:", ", ".join(missing))
    print("\nRun the following commands before starting this script:\n")
    print("export PATH=${PWD}/../bin:$PATH")
    print("export FABRIC_CFG_PATH=$PWD/../config")
    print("source ./scripts/envVar.sh")
    print("export ORDERER_CA=${PWD}/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem")
    print("export ORG1_CA=${PWD}/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem")
    print("export ORG2_CA=${PWD}/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem")
    sys.exit(1)

ORDERER_CA = os.environ["ORDERER_CA"]
ORG1_CA = os.environ["ORG1_CA"]
ORG2_CA = os.environ["ORG2_CA"]

#get info from ids
ATTACK_TYPES = [
    "AI_ALERT",
    "DDoS",
    "BOTNET",
    "PORT_SCAN",
    "MALWARE"
]
#replace create event for receive event when we are able to link the create iot 
def create_event(event_id):

    event_type = random.choice(ATTACK_TYPES)
    device_id = f"iot_{random.randint(1,10)}"
    timestamp = datetime.now().isoformat()
    risk_score = str(round(random.uniform(0.7, 0.99), 2))
    decision = "BLOCK"
    signature = "sig123"
    data_hash = "hash123"

    event = {
        "eventID": event_id,
        "eventType": event_type,
        "sourceID": device_id,
        "timestamp": timestamp,
        "riskScore": risk_score,
        "decision": decision,
        "signature": signature,
        "dataHash": data_hash
    }

    return event

    #debugging, remove in deployment
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
        "-o", "localhost:7050",
        "--ordererTLSHostnameOverride", "orderer.example.com",
        "--tls",
        "--cafile", ORDERER_CA,
        "-C", "mychannel",
        "-n", "eventcc",
        "--peerAddresses", "localhost:7051",
        "--tlsRootCertFiles", ORG1_CA,
        "--peerAddresses", "localhost:9051",
        "--tlsRootCertFiles", ORG2_CA,
        "-c",
        f'{{"Args":["CreateEvent","{event_id}","{event_type}","{device_id}","{timestamp}","{risk_score}","{decision}","{signature}","{data_hash}"]}}'
    ]

    result = subprocess.run(cmd,capture_output=True,text=True)

    if result.returncode == 0:
        print("Event completed without any errors:\n")
    else:
        print("Simulation failed, loading stderr:\n")
        print(result.stderr)

for i in range(1,101):
    event = create_event(f"E{i}")
    EVENT_BUFFER.append(event)
    if len(EVENT_BUFFER)==BLOCK_SIZE:
        serialized = json.dumps(EVENT_BUFFER,sort_keys=True).encode()
        block_hash = hashlib.sha3_256(serialized).hexdigest() #This currently uses SHA3 as thats we have explored to use within the researcgh paper
        
        partial_block = {
            "blockID": f"PB{BLOCK_NUMBER}",
            "timestamp": datetime.now().isoformat(),
            "eventCount": len(EVENT_BUFFER), #ideal world this should be 10, i dunno so im just gonna put len cause its already precompouted
            "blockHash": block_hash,
            "events": EVENT_BUFFER,
        }
        #debugging remove in production
        print("\n The Partial Block is ----------")
        print(json.dumps(partial_block,indent=4))
# Convert events list into a string
        events_json = json.dumps(partial_block["events"])

        cmd = [
            "peer", "chaincode", "invoke",
            "-o", "localhost:7050",
            "--ordererTLSHostnameOverride", "orderer.example.com",
            "--tls",
            "--cafile", ORDERER_CA,
            "-C", "mychannel",
            "-n", "eventcc",

            "--peerAddresses", "localhost:7051",
            "--tlsRootCertFiles", ORG1_CA,

            "--peerAddresses", "localhost:9051",
            "--tlsRootCertFiles", ORG2_CA,

            "-c",
            json.dumps({
                "Args": [
                    "CreatePartialBlock",
                    partial_block["blockID"],
                    partial_block["timestamp"],
                    partial_block["blockHash"],
                    events_json
                ]
            })
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"Successfully committed {partial_block['blockID']}")
        else:
            print("Failed to commit partial block")
            print(result.stderr)

        EVENT_BUFFER.clear()
        BLOCK_NUMBER+=1
