package main

import (
"log"

"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
"github.com/hyperledger/fabric-samples/security-channel/chaincode-go/chaincode"
)

func main() {
cc, err := contractapi.NewChaincode(&chaincode.SmartContract{})
if err != nil {
log.Panicf("Error creating security chaincode: %v", err)
}
if err := cc.Start(); err != nil {
log.Panicf("Error starting security chaincode: %v", err)
}
}
