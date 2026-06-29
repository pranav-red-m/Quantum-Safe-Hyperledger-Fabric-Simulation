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

type RecordChallenge struct {
	ChallengeID    string `json:"challengeId"`
	TxID           string `json:"txId"`
	ChallengingOrg string `json:"challengingOrg"`
	Reason         string `json:"reason"`
	Status         string `json:"status"`
	Timestamp      string `json:"timestamp"`
	Resolution     string `json:"resolution"`
}

type Device struct {
	DeviceID    string `json:"deviceId"`
	DeviceType  string `json:"deviceType"`
	EdgeCluster string `json:"edgeCluster"`
	OrgMSP      string `json:"orgMsp"`
	Active      bool   `json:"active"`
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

	deviceKey := "DEVICE_" + deviceID
	deviceJSON, err := ctx.GetStub().GetState(deviceKey)
	if err != nil {
		return fmt.Errorf("failed to check device registration: %v", err)
	}
	if deviceJSON == nil {
		return fmt.Errorf("device %s is not registered on the blockchain", deviceID)
	}

	var device Device
	err = json.Unmarshal(deviceJSON, &device)
	if err != nil {
		return fmt.Errorf("failed to unmarshal device: %v", err)
	}
	if !device.Active {
		return fmt.Errorf("device %s has been deactivated and cannot submit records", deviceID)
	}

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

func (s *SmartContract) ChallengeRecord(
	ctx contractapi.TransactionContextInterface,
	challengeID string,
	txID string,
	reason string,
) error {

	// Check the record being challenged actually exists
	recordJSON, err := ctx.GetStub().GetState(txID)
	if err != nil {
		return fmt.Errorf("failed to read record: %v", err)
	}
	if recordJSON == nil {
		return fmt.Errorf("record %s does not exist", txID)
	}

	// Check challenge doesn't already exist
	key := "CHALLENGE_" + challengeID
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read ledger: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("challenge %s already exists", challengeID)
	}

	// Get the MSP ID of the org raising the challenge
	clientMSP, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("failed to get client MSP: %v", err)
	}

	txTime, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get timestamp: %v", err)
	}
	timestamp := fmt.Sprintf("%d", txTime.Seconds)

	challenge := RecordChallenge{
		ChallengeID:    challengeID,
		TxID:           txID,
		ChallengingOrg: clientMSP,
		Reason:         reason,
		Status:         "open",
		Timestamp:      timestamp,
		Resolution:     "",
	}

	challengeJSON, err := json.Marshal(challenge)
	if err != nil {
		return fmt.Errorf("failed to marshal challenge: %v", err)
	}

	// Emit event so all orgs are notified
	ctx.GetStub().SetEvent("RecordChallenged", challengeJSON)

	return ctx.GetStub().PutState(key, challengeJSON)
}

// ResolveChallenge closes a challenge with a resolution
func (s *SmartContract) ResolveChallenge(
	ctx contractapi.TransactionContextInterface,
	challengeID string,
	resolution string,
) error {

	key := "CHALLENGE_" + challengeID
	challengeJSON, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read challenge: %v", err)
	}
	if challengeJSON == nil {
		return fmt.Errorf("challenge %s does not exist", challengeID)
	}

	var challenge RecordChallenge
	err = json.Unmarshal(challengeJSON, &challenge)
	if err != nil {
		return fmt.Errorf("failed to unmarshal challenge: %v", err)
	}

	if challenge.Status == "resolved" {
		return fmt.Errorf("challenge %s is already resolved", challengeID)
	}

	challenge.Status = "resolved"
	challenge.Resolution = resolution

	updated, err := json.Marshal(challenge)
	if err != nil {
		return fmt.Errorf("failed to marshal updated challenge: %v", err)
	}

	return ctx.GetStub().PutState(key, updated)
}

// GetChallengesForRecord returns all challenges raised against a record
func (s *SmartContract) GetChallengesForRecord(
	ctx contractapi.TransactionContextInterface,
	txID string,
) ([]*RecordChallenge, error) {

	iterator, err := ctx.GetStub().GetStateByRange("CHALLENGE_", "CHALLENGE_~")
	if err != nil {
		return nil, fmt.Errorf("failed to get challenges: %v", err)
	}
	defer iterator.Close()

	var challenges []*RecordChallenge

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		var challenge RecordChallenge
		if err := json.Unmarshal(result.Value, &challenge); err == nil {
			if challenge.TxID == txID {
				challenges = append(challenges, &challenge)
			}
		}
	}

	return challenges, nil
}

// GetAllChallenges returns every challenge across all records
func (s *SmartContract) GetAllChallenges(
	ctx contractapi.TransactionContextInterface,
) ([]*RecordChallenge, error) {

	iterator, err := ctx.GetStub().GetStateByRange("CHALLENGE_", "CHALLENGE_~")
	if err != nil {
		return nil, fmt.Errorf("failed to get challenges: %v", err)
	}
	defer iterator.Close()

	var challenges []*RecordChallenge

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		var challenge RecordChallenge
		if err := json.Unmarshal(result.Value, &challenge); err == nil {
			challenges = append(challenges, &challenge)
		}
	}

	return challenges, nil
}

// UpdateRecordStatus enforces valid state transitions on IoT records
func (s *SmartContract) UpdateRecordStatus(
	ctx contractapi.TransactionContextInterface,
	txID string,
	newStatus string,
) error {

	// Valid state transitions
	validTransitions := map[string][]string{
		"confirmed":  {"validated"},
		"submitted":  {"validated"},
		"validated":  {"approved", "flagged"},
		"approved":   {"archived"},
		"flagged":    {"resolved"},
		"resolved":   {"archived"},
	}

	// Read existing record
	recordJSON, err := ctx.GetStub().GetState(txID)
	if err != nil {
		return fmt.Errorf("failed to read record %s: %v", txID, err)
	}
	if recordJSON == nil {
		return fmt.Errorf("record %s does not exist", txID)
	}

	var record IoTRecord
	err = json.Unmarshal(recordJSON, &record)
	if err != nil {
		return fmt.Errorf("failed to unmarshal record: %v", err)
	}

	// Check if transition is valid
	allowedStatuses, exists := validTransitions[record.Status]
	if !exists {
		return fmt.Errorf("record %s has unknown status: %s", txID, record.Status)
	}

	valid := false
	for _, allowed := range allowedStatuses {
		if allowed == newStatus {
			valid = true
			break
		}
	}

	if !valid {
		return fmt.Errorf(
			"invalid transition for record %s: %s → %s (allowed: %v)",
			txID, record.Status, newStatus, allowedStatuses,
		)
	}

	// Apply the new status
	record.Status = newStatus

	updated, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal updated record: %v", err)
	}

	// Emit event so all orgs are notified of status change
	ctx.GetStub().SetEvent("RecordStatusUpdated", updated)

	return ctx.GetStub().PutState(txID, updated)
}

// RegisterDevice registers an IoT device on the blockchain
func (s *SmartContract) RegisterDevice(
	ctx contractapi.TransactionContextInterface,
	deviceID string,
	deviceType string,
	edgeCluster string,
	orgMSP string,
) error {

	key := "DEVICE_" + deviceID
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read ledger: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("device %s is already registered", deviceID)
	}

	device := Device{
		DeviceID:    deviceID,
		DeviceType:  deviceType,
		EdgeCluster: edgeCluster,
		OrgMSP:      orgMSP,
		Active:      true,
	}

	deviceJSON, err := json.Marshal(device)
	if err != nil {
		return fmt.Errorf("failed to marshal device: %v", err)
	}

	ctx.GetStub().SetEvent("DeviceRegistered", deviceJSON)
	return ctx.GetStub().PutState(key, deviceJSON)
}

// DeactivateDevice marks a device as inactive — called by IDS when malicious
func (s *SmartContract) DeactivateDevice(
	ctx contractapi.TransactionContextInterface,
	deviceID string,
	reason string,
) error {

	key := "DEVICE_" + deviceID
	deviceJSON, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read device: %v", err)
	}
	if deviceJSON == nil {
		return fmt.Errorf("device %s is not registered", deviceID)
	}

	var device Device
	err = json.Unmarshal(deviceJSON, &device)
	if err != nil {
		return fmt.Errorf("failed to unmarshal device: %v", err)
	}

	device.Active = false

	updated, err := json.Marshal(device)
	if err != nil {
		return fmt.Errorf("failed to marshal device: %v", err)
	}

	ctx.GetStub().SetEvent("DeviceDeactivated", updated)
	return ctx.GetStub().PutState(key, updated)
}

// GetDevice returns a registered device by ID
func (s *SmartContract) GetDevice(
	ctx contractapi.TransactionContextInterface,
	deviceID string,
) (*Device, error) {

	key := "DEVICE_" + deviceID
	deviceJSON, err := ctx.GetStub().GetState(key)
	if err != nil {
		return nil, fmt.Errorf("failed to read device: %v", err)
	}
	if deviceJSON == nil {
		return nil, fmt.Errorf("device %s is not registered", deviceID)
	}

	var device Device
	err = json.Unmarshal(deviceJSON, &device)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal device: %v", err)
	}

	return &device, nil
}

// GetAllDevices returns all registered devices
func (s *SmartContract) GetAllDevices(
	ctx contractapi.TransactionContextInterface,
) ([]*Device, error) {

	iterator, err := ctx.GetStub().GetStateByRange("DEVICE_", "DEVICE_~")
	if err != nil {
		return nil, fmt.Errorf("failed to get devices: %v", err)
	}
	defer iterator.Close()

	var devices []*Device

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		var device Device
		if err := json.Unmarshal(result.Value, &device); err == nil {
			devices = append(devices, &device)
		}
	}

	return devices, nil
}

func (s *SmartContract) GetRecordHistory(
    ctx contractapi.TransactionContextInterface,
    txID string,
) (string, error) {

    iterator, err := ctx.GetStub().GetHistoryForKey(txID)
    if err != nil {
        return "", fmt.Errorf("failed to get history: %v", err)
    }
    defer iterator.Close()

    type HistoryEntry struct {
        TxID      string    `json:"txId"`
        Value     IoTRecord `json:"value"`
        Timestamp string    `json:"timestamp"`
        IsDelete  bool      `json:"isDelete"`
    }

    var history []HistoryEntry

    for iterator.HasNext() {
        result, err := iterator.Next()
        if err != nil {
            return "", err
        }

        var record IoTRecord
        if !result.IsDelete {
            json.Unmarshal(result.Value, &record)
        }

        history = append(history, HistoryEntry{
            TxID:      result.TxId,
            Value:     record,
            Timestamp: fmt.Sprintf("%d", result.Timestamp.Seconds),
            IsDelete:  result.IsDelete,
        })
    }

    historyJSON, err := json.Marshal(history)
    if err != nil {
        return "", err
    }

    return string(historyJSON), nil
}