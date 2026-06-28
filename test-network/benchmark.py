#!/usr/bin/env python3

import subprocess
import time
import json
import statistics
import csv
import os
import sys
import threading
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

FULL_MODE = "--full" in sys.argv

HOME = os.path.expanduser("~")
NETWORK_DIR = f"{HOME}/testingmultpeers/fabric-samples/test-network"

ORDERER_CA = f"{NETWORK_DIR}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem"
ORG1_TLS   = f"{NETWORK_DIR}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
ORG2_TLS   = f"{NETWORK_DIR}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
ORG3_TLS   = f"{NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"

BASE_ENV = {
    **os.environ,
    "CORE_PEER_TLS_ENABLED": "true",
    "CORE_PEER_LOCALMSPID": "Org1MSP",
    "CORE_PEER_TLS_ROOTCERT_FILE": ORG1_TLS,
    "CORE_PEER_MSPCONFIGPATH": f"{NETWORK_DIR}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp",
    "CORE_PEER_ADDRESS": "localhost:7051",
    "FABRIC_CFG_PATH": f"{HOME}/testingmultpeers/fabric-samples/config",
    "PATH": f"{HOME}/testingmultpeers/fabric-samples/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
}

RESULTS = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

def invoke(args_json):
    cmd = [
        "peer", "chaincode", "invoke",
        "-o", "localhost:7050",
        "--ordererTLSHostnameOverride", "orderer.example.com",
        "--tls", "--cafile", ORDERER_CA,
        "-C", "mychannel", "-n", "iotcc",
        "--peerAddresses", "localhost:7051", "--tlsRootCertFiles", ORG1_TLS,
        "--peerAddresses", "localhost:9051", "--tlsRootCertFiles", ORG2_TLS,
        "--peerAddresses", "localhost:11051", "--tlsRootCertFiles", ORG3_TLS,
        "-c", args_json,
        "--waitForEvent"
    ]
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, env=BASE_ENV)
    elapsed = (time.time() - start) * 1000
    success = result.returncode == 0
    return elapsed, success, result.stderr

def query(args_json):
    cmd = [
        "peer", "chaincode", "query",
        "-C", "mychannel", "-n", "iotcc",
        "-c", args_json
    ]
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, env=BASE_ENV)
    elapsed = (time.time() - start) * 1000
    return elapsed, result.returncode == 0, result.stdout

def print_stats(label, times):
    if not times:
        print(f"\n  {label}: No successful results")
        return {}
    print(f"\n  {label}")
    print(f"    Runs:    {len(times)}")
    print(f"    Mean:    {statistics.mean(times):.2f} ms")
    print(f"    Median:  {statistics.median(times):.2f} ms")
    print(f"    StdDev:  {statistics.stdev(times) if len(times) > 1 else 0:.2f} ms")
    print(f"    Min:     {min(times):.2f} ms")
    print(f"    Max:     {max(times):.2f} ms")
    return {
        "mean": round(statistics.mean(times), 2),
        "median": round(statistics.median(times), 2),
        "stdev": round(statistics.stdev(times) if len(times) > 1 else 0, 2),
        "min": round(min(times), 2),
        "max": round(max(times), 2),
    }

# ── Test 1: Single Record Latency ─────────────────────────────────────────────

def test_single_latency(runs=30):
    print("\n[TEST 1] Single Record Submission Latency")
    times = []
    failures = 0
    for i in range(runs):
        tx_id = f"BENCH_SINGLE_{int(time.time()*1000)}_{i}"
        args = json.dumps({
            "function": "SubmitRecord",
            "Args": [tx_id, f"device-{i}", "edge-cluster-1", f"hash{i:04d}", "confirmed"]
        })
        elapsed, success, err = invoke(args)
        if success:
            times.append(elapsed)
            print(f"  Run {i+1}/{runs}: {elapsed:.2f} ms ✓")
        else:
            failures += 1
            print(f"  Run {i+1}/{runs}: FAILED — {err.strip()[-80:]}")
        time.sleep(0.3)

    stats = print_stats("Single Record", times)
    stats["failures"] = failures
    RESULTS["single_latency"] = stats

# ── Test 2: Batch vs Single ───────────────────────────────────────────────────

def test_batch_vs_single(batch_size=10, runs=10):
    print(f"\n[TEST 2] Batch ({batch_size} records) vs Single Submission")
    print("  ⚠️  Requires SubmitBatch in chaincode")

    single_times = []
    for i in range(runs):
        start = time.time()
        for j in range(batch_size):
            tx_id = f"BENCH_SEQ_{int(time.time()*1000)}_{i}_{j}"
            args = json.dumps({
                "function": "SubmitRecord",
                "Args": [tx_id, f"device-{j}", "edge-1", f"hash{j}", "confirmed"]
            })
            invoke(args)
        elapsed = (time.time() - start) * 1000
        single_times.append(elapsed)
        print(f"  Single run {i+1}: {elapsed:.2f} ms for {batch_size} records")
        time.sleep(0.5)

    batch_times = []
    for i in range(runs):
        records = [
            {
                "txId": f"BENCH_BATCH_{int(time.time()*1000)}_{i}_{j}",
                "deviceId": f"device-{j}",
                "edgeCluster": "edge-cluster-1",
                "dataHash": f"batchhash{j}",
                "timestamp": "",
                "status": "confirmed"
            }
            for j in range(batch_size)
        ]
        args = json.dumps({
            "function": "SubmitBatch",
            "Args": [json.dumps(records)]
        })
        elapsed, success, err = invoke(args)
        if success:
            batch_times.append(elapsed)
            print(f"  Batch run {i+1}: {elapsed:.2f} ms for {batch_size} records ✓")
        else:
            print(f"  Batch run {i+1}: FAILED — {err.strip()[-80:]}")
        time.sleep(0.5)

    speedup = round(statistics.mean(single_times) / statistics.mean(batch_times), 2) if batch_times else 0
    RESULTS["batch_vs_single"] = {
        "single": print_stats(f"Single x{batch_size}", single_times),
        "batch": print_stats(f"Batch x{batch_size}", batch_times),
        "speedup": speedup
    }
    print(f"\n  Speedup from batching: {speedup}x")

# ── Test 3: Concurrent Load ───────────────────────────────────────────────────

def test_concurrent_load(device_counts=[10, 50, 100]):
    print("\n[TEST 3] Concurrent Load Test")
    RESULTS["load_test"] = {}

    for count in device_counts:
        print(f"\n  Simulating {count} concurrent devices...")
        times = []
        lock = threading.Lock()

        def submit_device(device_num):
            tx_id = f"LOAD_{count}_{int(time.time()*1000)}_{device_num}"
            args = json.dumps({
                "function": "SubmitRecord",
                "Args": [tx_id, f"device-{device_num}", "edge-cluster-1", f"loadhash{device_num}", "confirmed"]
            })
            elapsed, success, _ = invoke(args)
            if success:
                with lock:
                    times.append(elapsed)

        threads = [threading.Thread(target=submit_device, args=(i,)) for i in range(count)]
        wall_start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall_time = (time.time() - wall_start) * 1000
        tps = count / (wall_time / 1000)

        print(f"  {count} devices: wall={wall_time:.2f}ms, tps={tps:.2f}, success={len(times)}/{count}")
        RESULTS["load_test"][str(count)] = {
            "wall_time_ms": round(wall_time, 2),
            "tps": round(tps, 2),
            "success_rate": f"{len(times)}/{count}"
        }
        time.sleep(2)

# ── Test 4: Query Latency ─────────────────────────────────────────────────────

def test_query_latency(runs=30):
    print("\n[TEST 4] Query Latency")
    single_times = []
    all_times = []

    for i in range(runs):
        elapsed, _, _ = query('{"function":"GetRecord","Args":["BENCH_SINGLE_0"]}')
        single_times.append(elapsed)
        elapsed2, _, _ = query('{"function":"GetAllRecords","Args":[]}')
        all_times.append(elapsed2)
        time.sleep(0.1)

    RESULTS["query_latency"] = {
        "get_record": print_stats("GetRecord", single_times),
        "get_all_records": print_stats("GetAllRecords", all_times)
    }

# ── Test 5: Alert Write Latency ───────────────────────────────────────────────

def test_alert_latency(runs=20):
    print("\n[TEST 5] Alert Write Latency (IDS → On-Chain)")
    print("  ⚠️  Requires RaiseAlert in chaincode")
    times = []

    for i in range(runs):
        alert_id = f"ALERT_{int(time.time()*1000)}_{i}"
        args = json.dumps({
            "function": "RaiseAlert",
            "Args": [alert_id, "TX001", "device-001", "HIGH", "Anomalous transmission rate detected", "edge-cluster-1"]
        })
        elapsed, success, err = invoke(args)
        if success:
            times.append(elapsed)
            print(f"  Alert {i+1}/{runs}: {elapsed:.2f} ms ✓")
        else:
            print(f"  Alert {i+1}/{runs}: FAILED — {err.strip()[-80:]}")
        time.sleep(0.3)

    RESULTS["alert_latency"] = print_stats("Alert Write", times)

# ── Save Results ──────────────────────────────────────────────────────────────

def save_results():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_file = f"benchmark_results_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(RESULTS, f, indent=2)
    print(f"\n✅ JSON saved to {json_file}")

    csv_file = f"benchmark_summary_{timestamp}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Test", "Metric", "Value"])
        if "single_latency" in RESULTS:
            for k, v in RESULTS["single_latency"].items():
                writer.writerow(["Single Latency", k, v])
        if "alert_latency" in RESULTS:
            for k, v in RESULTS["alert_latency"].items():
                writer.writerow(["Alert Latency", k, v])
        if "load_test" in RESULTS:
            for count, data in RESULTS["load_test"].items():
                writer.writerow([f"Load {count} devices", "tps", data["tps"]])
                writer.writerow([f"Load {count} devices", "wall_time_ms", data["wall_time_ms"]])
    print(f"✅ CSV saved to {csv_file}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Hyperledger Fabric IoT Benchmark Suite")
    if FULL_MODE:
        print("  Mode: FULL (includes SubmitBatch + RaiseAlert)")
    else:
        print("  Mode: BASIC (Tests 1, 3, 4 only)")
        print("  Run with --full once chaincode is updated")
    print("=" * 60)

    test_single_latency(runs=30)
    test_query_latency(runs=30)
    test_concurrent_load(device_counts=[10, 50, 100])

    if FULL_MODE:
        test_batch_vs_single(batch_size=10, runs=10)
        test_alert_latency(runs=20)

    save_results()

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(json.dumps(RESULTS, indent=2))