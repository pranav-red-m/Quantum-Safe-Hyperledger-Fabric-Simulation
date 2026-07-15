'use strict';
const { WorkloadModuleBase } = require('@hyperledger/caliper-core');

const DEVICE_COUNT = 10;

/**
 * One-time setup round: registers the 10 devices that every submit/get
 * round below targets (bench-device-0 .. bench-device-9). Must run once,
 * before any rate-sweep round, against a fresh ledger.
 */
class RegisterDevicesWorkload extends WorkloadModuleBase {
    constructor() {
        super();
        this.txIndex = 0;
    }

    async submitTransaction() {
        if (this.txIndex >= DEVICE_COUNT) {
            return;
        }
        const deviceId = `bench-device-${this.txIndex}`;
        this.txIndex++;

        const args = {
            contractId: 'iotcc',
            contractFunction: 'RegisterDevice',
            contractArguments: [deviceId, 'sensor-node', 'edge-cluster-1', 'Org1MSP'],
            readOnly: false,
        };

        await this.sutAdapter.sendRequests(args);
    }
}

function createWorkloadModule() {
    return new RegisterDevicesWorkload();
}
module.exports.createWorkloadModule = createWorkloadModule;