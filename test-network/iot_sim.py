import subprocess
import json
import time
import random
import csv
import datetime
import os

BASE = os.path.expanduser("~/thisbetterwork/fabric-samples")
TEST_NETWORK = f"{BASE}/test-network"
ORDERER_CA = f"{TEST_NETWORK}/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem"
CHANNEL = "mychannel"
CC_NAME = "eventcc"
NUM_TRANSACTIONS = 30                   #Number of transaction per organization
OUTPUT_CSV = "simulation_results.csv"
 

ORGS = {
    "Org1": {
        "mspid": "Org1MSP",
        "address": "localhost:7051",
        "tls_root": f"{TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem",
        "tls_cert": f"{TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt",
        "msp_path": f"{TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp",
    },
    "Org2": {
        "mspid": "Org2MSP",
        "address": "localhost:9051",
        "tls_root": f"{TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem",
        "tls_cert": f"{TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt",
        "msp_path": f"{TEST_NETWORK}/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp",
    },
    "Org3": {
        "mspid": "Org3MSP",
        "address": "localhost:11051",
        "tls_root": f"{TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/tlsca/tlsca.org3.example.com-cert.pem",
        "tls_cert": f"{TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt",
        "msp_path": f"{TEST_NETWORK}/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp",
    },
}
 
def submit(org_config, asset_id, temp, humidity):
    env = os.environ.copy()
    env["CORE_PEER_TLS_ENABLED"]       = "true"
    env["CORE_PEER_LOCALMSPID"]        = org_config["mspid"]
    env["CORE_PEER_ADDRESS"]           = org_config["address"]
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = org_config["tls_cert"]
    env["CORE_PEER_MSPCONFIGPATH"]     = org_config["msp_path"]
    env["PATH"]                        = f"{BASE}/bin:" + env.get("PATH", "")
    env["FABRIC_CFG_PATH"]             = f"{BASE}/config/"

    payload = json.dumps({
        "function": "CreateAsset",
        "Args": [
            asset_id,
            "sensor",
            str(int(temp)),
            "IoTDevice",
            str(int(humidity))
        ]
    })
 
    cmd = [
        f"{BASE}/bin/peer", "chaincode", "invoke",
        "-o", "localhost:7050",
        "--ordererTLSHostnameOverride", "orderer.example.com",
        "--tls", "--cafile", ORDERER_CA,
        "-C", CHANNEL, "-n", CC_NAME,
        "--peerAddresses", ORGS["Org1"]["address"],
        "--tlsRootCertFiles", ORGS["Org1"]["tls_root"],
        "--peerAddresses", ORGS["Org2"]["address"],
        "--tlsRootCertFiles", ORGS["Org2"]["tls_root"],
        "--peerAddresses", ORGS["Org3"]["address"],
        "--tlsRootCertFiles", ORGS["Org3"]["tls_root"],
        "-c", payload,
    ]
 
    start  = time.time()
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    latency_ms = (time.time() - start) * 1000
 
    success = result.returncode == 0
    if not success:
        print(f"    ERROR: {result.stderr}")
 
    return latency_ms, success

def main():
    print("=" * 55)
    print("  IoT Simulation Submitting random data to Fabric")
    print("=" * 55)
 
    results = []
    counter = int(time.time())
 
    for org_name, org_config in ORGS.items():
        print(f"\n[{org_name}] Submitting {NUM_TRANSACTIONS} transactions...")
        for i in range(NUM_TRANSACTIONS):
            asset_id = f"iot-{org_name.lower()}-{counter}"
            counter += 1
 
            temp     = round(random.uniform(20.0, 35.0), 2)
            humidity = round(random.uniform(40.0, 70.0), 2)
            pressure = round(random.uniform(980.0, 1050.0), 2)
 
            latency, success = submit(org_config, asset_id, temp, humidity)
            status = "OK  " if success else "FAIL"
 
            print(f"  [{status}] {asset_id} | temp={temp} humidity={humidity} pressure={pressure} | {latency:.0f}ms")
 
            results.append({
                "org":         org_name,
                "asset_id":    asset_id,
                "temperature": temp,
                "humidity":    humidity,
                "pressure":    pressure,
                "latency_ms":  round(latency, 2),
                "success":     success,
                "timestamp":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

            time.sleep(0.5)
    print("\n" + "=" * 55)
    print("  LATENCY SUMMARY")
    print("=" * 55)
    for org_name in ORGS:
        ok = [r for r in results if r["org"] == org_name and r["success"]]
        if ok:
            lats = [r["latency_ms"] for r in ok]
            print(f"\n  {org_name}:")
            print(f"    Success : {len(ok)}/{NUM_TRANSACTIONS}")
            print(f"    Avg     : {sum(lats)/len(lats):.2f} ms")
            print(f"    Min     : {min(lats):.2f} ms")
            print(f"    Max     : {max(lats):.2f} ms")
    if results:
        with open("results.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print("\nResults saved to results.csv\n")
 
if __name__ == "__main__":
    main()