'use strict';
const { WorkloadModuleBase } = require('@hyperledger/caliper-core');

/**
 * Seeds a fixed, deterministic pool of records (SEED_<worker>_<index>) so
 * the read-sweep rounds (get-*tps) can address known-good TxIDs without
 * depending on the write sweep's timestamp-based IDs. Run once, before any
 * get-*tps round, against a fresh ledger — after register-devices.
 *
 * roundArguments.recordsPerWorker controls pool size; the read sweep's
 * seedRecordsPerWorker argument must match this value.
 */
class SeedRecordsWorkload extends WorkloadModuleBase {
    constructor() {
        super();
        this.txIndex = 0;
    }

    async initializeWorkloadModule(workerIndex, totalWorkers, roundIndex, roundArguments, sutAdapter, sutContext) {
        await super.initializeWorkloadModule(workerIndex, totalWorkers, roundIndex, roundArguments, sutAdapter, sutContext);
        this.recordsPerWorker = (roundArguments && roundArguments.recordsPerWorker) || 200;
    }

    async submitTransaction() {
        if (this.txIndex >= this.recordsPerWorker) {
            return;
        }
        this.txIndex++;

        const args = {
            contractId: 'iotcc',
            contractFunction: 'SubmitRecord',
            contractArguments: [
                `SEED_${this.workerIndex}_${this.txIndex}`,
                `bench-device-${this.workerIndex % 10}`,
                'edge-cluster-1',
                `hash_seed_${this.workerIndex}_${this.txIndex}`,
                'confirmed',
            ],
            readOnly: false,
        };

        await this.sutAdapter.sendRequests(args);
    }
}

function createWorkloadModule() {
    return new SeedRecordsWorkload();
}
module.exports.createWorkloadModule = createWorkloadModule;