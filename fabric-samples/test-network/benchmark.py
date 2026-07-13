#!/usr/bin/env python3

import subprocess
import time
import json
import statistics
import csv
import os
import sys
import threading
import random
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

def invoke_with_retry(args_json, max_retries=5):
    """Wraps invoke() with jittered backoff on MVCC_READ_CONFLICT.
    Any other failure is returned immediately without retrying."""
    elapsed, success, err = None, False, None
    for attempt in range(max_retries):
        elapsed, success, err = invoke(args_json)
        if success:
            return elapsed, True, err
        if "MVCC_READ_CONFLICT" in str(err):
            time.sleep(0.05 * (2 ** attempt) + random.uniform(0, 0.05))
            continue
        return elapsed, False, err
    return elapsed, False, err

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

    # Register a test device first
    invoke(json.dumps({
        "function": "RegisterDevice",
        "Args": ["bench-device-001", "temperature-sensor", "edge-cluster-1", "Org1MSP"]
    }))
    time.sleep(1)

    for i in range(runs):
        tx_id = f"BENCH_SINGLE_{int(time.time()*1000)}_{i}"
        args = json.dumps({
            "function": "SubmitRecord",
            "Args": [tx_id, "bench-device-001", "edge-cluster-1", f"hash{i:04d}", "confirmed"]
        })
        elapsed, success, err = invoke(args)
        if success:
            times.append(elapsed)
            print(f"  Run {i+1}/{runs}: {elapsed:.2f} ms ✓")
        else:
            failures += 1
            print(f"  Run {i+1}/{runs}: FAILED — {err.strip()[-100:]}")
        time.sleep(0.3)

    stats = print_stats("Single Record", times)
    stats["failures"] = failures
    RESULTS["single_latency"] = stats

# ── Test 2: Batch vs Single ───────────────────────────────────────────────────

def test_batch_vs_single(batch_size=10, runs=10):
    print(f"\n[TEST 2] Batch ({batch_size} records) vs Single Submission")

    # Register batch test device
    invoke(json.dumps({
        "function": "RegisterDevice",
        "Args": ["bench-batch-device", "humidity-sensor", "edge-cluster-1", "Org1MSP"]
    }))
    time.sleep(1)

    single_times = []
    for i in range(runs):
        start = time.time()
        for j in range(batch_size):
            tx_id = f"BENCH_SEQ_{int(time.time()*1000)}_{i}_{j}"
            args = json.dumps({
                "function": "SubmitRecord",
                "Args": [tx_id, "bench-batch-device", "edge-cluster-1", f"hash{j}", "confirmed"]
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
                "deviceId": "bench-batch-device",
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
            print(f"  Batch run {i+1}: FAILED — {err.strip()[-100:]}")
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

        # Register N distinct devices so each thread writes to its own
        # chain tip key, rather than all threads contending for one
        # device's single LATEST_ key.
        device_ids = [f"bench-load-device-{count}-{i}" for i in range(count)]
        for d in device_ids:
            invoke(json.dumps({
                "function": "RegisterDevice",
                "Args": [d, "gps-sensor", "edge-cluster-1", "Org1MSP"]
            }))
        time.sleep(1)

        def submit_device(device_num):
            tx_id = f"LOAD_{count}_{int(time.time()*1000)}_{device_num}"
            args = json.dumps({
                "function": "SubmitRecord",
                "Args": [tx_id, device_ids[device_num], "edge-cluster-1", f"loadhash{device_num}", "confirmed"]
            })
            elapsed, success, _ = invoke_with_retry(args)
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

        committed_tps = len(times) / (wall_time / 1000) if wall_time > 0 else 0
        attempted_tps = count / (wall_time / 1000) if wall_time > 0 else 0

        print(f"  {count} devices: wall={wall_time:.2f}ms, "
              f"committed_tps={committed_tps:.2f}, attempted_tps={attempted_tps:.2f}, "
              f"success={len(times)}/{count}")
        RESULTS["load_test"][str(count)] = {
            "wall_time_ms": round(wall_time, 2),
            "committed_tps": round(committed_tps, 2),
            "attempted_tps": round(attempted_tps, 2),
            "success_rate": f"{len(times)}/{count}"
        }
        time.sleep(2)

    # Spot-check chain integrity for one device from the largest round.
    check_device = f"bench-load-device-{device_counts[-1]}-0"
    print(f"\n  Verifying hash chain integrity after concurrent load ({check_device})...")
    _, vok, vout = query(json.dumps({
        "function": "VerifyChain",
        "Args": [check_device]
    }))
    chain_valid = False
    if vok:
        try:
            result = json.loads(vout)
            chain_valid = result.get("valid", False)
            print(f"  VerifyChain({check_device}): valid={chain_valid}, "
                  f"records_checked={result.get('recordsChecked')}")
            if not chain_valid:
                print(f"    Broke at: {result.get('brokenAtTxId')} — {result.get('reason')}")
        except Exception:
            print(f"  Could not parse VerifyChain output: {vout[:200]}")
    RESULTS["load_test"]["chain_valid_after_load"] = chain_valid

# ── Test 4: Query Latency ─────────────────────────────────────────────────────

def test_query_latency(runs=30):
    print("\n[TEST 4] Query Latency")
    single_times = []
    all_times = []
    device_times = []

    for i in range(runs):
        elapsed, _, _ = query('{"function":"GetRecord","Args":["BENCH_SINGLE_0"]}')
        single_times.append(elapsed)

        elapsed2, _, _ = query('{"function":"GetAllRecords","Args":[]}')
        all_times.append(elapsed2)

        elapsed3, _, _ = query('{"function":"GetDevice","Args":["bench-device-001"]}')
        device_times.append(elapsed3)

        time.sleep(0.1)

    RESULTS["query_latency"] = {
        "get_record": print_stats("GetRecord", single_times),
        "get_all_records": print_stats("GetAllRecords", all_times),
        "get_device": print_stats("GetDevice", device_times)
    }

# ── Test 5: Alert Write Latency ───────────────────────────────────────────────

def test_alert_latency(runs=20):
    print("\n[TEST 5] Alert Write Latency (IDS → On-Chain)")
    times = []

    for i in range(runs):
        alert_id = f"ALERT_{int(time.time()*1000)}_{i}"
        args = json.dumps({
            "function": "RaiseAlert",
            "Args": [alert_id, "BENCH_SINGLE_0", "bench-device-001", "HIGH", "Anomalous transmission rate detected", "edge-cluster-1"]
        })
        elapsed, success, err = invoke(args)
        if success:
            times.append(elapsed)
            print(f"  Alert {i+1}/{runs}: {elapsed:.2f} ms ✓")
        else:
            print(f"  Alert {i+1}/{runs}: FAILED — {err.strip()[-100:]}")
        time.sleep(0.3)

    RESULTS["alert_latency"] = print_stats("Alert Write", times)

# ── Test 6: State Machine Transitions ────────────────────────────────────────

def test_state_machine(runs=10):
    print("\n[TEST 6] State Machine — Record Status Transitions")
    times = []
    failures = 0

    # Register device for state machine test
    invoke(json.dumps({
        "function": "RegisterDevice",
        "Args": ["bench-state-device", "motion-sensor", "edge-cluster-2", "Org1MSP"]
    }))
    time.sleep(1)

    for i in range(runs):
        tx_id = f"BENCH_STATE_{int(time.time()*1000)}_{i}"

        # Step 1 — Submit record
        elapsed, success, err = invoke(json.dumps({
            "function": "SubmitRecord",
            "Args": [tx_id, "bench-state-device", "edge-cluster-2", f"statehash{i}", "confirmed"]
        }))
        if not success:
            print(f"  Run {i+1}: SubmitRecord FAILED — {err.strip()[-80:]}")
            failures += 1
            continue
        time.sleep(0.5)

        # Step 2 — confirmed → validated
        elapsed, success, err = invoke(json.dumps({
            "function": "UpdateRecordStatus",
            "Args": [tx_id, "validated"]
        }))
        if not success:
            print(f"  Run {i+1}: validated FAILED — {err.strip()[-80:]}")
            failures += 1
            continue
        time.sleep(0.5)

        # Step 3 — validated → approved
        elapsed, success, err = invoke(json.dumps({
            "function": "UpdateRecordStatus",
            "Args": [tx_id, "approved"]
        }))
        if not success:
            print(f"  Run {i+1}: approved FAILED — {err.strip()[-80:]}")
            failures += 1
            continue

        times.append(elapsed)
        print(f"  Run {i+1}/{runs}: full transition confirmed→validated→approved ✓")
        time.sleep(0.5)

    # Test invalid transition — should be rejected
    print("\n  Testing invalid transition (validated → confirmed) — should FAIL:")
    tx_id = f"BENCH_INVALID_{int(time.time()*1000)}"
    invoke(json.dumps({
        "function": "SubmitRecord",
        "Args": [tx_id, "bench-state-device", "edge-cluster-2", "invalidhash", "confirmed"]
    }))
    time.sleep(0.5)
    invoke(json.dumps({"function": "UpdateRecordStatus", "Args": [tx_id, "validated"]}))
    time.sleep(0.5)
    _, success, err = invoke(json.dumps({
        "function": "UpdateRecordStatus",
        "Args": [tx_id, "confirmed"]
    }))
    if not success:
        print(f"  ✅ Invalid transition correctly rejected by chaincode")
    else:
        print(f"  ❌ Invalid transition was accepted — state machine not working")

    stats = print_stats("State Transitions", times)
    stats["failures"] = failures
    RESULTS["state_machine"] = stats

# ── Test 7: Challenge Record ──────────────────────────────────────────────────

def test_challenge_record(runs=10):
    print("\n[TEST 7] Cross-Org Record Challenge")
    times = []
    failures = 0

    # Register device for challenge test
    invoke(json.dumps({
        "function": "RegisterDevice",
        "Args": ["bench-challenge-device", "pressure-sensor", "edge-cluster-3", "Org1MSP"]
    }))
    time.sleep(1)

    for i in range(runs):
        tx_id = f"BENCH_CHALLENGE_{int(time.time()*1000)}_{i}"

        # Submit a record
        invoke(json.dumps({
            "function": "SubmitRecord",
            "Args": [tx_id, "bench-challenge-device", "edge-cluster-3", f"challengehash{i}", "confirmed"]
        }))
        time.sleep(0.5)

        # Raise a challenge against it
        challenge_id = f"CH_{int(time.time()*1000)}_{i}"
        elapsed, success, err = invoke(json.dumps({
            "function": "ChallengeRecord",
            "Args": [challenge_id, tx_id, "Sensor reading deviates 60% from baseline — possible tampering"]
        }))
        if success:
            times.append(elapsed)
            print(f"  Run {i+1}/{runs}: challenge raised in {elapsed:.2f} ms ✓")
        else:
            failures += 1
            print(f"  Run {i+1}/{runs}: FAILED — {err.strip()[-100:]}")
        time.sleep(0.3)

    # Query challenges for last record
    print("\n  Querying challenges for last record...")
    _, ok, out = query(json.dumps({
        "function": "GetChallengesForRecord",
        "Args": [tx_id]
    }))
    if ok:
        print(f"  ✅ Challenges retrieved: {out.strip()[:200]}")
    else:
        print(f"  ❌ Query failed")

    stats = print_stats("Challenge Write", times)
    stats["failures"] = failures
    RESULTS["challenge_record"] = stats

# ── Test 8: Device Registry ───────────────────────────────────────────────────

def test_device_registry(runs=20):
    print("\n[TEST 8] Device Registry — Register and Query")
    reg_times = []
    query_times = []
    failures = 0

    for i in range(runs):
        device_id = f"BENCH_DEV_{int(time.time()*1000)}_{i}"

        # Register
        elapsed, success, err = invoke(json.dumps({
            "function": "RegisterDevice",
            "Args": [device_id, "temperature-sensor", "edge-cluster-1", "Org1MSP"]
        }))
        if success:
            reg_times.append(elapsed)
            print(f"  Register {i+1}/{runs}: {elapsed:.2f} ms ✓")
        else:
            failures += 1
            print(f"  Register {i+1}/{runs}: FAILED — {err.strip()[-80:]}")
        time.sleep(0.3)

        # Query it back
        elapsed2, ok, _ = query(json.dumps({
            "function": "GetDevice",
            "Args": [device_id]
        }))
        if ok:
            query_times.append(elapsed2)

    # Test unregistered device rejection
    print("\n  Testing unregistered device rejection...")
    _, success, err = invoke(json.dumps({
        "function": "SubmitRecord",
        "Args": ["TX_UNREGISTERED", "totally-fake-device-xyz", "edge-1", "hash000", "confirmed"]
    }))
    if not success:
        print(f"  ✅ Unregistered device correctly rejected")
    else:
        print(f"  ❌ Unregistered device was accepted — access control not working")

    RESULTS["device_registry"] = {
        "register": print_stats("RegisterDevice", reg_times),
        "query": print_stats("GetDevice", query_times),
        "failures": failures
    }

# ── Test 9: Record History ────────────────────────────────────────────────────

def test_record_history(runs=20):
    print("\n[TEST 9] Record History — Full Audit Trail")
    times = []
    failures = 0

    # Register device for history test
    invoke(json.dumps({
        "function": "RegisterDevice",
        "Args": ["bench-history-device", "temperature-sensor", "edge-cluster-1", "Org1MSP"]
    }))
    time.sleep(1)

    # Create a record and put it through full state machine
    # so history has multiple entries
    history_tx_id = f"BENCH_HISTORY_{int(time.time()*1000)}"
    print(f"\n  Setting up record {history_tx_id} with full state transitions...")

    invoke(json.dumps({
        "function": "SubmitRecord",
        "Args": [history_tx_id, "bench-history-device", "edge-cluster-1", "historyhash001", "confirmed"]
    }))
    time.sleep(1)

    invoke(json.dumps({
        "function": "UpdateRecordStatus",
        "Args": [history_tx_id, "validated"]
    }))
    time.sleep(1)

    invoke(json.dumps({
        "function": "UpdateRecordStatus",
        "Args": [history_tx_id, "approved"]
    }))
    time.sleep(1)

    print(f"  Record has 3 history entries: confirmed → validated → approved")

    # Now benchmark GetRecordHistory
    print(f"\n  Benchmarking GetRecordHistory ({runs} runs)...")
    for i in range(runs):
        elapsed, success, out = query(json.dumps({
            "function": "GetRecordHistory",
            "Args": [history_tx_id]
        }))
        if success:
            times.append(elapsed)
            try:
                history = json.loads(out)
                print(f"  Run {i+1}/{runs}: {elapsed:.2f} ms ✓ ({len(history)} history entries)")
            except:
                print(f"  Run {i+1}/{runs}: {elapsed:.2f} ms ✓")
        else:
            failures += 1
            print(f"  Run {i+1}/{runs}: FAILED")
        time.sleep(0.1)

    # Show full history of the record
    print(f"\n  Full audit trail for {history_tx_id}:")
    _, ok, out = query(json.dumps({
        "function": "GetRecordHistory",
        "Args": [history_tx_id]
    }))
    if ok:
        try:
            history = json.loads(out)
            for idx, entry in enumerate(history):
                print(f"    [{idx+1}] TxID: {entry.get('txId','?')[:20]}... | Status: {entry.get('value',{}).get('status','?')} | Time: {entry.get('timestamp','?')}")
        except:
            print(f"    {out[:300]}")

    stats = print_stats("GetRecordHistory", times)
    stats["failures"] = failures
    RESULTS["record_history"] = stats

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
                if not isinstance(data, dict):
                    continue  # skip the "chain_valid_after_load" bool entry
                writer.writerow([f"Load {count} devices", "committed_tps", data.get("committed_tps")])
                writer.writerow([f"Load {count} devices", "attempted_tps", data.get("attempted_tps")])
                writer.writerow([f"Load {count} devices", "wall_time_ms", data.get("wall_time_ms")])
        if "state_machine" in RESULTS:
            for k, v in RESULTS["state_machine"].items():
                writer.writerow(["State Machine", k, v])
        if "challenge_record" in RESULTS:
            for k, v in RESULTS["challenge_record"].items():
                writer.writerow(["Challenge Record", k, v])
        if "device_registry" in RESULTS:
            for k, v in RESULTS["device_registry"].get("register", {}).items():
                writer.writerow(["Device Registry", k, v])
        if "record_history" in RESULTS:
            for k, v in RESULTS["record_history"].items():
                writer.writerow(["Record History", k, v])
    print(f"✅ CSV saved to {csv_file}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Hyperledger Fabric IoT Benchmark Suite")
    if FULL_MODE:
        print("  Mode: FULL — all 8 tests")
    else:
        print("  Mode: BASIC — Tests 1, 3, 4 only")
        print("  Run with --full for all tests")
    print("=" * 60)

    # Basic tests — always run
    test_single_latency(runs=30)
    test_query_latency(runs=30)
    test_concurrent_load(device_counts=[10, 50, 100])

    # Full tests — only when chaincode is updated
    if FULL_MODE:
        test_batch_vs_single(batch_size=10, runs=10)
        test_alert_latency(runs=20)
        test_state_machine(runs=10)
        test_challenge_record(runs=10)
        test_device_registry(runs=20)
        test_record_history(runs=20) 

    save_results()

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(json.dumps(RESULTS, indent=2))