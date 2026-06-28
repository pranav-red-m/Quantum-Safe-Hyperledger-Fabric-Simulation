package chaincode

import (
	"encoding/json"
	"fmt"

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

func (s *SmartContract) SubmitRecord(
	ctx contractapi.TransactionContextInterface,
	txID string,
	deviceID string,
	edgeCluster string,
	dataHash string,
	status string,
) error {

	existing, err := ctx.GetStub().GetState(txID)
	if err != nil {
		return fmt.Errorf("failed to read from ledger: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("record with ID %s already exists", txID)
	}

	txTimestamp, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get transaction timestamp: %v", err)
	}
	timestamp := fmt.Sprintf("%d", txTimestamp.Seconds)

	record := IoTRecord{
		TxID:        txID,
		DeviceID:    deviceID,
		EdgeCluster: edgeCluster,
		DataHash:    dataHash,
		Timestamp:   timestamp,
		Status:      status,
	}

	recordJSON, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal record: %v", err)
	}

	err = ctx.GetStub().SetEvent("SubmitRecord", recordJSON)
	if err != nil {
		return fmt.Errorf("failed to set event: %v", err)
	}

	return ctx.GetStub().PutState(txID, recordJSON)
}

func (s *SmartContract) GetRecord(
	ctx contractapi.TransactionContextInterface,
	txID string,
) (*IoTRecord, error) {

	recordJSON, err := ctx.GetStub().GetState(txID)
	if err != nil {
		return nil, fmt.Errorf("failed to read record %s: %v", txID, err)
	}
	if recordJSON == nil {
		return nil, fmt.Errorf("record %s does not exist", txID)
	}

	var record IoTRecord
	err = json.Unmarshal(recordJSON, &record)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal record: %v", err)
	}

	return &record, nil
}


func (s *SmartContract) GetAllRecords(
	ctx contractapi.TransactionContextInterface,
) ([]*IoTRecord, error) {

	iterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, fmt.Errorf("failed to get state iterator: %v", err)
	}
	defer iterator.Close()

	var records []*IoTRecord

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("failed to iterate records: %v", err)
		}

		var record IoTRecord
		err = json.Unmarshal(result.Value, &record)
		if err != nil {
			return nil, fmt.Errorf("failed to unmarshal record: %v", err)
		}

		records = append(records, &record)
	}

	return records, nil
}

func (s *SmartContract) VerifyHash(
	ctx contractapi.TransactionContextInterface,
	txID string,
	hash string,
) (bool, error) {

	record, err := s.GetRecord(ctx, txID)
	if err != nil {
		return false, err
	}

	return record.DataHash == hash, nil
}

// SubmitBatch allows edge nodes to submit multiple IoT records in one transaction
func (s *SmartContract) SubmitBatch(
	ctx contractapi.TransactionContextInterface,
	recordsJSON string,
) error {

	var records []IoTRecord
	err := json.Unmarshal([]byte(recordsJSON), &records)
	if err != nil {
		return fmt.Errorf("failed to parse batch records: %v", err)
	}

	txTime, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get timestamp: %v", err)
	}
	timestamp := fmt.Sprintf("%d", txTime.Seconds)

	for _, record := range records {
		record.Timestamp = timestamp

		existing, err := ctx.GetStub().GetState(record.TxID)
		if err != nil {
			return fmt.Errorf("failed to read ledger for %s: %v", record.TxID, err)
		}
		if existing != nil {
			return fmt.Errorf("record %s already exists", record.TxID)
		}

		recordJSON, err := json.Marshal(record)
		if err != nil {
			return fmt.Errorf("failed to marshal record %s: %v", record.TxID, err)
		}

		err = ctx.GetStub().PutState(record.TxID, recordJSON)
		if err != nil {
			return fmt.Errorf("failed to write record %s: %v", record.TxID, err)
		}
	}

	batchEvent := map[string]int{"recordsSubmitted": len(records)}
	batchJSON, _ := json.Marshal(batchEvent)
	ctx.GetStub().SetEvent("BatchSubmitted", batchJSON)

	return nil
}

// RaiseAlert writes an IDS anomaly alert immutably to the blockchain
func (s *SmartContract) RaiseAlert(
	ctx contractapi.TransactionContextInterface,
	alertID string,
	txID string,
	deviceID string,
	severity string,
	description string,
	flaggedBy string,
) error {

	key := "ALERT_" + alertID
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read ledger: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("alert %s already exists", alertID)
	}

	txTime, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get timestamp: %v", err)
	}
	timestamp := fmt.Sprintf("%d", txTime.Seconds)

	alert := struct {
		AlertID     string `json:"alertId"`
		TxID        string `json:"txId"`
		DeviceID    string `json:"deviceId"`
		Severity    string `json:"severity"`
		Description string `json:"description"`
		FlaggedBy   string `json:"flaggedBy"`
		Timestamp   string `json:"timestamp"`
		Resolved    bool   `json:"resolved"`
	}{
		AlertID:     alertID,
		TxID:        txID,
		DeviceID:    deviceID,
		Severity:    severity,
		Description: description,
		FlaggedBy:   flaggedBy,
		Timestamp:   timestamp,
		Resolved:    false,
	}

	alertJSON, err := json.Marshal(alert)
	if err != nil {
		return fmt.Errorf("failed to marshal alert: %v", err)
	}

	err = ctx.GetStub().SetEvent("AnomalyAlert", alertJSON)
	if err != nil {
		return fmt.Errorf("failed to set event: %v", err)
	}

	// Also flag the original record if txID provided
	if txID != "" {
		recordJSON, err := ctx.GetStub().GetState(txID)
		if err == nil && recordJSON != nil {
			var record IoTRecord
			if json.Unmarshal(recordJSON, &record) == nil {
				record.Status = "flagged"
				updated, _ := json.Marshal(record)
				ctx.GetStub().PutState(txID, updated)
			}
		}
	}

	return ctx.GetStub().PutState(key, alertJSON)
}

// GetAlertsForDevice returns all alerts for a specific device
func (s *SmartContract) GetAlertsForDevice(
	ctx contractapi.TransactionContextInterface,
	deviceID string,
) ([]*struct {
	AlertID     string `json:"alertId"`
	TxID        string `json:"txId"`
	DeviceID    string `json:"deviceId"`
	Severity    string `json:"severity"`
	Description string `json:"description"`
	FlaggedBy   string `json:"flaggedBy"`
	Timestamp   string `json:"timestamp"`
	Resolved    bool   `json:"resolved"`
}, error) {
	iterator, err := ctx.GetStub().GetStateByRange("ALERT_", "ALERT_~")
	if err != nil {
		return nil, fmt.Errorf("failed to get alerts: %v", err)
	}
	defer iterator.Close()

	var alerts []*struct {
		AlertID     string `json:"alertId"`
		TxID        string `json:"txId"`
		DeviceID    string `json:"deviceId"`
		Severity    string `json:"severity"`
		Description string `json:"description"`
		FlaggedBy   string `json:"flaggedBy"`
		Timestamp   string `json:"timestamp"`
		Resolved    bool   `json:"resolved"`
	}

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		var alert struct {
			AlertID     string `json:"alertId"`
			TxID        string `json:"txId"`
			DeviceID    string `json:"deviceId"`
			Severity    string `json:"severity"`
			Description string `json:"description"`
			FlaggedBy   string `json:"flaggedBy"`
			Timestamp   string `json:"timestamp"`
			Resolved    bool   `json:"resolved"`
		}
		if err := json.Unmarshal(result.Value, &alert); err == nil {
			if alert.DeviceID == deviceID {
				alerts = append(alerts, &alert)
			}
		}
	}
	return alerts, nil
}