package main

import (
"log"

"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
"github.com/hyperledger/fabric-samples/iot-channel/chaincode-go/chaincode"
)

func main() {
assetChaincode, err := contractapi.NewChaincode(&chaincode.SmartContract{})
if err != nil {
log.Panicf("Error creating iot chaincode: %v", err)
}

if err := assetChaincode.Start(); err != nil {
log.Panicf("Error starting iot chaincode: %v", err)
}
}
