'use strict';
const { WorkloadModuleBase } = require('@hyperledger/caliper-core');

class SubmitRecordWorkload extends WorkloadModuleBase {
    constructor() {
        super();
        this.txIndex = 0;
    }

    async submitTransaction() {
        this.txIndex++;
        const args = {
            contractId: 'iotcc',
            contractFunction: 'SubmitRecord',
            contractArguments: [
                `CALIPER_${this.workerIndex}_${this.txIndex}_${Date.now()}`,
                `bench-caliper-device-${this.workerIndex}`,   // <-- unique per worker
                'edge-cluster-1',
                `hash_${this.workerIndex}_${this.txIndex}`,
                'confirmed'
            ],
            readOnly: false
        };
        await this.sutAdapter.sendRequests(args);
    }
}

function createWorkloadModule() {
    return new SubmitRecordWorkload();
}
module.exports.createWorkloadModule = createWorkloadModule;