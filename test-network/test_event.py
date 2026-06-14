import subprocess
from datetime import datetime
import random
import time
import os
import sys
# Verify Fabric environment variables
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

def create_event(event_id):

    event_type = random.choice(ATTACK_TYPES)
    device_id = f"iot_{random.randint(1,10)}"
    timestamp = datetime.now().isoformat()
    risk_score = str(round(random.uniform(0.7, 0.99), 2))
    decision = "BLOCK"
    signature = "sig123"
    data_hash = "hash123"

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


#do 10 events
for i in range(1, 11):
    create_event(f"E{i}")
    time.sleep(1)