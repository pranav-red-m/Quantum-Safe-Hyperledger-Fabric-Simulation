import argparse, csv, json, os, statistics, subprocess, time, uuid
from dataclasses import dataclass, field

TEST_NETWORK_DIRECTORY = os.path.expanduser("~/testingmultpeers/fabric-samples/test-network")
ORGANIZATION_BASE = os.path.join(TEST_NETWORK_DIRECTORY, "organizations")
FABRIC_BINARY_DIRECTORY = os.path.expanduser("~/testingmultpeers/fabric-samples/bin")
FABRIC_CONFIG_PATH = os.path.expanduser("~/testingmultpeers/fabric-samples/config")
CHANNEL_NAME = "mychannel"
CHAINCODE_NAME = "iotcc"
ORDERER_ADDRESS = "localhost:7050"
ORDERER_TLS_HOSTNAME = "orderer.example.com"
ORDERER_CERTIFICATE_AUTHORITY = os.path.join(
    ORGANIZATION_BASE,
    "ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem",
)
PEERS = [
    ("localhost:7051", os.path.join(ORGANIZATION_BASE, "peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt")),
    ("localhost:9051", os.path.join(ORGANIZATION_BASE, "peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt")),
]
CORE_PEER_LOCAL_MSP_ID = "Org1MSP"
CORE_PEER_TLS_ROOT_CERTIFICATE_FILE = os.path.join(ORGANIZATION_BASE, "peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem")
CORE_PEER_MSP_CONFIG_PATH = os.path.join(ORGANIZATION_BASE, "peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp")
CORE_PEER_ADDRESS = "localhost:7051"


def build_environment():
    environment = os.environ.copy()
    environment["FABRIC_CFG_PATH"] = FABRIC_CONFIG_PATH
    environment["PATH"] = FABRIC_BINARY_DIRECTORY + os.pathsep + environment.get("PATH", "")
    environment["CORE_PEER_TLS_ENABLED"] = "true"
    environment["CORE_PEER_LOCALMSPID"] = CORE_PEER_LOCAL_MSP_ID
    environment["CORE_PEER_TLS_ROOTCERT_FILE"] = CORE_PEER_TLS_ROOT_CERTIFICATE_FILE
    environment["CORE_PEER_MSPCONFIGPATH"] = CORE_PEER_MSP_CONFIG_PATH
    environment["CORE_PEER_ADDRESS"] = CORE_PEER_ADDRESS
    return environment


def invoke_chaincode(function_name, arguments):
    command = [
        "peer", "chaincode", "invoke",
        "-o", ORDERER_ADDRESS,
        "--ordererTLSHostnameOverride", ORDERER_TLS_HOSTNAME,
        "--tls", "--cafile", ORDERER_CERTIFICATE_AUTHORITY,
        "-C", CHANNEL_NAME, "-n", CHAINCODE_NAME,
        "--waitForEvent",
    ]
    for address, certificate in PEERS:
        command += ["--peerAddresses", address, "--tlsRootCertFiles", certificate]
    command += ["-c", json.dumps({"function": function_name, "Args": arguments})]

    start_time = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, env=build_environment())
    elapsed_milliseconds = (time.perf_counter() - start_time) * 1000

    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return elapsed_milliseconds


def query_chaincode(function_name, arguments):
    command = [
        "peer", "chaincode", "query",
        "-C", CHANNEL_NAME, "-n", CHAINCODE_NAME,
        "-c", json.dumps({"function": function_name, "Args": arguments}),
    ]

    start_time = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, env=build_environment())
    elapsed_milliseconds = (time.perf_counter() - start_time) * 1000

    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return elapsed_milliseconds, result.stdout


@dataclass
class TestResult:
    name: str
    latencies: list = field(default_factory=list)
    failures: int = 0

    def add(self, value):
        self.latencies.append(value)

    def summary(self):
        sorted_latencies = sorted(self.latencies)
        count = len(sorted_latencies)
        if not count:
            return {}
        return dict(
            minimum=min(sorted_latencies),
            maximum=max(sorted_latencies),
            mean=statistics.mean(sorted_latencies),
            median=statistics.median(sorted_latencies),
            percentile_95=sorted_latencies[min(int(0.95 * (count - 1)), count - 1)],
            percentile_99=sorted_latencies[min(int(0.99 * (count - 1)), count - 1)],
            standard_deviation=statistics.pstdev(sorted_latencies) if count > 1 else 0,
        )


def build_test_functions():
    partial_block_ids = {}
    full_block_ids = {}
    rejected_full_block_ids = {}

    def initialize_ledger(index):
        print("Testing function: InitLedger")
        print("  Creating the genesis block and setting up the ledger.")
        return invoke_chaincode("InitLedger", [])

    def submit_partial_block(index):
        print("Testing function: SubmitPartialBlock")
        partial_block_id = f"PARTIAL-BLOCK-{uuid.uuid4().hex}"
        device_id = f"DEVICE-{uuid.uuid4().hex[:8]}"
        edge_cluster = f"Edge{index % 3 + 1}"
        print(f"  Submitting partial block '{partial_block_id}' from device '{device_id}' through edge cluster '{edge_cluster}'.")
        elapsed_milliseconds = invoke_chaincode(
            "SubmitPartialBlock",
            [partial_block_id, f"Owner{index}", f"PublicKey{index}", f"EncryptedTransaction{index}", f"Signature{index}", edge_cluster, device_id],
        )
        partial_block_ids[index] = partial_block_id
        return elapsed_milliseconds

    def finalize_full_block(index):
        print("Testing function: FinalizeFullBlock")
        if index not in partial_block_ids:
            submit_partial_block(index)
        full_block_id = f"FULL-BLOCK-{uuid.uuid4().hex}"
        random_nonce = uuid.uuid4().hex[:8]
        print(f"  Finalizing full block '{full_block_id}' from partial block '{partial_block_ids[index]}'.")
        elapsed_milliseconds = invoke_chaincode(
            "FinalizeFullBlock",
            [full_block_id, partial_block_ids[index], random_nonce, "true"],
        )
        full_block_ids[index] = full_block_id
        return elapsed_milliseconds

    def commit_full_block(index):
        print("Testing function: CommitFullBlock")
        if index not in full_block_ids:
            finalize_full_block(index)
        print(f"  Committing full block '{full_block_ids[index]}' to the blockchain.")
        return invoke_chaincode("CommitFullBlock", [full_block_ids[index]])

    def reject_full_block(index):
        print("Testing function: RejectFullBlock")
        submit_partial_block(index)
        finalize_full_block(index)
        full_block_id = full_block_ids[index]
        print(f"  Rejecting full block '{full_block_id}' because consensus failed.")
        elapsed_milliseconds = invoke_chaincode("RejectFullBlock", [full_block_id])
        rejected_full_block_ids[index] = full_block_id
        return elapsed_milliseconds

    def get_partial_block(index):
        print("Testing function: GetPartialBlock")
        if index not in partial_block_ids:
            submit_partial_block(index)
        print(f"  Retrieving partial block '{partial_block_ids[index]}'.")
        return query_chaincode("GetPartialBlock", [partial_block_ids[index]])[0]

    def get_full_block(index):
        print("Testing function: GetFullBlock")
        if index not in full_block_ids:
            finalize_full_block(index)
        print(f"  Retrieving full block '{full_block_ids[index]}'.")
        return query_chaincode("GetFullBlock", [full_block_ids[index]])[0]

    def get_all_full_blocks(index):
        print("Testing function: GetAllFullBlocks")
        print("  Retrieving every full block currently stored on the ledger.")
        return query_chaincode("GetAllFullBlocks", [])[0]

    def get_chain_metadata(index):
        print("Testing function: GetChainMeta")
        print("  Retrieving the current blockchain metadata, including height and latest hash.")
        return query_chaincode("GetChainMeta", [])[0]

    def end_to_end_full_flow(index):
        print("Testing flow: End-to-end commit")
        print("  Running submit, finalize, and commit in sequence.")
        return submit_partial_block(index) + finalize_full_block(index) + commit_full_block(index)

    def end_to_end_reject_flow(index):
        print("Testing flow: End-to-end reject")
        print("  Running submit, finalize, and reject in sequence.")
        return submit_partial_block(index) + finalize_full_block(index) + reject_full_block(index)

    return {
        "initialize_ledger": initialize_ledger,
        "submit_partial_block": submit_partial_block,
        "finalize_full_block": finalize_full_block,
        "commit_full_block": commit_full_block,
        "reject_full_block": reject_full_block,
        "get_partial_block": get_partial_block,
        "get_full_block": get_full_block,
        "get_all_full_blocks": get_all_full_blocks,
        "get_chain_metadata": get_chain_metadata,
        "end_to_end_full_flow": end_to_end_full_flow,
        "end_to_end_reject_flow": end_to_end_reject_flow,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--csv-file", help="Optional CSV file with every individual iteration's latency")
    parser.add_argument("--summary-csv-file", default="benchmark_summary.csv", help="CSV file with per-function latency summary statistics (written automatically)")
    parser.add_argument(
        "--functions",
        nargs="+",
        default=[
            "initialize_ledger",
            "submit_partial_block",
            "finalize_full_block",
            "commit_full_block",
            "reject_full_block",
            "get_partial_block",
            "get_full_block",
            "get_all_full_blocks",
            "get_chain_metadata",
            "end_to_end_full_flow",
            "end_to_end_reject_flow",
        ],
    )
    arguments = parser.parse_args()

    test_functions = build_test_functions()
    all_rows = []
    summary_rows = []

    for function_name in arguments.functions:
        iteration_count = 1 if function_name in ("initialize_ledger", "get_all_full_blocks", "get_chain_metadata") else arguments.iterations
        result = TestResult(function_name)
        print(f"\n===== {function_name} =====")

        for iteration_index in range(iteration_count):
            print(f"\nIteration {iteration_index + 1} of {iteration_count}")
            try:
                latency = test_functions[function_name](iteration_index)
                result.add(latency)
                all_rows.append((function_name, iteration_index, latency))
                print(f"  Result: succeeded in {latency:.2f} milliseconds")
            except Exception as error:
                result.failures += 1
                all_rows.append((function_name, iteration_index, "ERROR"))
                print(f"  Result: failed - {error}")

        summary = result.summary()
        if summary:
            print(
                f"\nSummary for {function_name}: "
                f"mean={summary['mean']:.2f}ms, median={summary['median']:.2f}ms, "
                f"percentile_95={summary['percentile_95']:.2f}ms, maximum={summary['maximum']:.2f}ms, "
                f"standard_deviation={summary['standard_deviation']:.2f}ms, failures={result.failures}"
            )
            summary_rows.append([
                function_name,
                iteration_count,
                result.failures,
                f"{summary['minimum']:.2f}",
                f"{summary['maximum']:.2f}",
                f"{summary['mean']:.2f}",
                f"{summary['median']:.2f}",
                f"{summary['percentile_95']:.2f}",
                f"{summary['percentile_99']:.2f}",
                f"{summary['standard_deviation']:.2f}",
            ])
        else:
            print(f"\nSummary for {function_name}: all {iteration_count} iterations failed")
            summary_rows.append([
                function_name, iteration_count, result.failures,
                "", "", "", "", "", "", "",
            ])

    if arguments.csv_file:
        with open(arguments.csv_file, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["function_name", "iteration", "latency_milliseconds"])
            writer.writerows(all_rows)
        print(f"\nDetailed per-iteration results written to CSV file: {arguments.csv_file}")

    with open(arguments.summary_csv_file, "w", newline="") as summary_csv_file:
        writer = csv.writer(summary_csv_file)
        writer.writerow([
            "function_name",
            "iterations_attempted",
            "failures",
            "minimum_ms",
            "maximum_ms",
            "mean_ms",
            "median_ms",
            "percentile_95_ms",
            "percentile_99_ms",
            "standard_deviation_ms",
        ])
        writer.writerows(summary_rows)
    print(f"Per-function summary results written to CSV file: {arguments.summary_csv_file}")