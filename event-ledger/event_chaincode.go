package main

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// SmartContract defines the chaincode structure
type SmartContract struct {
	contractapi.Contract
}

// Event structure (THIS is your universal AI + IoT + PQC event format)
type Event struct {
	EventID    string `json:"eventID"`
	EventType  string `json:"eventType"`   // AI_ALERT, IOT_DATA, AUTH_EVENT
	SourceID   string `json:"sourceID"`    // device or AI system
	Timestamp  string `json:"timestamp"`
	RiskScore  string `json:"riskScore"`
	Decision   string `json:"decision"`     // ALLOW, BLOCK, FLAG
	Signature  string `json:"signature"`    // PQC placeholder
	DataHash   string `json:"dataHash"`     // integrity check
}

// CreateEvent stores a new security event on blockchain
func (s *SmartContract) CreateEvent(ctx contractapi.TransactionContextInterface,
	eventID string,
	eventType string,
	sourceID string,
	timestamp string,
	riskScore string,
	decision string,
	signature string,
	dataHash string) error {

	fmt.Println("DEBUG: CreateEvent called")

	event := Event{
		EventID:   eventID,
		EventType: eventType,
		SourceID:  sourceID,
		Timestamp: timestamp,
		RiskScore: riskScore,
		Decision:  decision,
		Signature: signature,
		DataHash:  dataHash,
	}


	eventJSON, _ := json.Marshal(event)

	err := ctx.GetStub().PutState(eventID, eventJSON)
	if err != nil {
		fmt.Println("PUTSTATE FAILED:", err)
		return err
	}

	fmt.Println("SUCCESS WRITE:", eventID)

	return nil
}

// ReadEvent retrieves a single event
func (s *SmartContract) ReadEvent(ctx contractapi.TransactionContextInterface, eventID string) (*Event, error) {

	eventJSON, err := ctx.GetStub().GetState(eventID)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if eventJSON == nil {
		return nil, fmt.Errorf("event not found")
	}

	var event Event
	err = json.Unmarshal(eventJSON, &event)
	if err != nil {
		return nil, err
	}

	return &event, nil
}

// GetAllEvents returns full ledger (for stats & graphs)
func (s *SmartContract) GetAllEvents(ctx contractapi.TransactionContextInterface) ([]*Event, error) {

	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var events []*Event

	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var event Event
		err = json.Unmarshal(queryResponse.Value, &event)
		if err != nil {
			return nil, err
		}

		copyEvent := event
		events = append(events, &copyEvent)
	}

	return events, nil
}
// MAIN function (Fabric entry point)
func main() {
    chaincode, err := contractapi.NewChaincode(new(SmartContract))
    if err != nil {
        fmt.Printf("Error creating chaincode: %v", err)
        return
    }

    if err := chaincode.Start(); err != nil {
        fmt.Printf("Error starting chaincode: %v", err)
    }
}