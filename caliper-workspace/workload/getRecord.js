'use strict';
const { WorkloadModuleBase } = require('@hyperledger/caliper-core');
class GetRecordWorkload extends WorkloadModuleBase {
    constructor() {
        super();
        this.txIndex = 0;
    }

    async initializeWorkloadModule(workerIndex, totalWorkers, roundIndex, roundArguments, sutAdapter, sutContext) {
        await super.initializeWorkloadModule(workerIndex, totalWorkers, roundIndex, roundArguments, sutAdapter, sutContext);
        this.seedRecordsPerWorker = (roundArguments && roundArguments.seedRecordsPerWorker) || 200;
    }

    async submitTransaction() {
        this.txIndex++;
        const sourceIndex = (this.txIndex % this.seedRecordsPerWorker) + 1;
        const txId = `SEED_${this.workerIndex}_${sourceIndex}`;

        const args = {
            contractId: 'iotcc',
            contractFunction: 'GetRecord',
            contractArguments: [txId],
            readOnly: true,
        };

        await this.sutAdapter.sendRequests(args);
    }
}

function createWorkloadModule() {
    return new GetRecordWorkload();
}
module.exports.createWorkloadModule = createWorkloadModule;