'use strict';
const { WorkloadModuleBase } = require('@hyperledger/caliper-core');
const fs = require('fs');

fs.appendFileSync('/tmp/caliper-retry-debug.log', `MODULE LOADED at ${new Date().toISOString()}\n`);

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
                `bench-caliper-device-${this.workerIndex}`,
                'edge-cluster-1',
                `hash_${this.workerIndex}_${this.txIndex}`,
                'confirmed'
            ],
            readOnly: false
        };

        await this._sendWithRetry(args);
    }
    async _sendWithRetry(args, maxRetries = 3) {
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            const result = await this.sutAdapter.sendRequests(args);
            const status = result && result.status && result.status.status;

            if (status === 'success') {
                return;
            }

            if (attempt === maxRetries) {
                return;
            }

            const delay = Math.min(100 * Math.pow(2, attempt), 500) + Math.floor(Math.random() * 50);
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }
}

function createWorkloadModule() {
    return new SubmitRecordWorkload();
}
module.exports.createWorkloadModule = createWorkloadModule;