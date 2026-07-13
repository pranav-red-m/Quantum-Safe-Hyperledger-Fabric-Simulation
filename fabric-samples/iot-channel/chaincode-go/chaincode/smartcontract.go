package chaincode

import (
	"crypto/sha256"
	"encoding/hex"
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
	PreviousRecordHash string `json:"previousRecordHash"`
	RecordHash string `json:"recordHash"`
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

func recordKey(txID string) string {
	return "RECORD_" + txID
}

func computeRecordHash(r IoTRecord) string {
	h := sha256.New()
	h.Write([]byte(r.TxID))
	h.Write([]byte("|"))
	h.Write([]byte(r.DeviceID))
	h.Write([]byte("|"))
	h.Write([]byte(r.EdgeCluster))
	h.Write([]byte("|"))
	h.Write([]byte(r.DataHash))
	h.Write([]byte("|"))
	h.Write([]byte(r.Timestamp))
	h.Write([]byte("|"))
	h.Write([]byte(r.Status))
	h.Write([]byte("|"))
	h.Write([]byte(r.PreviousRecordHash))
	return hex.EncodeToString(h.Sum(nil))
}

func (s *SmartContract) SubmitRecord(
	ctx contractapi.TransactionContextInterface,
	txID string,
	deviceID string,
	edgeCluster string,
	dataHash string,
	status string,
) error {

	key := recordKey(txID)
	existing, err := ctx.GetStub().GetState(key)
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
	if err := json.Unmarshal(deviceJSON, &device); err != nil {
		return fmt.Errorf("failed to unmarshal device: %v", err)
	}
	if !device.Active {
		return fmt.Errorf("device %s has been deactivated and cannot submit records", deviceID)
	}

	// Look up this device's current chain tip. No prior record means this
	// is the genesis record for the device's chain.
	latestKey := "LATEST_" + deviceID
	prevHashBytes, err := ctx.GetStub().GetState(latestKey)
	if err != nil {
		return fmt.Errorf("failed to read device chain tip: %v", err)
	}
	previousRecordHash := ""
	if prevHashBytes != nil {
		previousRecordHash = string(prevHashBytes)
	}

	record := IoTRecord{
		TxID:               txID,
		DeviceID:            deviceID,
		EdgeCluster:         edgeCluster,
		DataHash:            dataHash,
		Timestamp:           timestamp,
		Status:              status,
		PreviousRecordHash:  previousRecordHash,
	}
	record.RecordHash = computeRecordHash(record)

	recordJSON, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal record: %v", err)
	}

	if err := ctx.GetStub().SetEvent("SubmitRecord", recordJSON); err != nil {
		return fmt.Errorf("failed to set event: %v", err)
	}

	if err := ctx.GetStub().PutState(key, recordJSON); err != nil {
		return fmt.Errorf("failed to write record: %v", err)
	}

	return ctx.GetStub().PutState(latestKey, []byte(record.RecordHash))
}

func (s *SmartContract) GetRecord(
	ctx contractapi.TransactionContextInterface,
	txID string,
) (*IoTRecord, error) {

	recordJSON, err := ctx.GetStub().GetState(recordKey(txID))
	if err != nil {
		return nil, fmt.Errorf("failed to read record %s: %v", txID, err)
	}
	if recordJSON == nil {
		return nil, fmt.Errorf("record %s does not exist", txID)
	}

	var record IoTRecord
	if err := json.Unmarshal(recordJSON, &record); err != nil {
		return nil, fmt.Errorf("failed to unmarshal record: %v", err)
	}

	return &record, nil
}

func (s *SmartContract) GetAllRecords(
	ctx contractapi.TransactionContextInterface,
) ([]*IoTRecord, error) {

	iterator, err := ctx.GetStub().GetStateByRange("RECORD_", "RECORD_~")
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
		if err := json.Unmarshal(result.Value, &record); err != nil {
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

type ChainVerificationResult struct {
	DeviceID     string `json:"deviceId"`
	Valid        bool   `json:"valid"`
	RecordsCheck int    `json:"recordsChecked"`
	BrokenAtTxID string `json:"brokenAtTxId,omitempty" metadata:",optional"`
	Reason       string `json:"reason,omitempty" metadata:",optional"`
}

func (s *SmartContract) VerifyChain(
	ctx contractapi.TransactionContextInterface,
	deviceID string,
) (*ChainVerificationResult, error) {

	all, err := s.GetAllRecords(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to load records: %v", err)
	}

	var chain []*IoTRecord
	for _, r := range all {
		if r.DeviceID == deviceID {
			chain = append(chain, r)
		}
	}

	result := &ChainVerificationResult{DeviceID: deviceID}

	if len(chain) == 0 {
		result.Valid = false
		result.Reason = "no records found for device"
		return result, nil
	}

	byPrevHash := make(map[string]*IoTRecord, len(chain))
	var genesis *IoTRecord
	genesisCount := 0
	for _, r := range chain {
		if r.PreviousRecordHash == "" {
			genesis = r
			genesisCount++
		} else {
			if _, exists := byPrevHash[r.PreviousRecordHash]; exists {
				result.Valid = false
				result.Reason = "two records share the same PreviousRecordHash — chain forked (likely concurrent writes without proper serialization)"
				return result, nil
			}
			byPrevHash[r.PreviousRecordHash] = r
		}
	}
	if genesisCount != 1 {
		result.Valid = false
		result.Reason = fmt.Sprintf("expected exactly 1 genesis record, found %d", genesisCount)
		return result, nil
	}

	ordered := []*IoTRecord{genesis}
	cur := genesis
	for len(ordered) < len(chain) {
		next, ok := byPrevHash[cur.RecordHash]
		if !ok {
			result.Valid = false
			result.BrokenAtTxID = cur.TxID
			result.Reason = "no record found linking to this hash — chain is broken or incomplete"
			return result, nil
		}
		ordered = append(ordered, next)
		cur = next
	}

	for _, r := range ordered {
		result.RecordsCheck++
		recomputed := computeRecordHash(IoTRecord{
			TxID:               r.TxID,
			DeviceID:           r.DeviceID,
			EdgeCluster:        r.EdgeCluster,
			DataHash:           r.DataHash,
			Timestamp:          r.Timestamp,
			Status:             r.Status,
			PreviousRecordHash: r.PreviousRecordHash,
		})
		if recomputed != r.RecordHash {
			result.Valid = false
			result.BrokenAtTxID = r.TxID
			result.Reason = "stored RecordHash does not match recomputed hash — record contents were altered after submission"
			return result, nil
		}
	}

	result.Valid = true
	return result, nil
}

// SubmitBatch allows edge nodes to submit multiple IoT records in one transaction
func (s *SmartContract) SubmitBatch(
	ctx contractapi.TransactionContextInterface,
	recordsJSON string,
) error {

	var records []IoTRecord
	if err := json.Unmarshal([]byte(recordsJSON), &records); err != nil {
		return fmt.Errorf("failed to parse batch records: %v", err)
	}
	if len(records) == 0 {
		return fmt.Errorf("batch must contain at least one record")
	}

	txTime, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get timestamp: %v", err)
	}
	timestamp := fmt.Sprintf("%d", txTime.Seconds)

	seen := make(map[string]bool, len(records))
	chainTips := make(map[string]string)

	for _, record := range records {
		if seen[record.TxID] {
			return fmt.Errorf("duplicate txID %s within batch", record.TxID)
		}
		seen[record.TxID] = true

		record.Timestamp = timestamp

		key := recordKey(record.TxID)
		existing, err := ctx.GetStub().GetState(key)
		if err != nil {
			return fmt.Errorf("failed to read ledger for %s: %v", record.TxID, err)
		}
		if existing != nil {
			return fmt.Errorf("record %s already exists", record.TxID)
		}

		prevHash, inBatch := chainTips[record.DeviceID]
		if !inBatch {
			latestKey := "LATEST_" + record.DeviceID
			prevHashBytes, err := ctx.GetStub().GetState(latestKey)
			if err != nil {
				return fmt.Errorf("failed to read chain tip for %s: %v", record.DeviceID, err)
			}
			if prevHashBytes != nil {
				prevHash = string(prevHashBytes)
			}
		}

		record.PreviousRecordHash = prevHash
		record.RecordHash = computeRecordHash(record)
		chainTips[record.DeviceID] = record.RecordHash

		recordJSON, err := json.Marshal(record)
		if err != nil {
			return fmt.Errorf("failed to marshal record %s: %v", record.TxID, err)
		}

		if err := ctx.GetStub().PutState(key, recordJSON); err != nil {
			return fmt.Errorf("failed to write record %s: %v", record.TxID, err)
		}
	}

	for deviceID, tipHash := range chainTips {
		latestKey := "LATEST_" + deviceID
		if err := ctx.GetStub().PutState(latestKey, []byte(tipHash)); err != nil {
			return fmt.Errorf("failed to update chain tip for %s: %v", deviceID, err)
		}
	}

	batchEvent := map[string]int{"recordsSubmitted": len(records)}
	batchJSON, err := json.Marshal(batchEvent)
	if err != nil {
		return fmt.Errorf("failed to marshal batch event: %v", err)
	}
	return ctx.GetStub().SetEvent("BatchSubmitted", batchJSON)
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

	if err := ctx.GetStub().SetEvent("AnomalyAlert", alertJSON); err != nil {
		return fmt.Errorf("failed to set event: %v", err)
	}

	if txID != "" {
		rKey := recordKey(txID)
		recordJSON, err := ctx.GetStub().GetState(rKey)
		if err == nil && recordJSON != nil {
			var record IoTRecord
			if json.Unmarshal(recordJSON, &record) == nil {
				record.Status = "flagged"
				updated, _ := json.Marshal(record)
				ctx.GetStub().PutState(rKey, updated)
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

	recordJSON, err := ctx.GetStub().GetState(recordKey(txID))
	if err != nil {
		return fmt.Errorf("failed to read record: %v", err)
	}
	if recordJSON == nil {
		return fmt.Errorf("record %s does not exist", txID)
	}

	key := "CHALLENGE_" + challengeID
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read ledger: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("challenge %s already exists", challengeID)
	}

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

	validTransitions := map[string][]string{
		"confirmed": {"validated"},
		"submitted": {"validated"},
		"validated": {"approved", "flagged"},
		"approved":  {"archived"},
		"flagged":   {"resolved"},
		"resolved":  {"archived"},
	}

	key := recordKey(txID)
	recordJSON, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read record %s: %v", txID, err)
	}
	if recordJSON == nil {
		return fmt.Errorf("record %s does not exist", txID)
	}

	var record IoTRecord
	if err := json.Unmarshal(recordJSON, &record); err != nil {
		return fmt.Errorf("failed to unmarshal record: %v", err)
	}

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
			"invalid transition for record %s: %s -> %s (allowed: %v)",
			txID, record.Status, newStatus, allowedStatuses,
		)
	}

	record.Status = newStatus

	updated, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal updated record: %v", err)
	}

	if err := ctx.GetStub().SetEvent("RecordStatusUpdated", updated); err != nil {
		return fmt.Errorf("failed to set event: %v", err)
	}

	return ctx.GetStub().PutState(key, updated)
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

	iterator, err := ctx.GetStub().GetHistoryForKey(recordKey(txID))
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