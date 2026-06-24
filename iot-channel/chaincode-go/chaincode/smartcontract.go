package chaincode

import (
"encoding/json"
"fmt"
"time"

"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

type SmartContract struct {
contractapi.Contract
}

type IoTRecord struct {
TxID        string `json:"txId"`
DeviceID    string `json:"deviceId"`
EdgeCluster string `json:"edgeCluster"`
DataHash    string `json:"dataHash"`
Timestamp   string `json:"timestamp"`
Status      string `json:"status"`
}

func (s *SmartContract) SubmitRecord(ctx contractapi.TransactionContextInterface, txID string, deviceID string, edgeCluster string, dataHash string, status string) error {
existing, err := ctx.GetStub().GetState(txID)
if err != nil {
return fmt.Errorf("failed to read ledger: %v", err)
}
if existing != nil {
return fmt.Errorf("record %s already exists", txID)
}
record := IoTRecord{
TxID:        txID,
DeviceID:    deviceID,
EdgeCluster: edgeCluster,
DataHash:    dataHash,
txTime, _ := ctx.GetStub().GetTxTimestamp()
		Timestamp:   fmt.Sprintf("%d", txTime.Seconds),
Status:      status,
}
recordJSON, err := json.Marshal(record)
if err != nil {
return err
}
ctx.GetStub().SetEvent("SubmitRecord", recordJSON)
return ctx.GetStub().PutState(txID, recordJSON)
}

func (s *SmartContract) GetRecord(ctx contractapi.TransactionContextInterface, txID string) (*IoTRecord, error) {
recordJSON, err := ctx.GetStub().GetState(txID)
if err != nil {
return nil, fmt.Errorf("failed to read record: %v", err)
}
if recordJSON == nil {
return nil, fmt.Errorf("record %s does not exist", txID)
}
var record IoTRecord
err = json.Unmarshal(recordJSON, &record)
if err != nil {
return nil, err
}
return &record, nil
}

func (s *SmartContract) GetAllRecords(ctx contractapi.TransactionContextInterface) ([]*IoTRecord, error) {
iterator, err := ctx.GetStub().GetStateByRange("", "")
if err != nil {
return nil, err
}
defer iterator.Close()
var records []*IoTRecord
for iterator.HasNext() {
result, err := iterator.Next()
if err != nil {
return nil, err
}
var record IoTRecord
err = json.Unmarshal(result.Value, &record)
if err != nil {
return nil, err
}
records = append(records, &record)
}
return records, nil
}

func (s *SmartContract) VerifyHash(ctx contractapi.TransactionContextInterface, txID string, hash string) (bool, error) {
record, err := s.GetRecord(ctx, txID)
if err != nil {
return false, err
}
return record.DataHash == hash, nil
}
