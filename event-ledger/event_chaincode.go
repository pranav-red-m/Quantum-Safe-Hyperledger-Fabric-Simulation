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
// Defining Partial Block

type PartialBlock struct {
    BlockID      string  `json:"blockID"`
    PreviousHash string  `json:"previousHash"`
    Timestamp    string  `json:"timestamp"`
    EventCount   int     `json:"eventCount"`
    BlockHash    string  `json:"blockHash"`
    Events       []Event `json:"events"`
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

func (s *SmartContract) CreatePartialBlock(
    ctx contractapi.TransactionContextInterface,
    blockID string,
	prevHash string,
    timestamp string,
    blockHash string,
    eventsJSON string,
) error{
	var events []Event
	err := json.Unmarshal([]byte(eventsJSON),&events,)
	if err != nil {return err}

	partialBlock := PartialBlock{
		BlockID:      blockID,
		PreviousHash: prevHash,
		Timestamp:    timestamp,
		EventCount:   len(events),
		BlockHash:    blockHash,
		Events:       events,
	}

	blockJSON, err :=json.Marshal(partialBlock)
	if err != nil {return err}

	return ctx.GetStub().PutState(blockID,blockJSON,)
}

// Read partial block
func (s *SmartContract) ReadPartialBlock(
	ctx contractapi.TransactionContextInterface,
	blockID string,
) (*PartialBlock,error){
	blockJSON,err := ctx.GetStub().GetState(blockID)
	if err != nil {return nil,err}
	if blockJSON == nil {return nil,fmt.Errorf("Partialblock not found")}

	var block PartialBlock

	err = json.Unmarshal(blockJSON,&block,)
	if err != nil {return nil,err}
	return &block,nil
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
func main() {
    chaincode, err := contractapi.NewChaincode(new(SmartContract))
    if err != nil {fmt.Printf("Error creating chaincode: %v", err)return}
    if err := chaincode.Start(); err != nil {fmt.Printf("Error starting chaincode: %v", err)}
}