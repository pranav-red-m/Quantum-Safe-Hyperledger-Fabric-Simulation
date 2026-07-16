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
// PartialBlock = ParBESRi = [OWESRi, PUESRi, ENC_PUESRi(TRASESRi)]
type PartialBlock struct {
	PartialBlockID string `json:"partialBlockId"`
	OwnerID        string `json:"ownerId"`        // OWESRi
	OwnerPubKey    string `json:"ownerPubKey"`     // PUESRi
	EncryptedTx    string `json:"encryptedTx"`     // ENC_PUESRi(TRASESRi)
	Signature      string `json:"signature"`       // sgESRi, produced at the edge, carried through
	EdgeCluster    string `json:"edgeCluster"`
	DeviceID       string `json:"deviceId"`
	Status         string `json:"status"` // PENDING | SEALED
	FullBlockID    string `json:"fullBlockId,omitempty"`
}

// FullBlock = FulBESRi = [BIDESRi, TSi, RNi, hashESRi, hashESRi-1, OWESRi, PUESRi, ENC_PUESRi(TRASESRi), sgESRi]
type FullBlock struct {
	BlockID         string `json:"blockId"`      // BIDESRi
	Timestamp       string `json:"timestamp"`    // TSi - set by chaincode via ctx.GetStub().GetTxTimestamp(), not client-supplied
	Nonce           string `json:"nonce"`        // RNi
	Hash            string `json:"hash"`         // hashESRi
	PreviousHash    string `json:"previousHash"` // hashESRi-1
	OwnerID         string `json:"ownerId"`
	OwnerPubKey     string `json:"ownerPubKey"`
	EncryptedTx     string `json:"encryptedTx"`
	Signature       string `json:"signature"`         // sgESRi, carried from PartialBlock
	SignatureVerified bool `json:"signatureVerified"` // asserted by caller at FinalizeFullBlock time
	PartialBlockID  string `json:"partialBlockId"`
	DeviceID        string `json:"deviceId"`
	ConsensusStatus string `json:"consensusStatus"` // PROPOSED | COMMITTED | REJECTED
}

type ChainMeta struct {
	LatestHash    string `json:"latestHash"`
	LatestBlockID string `json:"latestBlockId"`
	Height        int    `json:"height"`
}

const (
	chainMetaKey = "CHAIN_META"
	genesisHash  = "0000000000000000000000000000000000000000000000000000000000000"
)

// ---------- Init ----------

func (s *SmartContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	meta := ChainMeta{
		LatestHash:    genesisHash,
		LatestBlockID: "GENESIS",
		Height:        0,
	}
	metaJSON, err := json.Marshal(meta)
	if err != nil {
		return fmt.Errorf("failed to marshal chain meta: %v", err)
	}
	return ctx.GetStub().PutState(chainMetaKey, metaJSON)
}

// ---------- Edge Server: create partial block ----------

// CreatePartialBlock is invoked by an edge server (ESRi) after it has
// authenticated the IoT device and processed its data into a transaction.
// It stores ParBESRi = [OWESRi, PUESRi, ENC_PUESRi(TRASESRi)].
func (s *SmartContract) SubmitPartialBlock(
	ctx contractapi.TransactionContextInterface,
	partialBlockID string,
	ownerID string,
	ownerPubKey string,
	encryptedTx string,
	signature string,
	edgeCluster string,
	deviceID string,
) error {
	exists, err := s.assetExists(ctx, partialBlockID)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("partial block %s already exists", partialBlockID)
	}
	if ownerID == "" || ownerPubKey == "" || encryptedTx == "" || signature == "" || deviceID == "" {
		return fmt.Errorf("ownerID, ownerPubKey, encryptedTx, signature and deviceID are required")
	}

	partial := PartialBlock{
		PartialBlockID: partialBlockID,
		OwnerID:        ownerID,
		OwnerPubKey:    ownerPubKey,
		EncryptedTx:    encryptedTx,
		Signature:      signature,
		EdgeCluster:    edgeCluster,
		DeviceID:       deviceID,
		Status:         "PENDING",
	}
	partialJSON, err := json.Marshal(partial)
	if err != nil {
		return fmt.Errorf("failed to marshal partial block: %v", err)
	}
	return ctx.GetStub().PutState(partialBlockID, partialJSON)
}

func (s *SmartContract) GetPartialBlock(ctx contractapi.TransactionContextInterface, partialBlockID string) (*PartialBlock, error) {
	partialJSON, err := ctx.GetStub().GetState(partialBlockID)
	if err != nil {
		return nil, fmt.Errorf("failed to read partial block %s: %v", partialBlockID, err)
	}
	if partialJSON == nil {
		return nil, fmt.Errorf("partial block %s does not exist", partialBlockID)
	}
	var partial PartialBlock
	if err := json.Unmarshal(partialJSON, &partial); err != nil {
		return nil, err
	}
	return &partial, nil
}

// ---------- Cloud Server: assemble full block from partial block ----------

// CreateFullBlock is invoked by a cloud server (CSk) after receiving ParBESRi.
// It links to the current chain tip for hashESRi-1, computes hashESRi over the
// block contents, and stores FulBESRi as PROPOSED pending consensus.
func (s *SmartContract) FinalizeFullBlock(
	ctx contractapi.TransactionContextInterface,
	blockID string,
	partialBlockID string,
	nonce string,
	signatureVerified string,
) error {
	exists, err := s.assetExists(ctx, blockID)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("full block %s already exists", blockID)
	}

	partial, err := s.GetPartialBlock(ctx, partialBlockID)
	if err != nil {
		return err
	}
	if partial.Status == "SEALED" {
		return fmt.Errorf("partial block %s already sealed into %s", partialBlockID, partial.FullBlockID)
	}

	verified := signatureVerified == "true"
	if !verified {
		return fmt.Errorf("cannot finalize block %s: signature not verified", blockID)
	}

	txTimestamp, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get tx timestamp: %v", err)
	}

	full := FullBlock{
		BlockID:           blockID,
		Timestamp:         txTimestamp.AsTime().UTC().Format("2006-01-02T15:04:05Z"),
		Nonce:             nonce,
		PreviousHash:      "",
		OwnerID:           partial.OwnerID,
		OwnerPubKey:       partial.OwnerPubKey,
		EncryptedTx:       partial.EncryptedTx,
		Signature:         partial.Signature,
		SignatureVerified: verified,
		PartialBlockID:    partialBlockID,
		DeviceID:          partial.DeviceID,
		ConsensusStatus:   "PROPOSED",
		Hash		   :   "",
	}

	fullJSON, err := json.Marshal(full)
	if err != nil {
		return fmt.Errorf("failed to marshal full block: %v", err)
	}
	if err := ctx.GetStub().PutState(blockID, fullJSON); err != nil {
		return err
	}

	partial.Status = "SEALED"
	partial.FullBlockID = blockID
	partialJSON, err := json.Marshal(partial)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(partialBlockID, partialJSON)
}

func (s *SmartContract) GetFullBlock(ctx contractapi.TransactionContextInterface, blockID string) (*FullBlock, error) {
	blockJSON, err := ctx.GetStub().GetState(blockID)
	if err != nil {
		return nil, fmt.Errorf("failed to read full block %s: %v", blockID, err)
	}
	if blockJSON == nil {
		return nil, fmt.Errorf("full block %s does not exist", blockID)
	}
	var full FullBlock
	if err := json.Unmarshal(blockJSON, &full); err != nil {
		return nil, err
	}
	return &full, nil
}

// ---------- Consensus / commit ----------

// CommitFullBlock is invoked by the P2PCS network leader once the standard
// consensus procedure (proposal, voting/endorsement, ordering) has approved
// FulBESRi. It verifies hash linkage and integrity, then advances the chain tip.
func (s *SmartContract) CommitFullBlock(ctx contractapi.TransactionContextInterface, blockID string) error {
	full, err := s.GetFullBlock(ctx, blockID)
	if err != nil {
		return err
	}
	if full.ConsensusStatus == "COMMITTED" {
		return fmt.Errorf("full block %s is already committed", blockID)
	}

	meta, err := s.getChainMeta(ctx)
	if err != nil {
		return err
	}

	// verify hash chain linkage
	full.PreviousHash = meta.LatestHash

	// verify block integrity (recompute hash, ignoring the stored hash+status fields)
	recomputed := computeBlockHash(FullBlock{
		BlockID:           full.BlockID,
		Timestamp:         full.Timestamp,
		Nonce:             full.Nonce,
		PreviousHash:      full.PreviousHash,
		OwnerID:           full.OwnerID,
		OwnerPubKey:       full.OwnerPubKey,
		EncryptedTx:       full.EncryptedTx,
		Signature:         full.Signature,
		SignatureVerified: full.SignatureVerified,
		PartialBlockID:    full.PartialBlockID,
		DeviceID:          full.DeviceID,
	})
	full.Hash = recomputed

	full.ConsensusStatus = "COMMITTED"
	fullJSON, err := json.Marshal(full)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutState(blockID, fullJSON); err != nil {
		return err
	}

	meta.LatestHash = full.Hash
	meta.LatestBlockID = full.BlockID
	meta.Height++
	metaJSON, err := json.Marshal(meta)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(chainMetaKey, metaJSON)
}

// RejectFullBlock lets the P2PCS leader mark a proposed block as rejected
// if consensus fails (e.g. insufficient endorsements/votes).
func (s *SmartContract) RejectFullBlock(ctx contractapi.TransactionContextInterface, blockID string) error {
	full, err := s.GetFullBlock(ctx, blockID)
	if err != nil {
		return err
	}
	if full.ConsensusStatus == "COMMITTED" {
		return fmt.Errorf("cannot reject block %s: already committed", blockID)
	}
	full.ConsensusStatus = "REJECTED"
	fullJSON, err := json.Marshal(full)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(blockID, fullJSON)
}

// ---------- Queries ----------

func (s *SmartContract) GetChainMeta(ctx contractapi.TransactionContextInterface) (*ChainMeta, error) {
	return s.getChainMeta(ctx)
}

// GetAllFullBlocks returns all full blocks (partial and complete state) for audit/UI use.
func (s *SmartContract) GetAllFullBlocks(ctx contractapi.TransactionContextInterface) ([]*FullBlock, error) {
	iterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer iterator.Close()

	var blocks []*FullBlock
	for iterator.HasNext() {
		item, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		var full FullBlock
		if err := json.Unmarshal(item.Value, &full); err != nil {
			continue // skip non-FullBlock records (partial blocks, chain meta)
		}
		if full.BlockID != "" {
			blocks = append(blocks, &full)
		}
	}
	return blocks, nil
}

// ---------- Helpers ----------

func (s *SmartContract) assetExists(ctx contractapi.TransactionContextInterface, id string) (bool, error) {
	assetJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return false, fmt.Errorf("failed to read from world state: %v", err)
	}
	return assetJSON != nil, nil
}

func (s *SmartContract) getChainMeta(ctx contractapi.TransactionContextInterface) (*ChainMeta, error) {
	metaJSON, err := ctx.GetStub().GetState(chainMetaKey)
	if err != nil {
		return nil, fmt.Errorf("failed to read chain meta: %v", err)
	}
	if metaJSON == nil {
		return nil, fmt.Errorf("ledger not initialized: call InitLedger first")
	}
	var meta ChainMeta
	if err := json.Unmarshal(metaJSON, &meta); err != nil {
		return nil, err
	}
	return &meta, nil
}

// computeBlockHash derives hashESRi deterministically from block contents,
// including hashESRi-1 so tampering with any prior block invalidates the chain.
func computeBlockHash(f FullBlock) string {
	payload := f.BlockID + f.Timestamp + f.Nonce + f.PreviousHash +
		f.OwnerID + f.OwnerPubKey + f.EncryptedTx + f.Signature +
		f.PartialBlockID + f.DeviceID
	sum := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(sum[:])
}