export PATH=~/testingmultpeers/fabric-samples/bin:$PATH
export FABRIC_CFG_PATH=~/testingmultpeers/fabric-samples/config/
source ./scripts/envVar.sh
setGlobals 1 
peer channel fetch 0 mychannel.block -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com -c mychannel --tls --cafile "${PWD}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem"
setGlobals 1 && export CORE_PEER_ADDRESS=localhost:8051
peer channel join -b mychannel.block
setGlobals 2 && export CORE_PEER_ADDRESS=localhost:10051
peer channel join -b mychannel.block