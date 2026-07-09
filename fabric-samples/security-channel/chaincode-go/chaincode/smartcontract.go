package chaincode

import (
"encoding/json"
"fmt"
"strconv"

"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

type SmartContract struct {
contractapi.Contract
}

type Alert struct {
AlertID     string  `json:"alertId"`
TxRef       string  `json:"txRef"`
DeviceID    string  `json:"deviceId"`
EdgeCluster string  `json:"edgeCluster"`
ThreatType  string  `json:"threatType"`
Severity    string  `json:"severity"`
Score       float64 `json:"score"`
Timestamp   string  `json:"timestamp"`
Resolved    bool    `json:"resolved"`
}

func (s *SmartContract) RaiseAlert(ctx contractapi.TransactionContextInterface, alertID string, txRef string, deviceID string, edgeCluster string, threatType string, severity string, scoreStr string) error {
existing, err := ctx.GetStub().GetState(alertID)
if err != nil {
return fmt.Errorf("failed to read ledger: %v", err)
}
if existing != nil {
return fmt.Errorf("alert %s already exists", alertID)
}
score, err := strconv.ParseFloat(scoreStr, 64)
if err != nil {
return fmt.Errorf("invalid score: %v", err)
}
txTime, err := ctx.GetStub().GetTxTimestamp()
if err != nil {
return fmt.Errorf("failed to get tx timestamp: %v", err)
}
alert := Alert{
AlertID:     alertID,
TxRef:       txRef,
DeviceID:    deviceID,
EdgeCluster: edgeCluster,
ThreatType:  threatType,
Severity:    severity,
Score:       score,
Timestamp:   fmt.Sprintf("%d", txTime.Seconds),
Resolved:    false,
}
alertJSON, err := json.Marshal(alert)
if err != nil {
return err
}
ctx.GetStub().SetEvent("RaiseAlert", alertJSON)
return ctx.GetStub().PutState(alertID, alertJSON)
}

func (s *SmartContract) GetAlert(ctx contractapi.TransactionContextInterface, alertID string) (*Alert, error) {
alertJSON, err := ctx.GetStub().GetState(alertID)
if err != nil {
return nil, fmt.Errorf("failed to read alert: %v", err)
}
if alertJSON == nil {
return nil, fmt.Errorf("alert %s does not exist", alertID)
}
var alert Alert
err = json.Unmarshal(alertJSON, &alert)
if err != nil {
return nil, err
}
return &alert, nil
}

func (s *SmartContract) ResolveAlert(ctx contractapi.TransactionContextInterface, alertID string) error {
alert, err := s.GetAlert(ctx, alertID)
if err != nil {
return err
}
alert.Resolved = true
alertJSON, err := json.Marshal(alert)
if err != nil {
return err
}
return ctx.GetStub().PutState(alertID, alertJSON)
}

func (s *SmartContract) GetAllAlerts(ctx contractapi.TransactionContextInterface) ([]*Alert, error) {
iterator, err := ctx.GetStub().GetStateByRange("", "")
if err != nil {
return nil, err
}
defer iterator.Close()
var alerts []*Alert
for iterator.HasNext() {
result, err := iterator.Next()
if err != nil {
return nil, err
}
var alert Alert
err = json.Unmarshal(result.Value, &alert)
if err != nil {
return nil, err
}
alerts = append(alerts, &alert)
}
return alerts, nil
}

func (s *SmartContract) GetUnresolvedAlerts(ctx contractapi.TransactionContextInterface) ([]*Alert, error) {
all, err := s.GetAllAlerts(ctx)
if err != nil {
return nil, err
}
var unresolved []*Alert
for _, a := range all {
if !a.Resolved {
unresolved = append(unresolved, a)
}
}
return unresolved, nil
}
