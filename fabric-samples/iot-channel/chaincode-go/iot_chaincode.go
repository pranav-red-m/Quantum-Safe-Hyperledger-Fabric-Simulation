package main

import (
	"fmt"

	"github.com/hyperledger/fabric-samples/iot-channel/chaincode-go/chaincode"
	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

func main() {
	cc, err := contractapi.NewChaincode(&chaincode.SmartContract{})
	if err != nil {
		fmt.Printf("Error creating IoT chaincode: %v\n", err)
		return
	}

	if err := cc.Start(); err != nil {
		fmt.Printf("Error starting IoT chaincode: %v\n", err)
	}
}