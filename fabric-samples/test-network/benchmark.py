import argparse,csv,json,os,statistics,subprocess,time,uuid
from dataclasses import dataclass,field

TEST_NETWORK_DIR=os.path.expanduser("~/testingmultpeers/fabric-samples/test-network")
ORG_BASE=os.path.join(TEST_NETWORK_DIR,"organizations")
FABRIC_BIN_DIR=os.path.expanduser("~/testingmultpeers/fabric-samples/bin")
FABRIC_CFG_PATH=os.path.expanduser("~/testingmultpeers/fabric-samples/config")
CHANNEL="mychannel"
CC_NAME="iotcc"
ORDERER_ADDR="localhost:7050"
ORDERER_TLS_HOSTNAME="orderer.example.com"
ORDERER_CA=os.path.join(ORG_BASE,"ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem")
PEERS=[
("localhost:7051",os.path.join(ORG_BASE,"peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt")),
("localhost:9051",os.path.join(ORG_BASE,"peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt")),
]
CORE_PEER_LOCALMSPID="Org1MSP"
CORE_PEER_TLS_ROOTCERT_FILE=os.path.join(ORG_BASE,"peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem")
CORE_PEER_MSPCONFIGPATH=os.path.join(ORG_BASE,"peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp")
CORE_PEER_ADDRESS="localhost:7051"

def env():
 e=os.environ.copy();e["FABRIC_CFG_PATH"]=FABRIC_CFG_PATH;e["PATH"]=FABRIC_BIN_DIR+os.pathsep+e.get("PATH","");e["CORE_PEER_TLS_ENABLED"]="true";e["CORE_PEER_LOCALMSPID"]=CORE_PEER_LOCALMSPID;e["CORE_PEER_TLS_ROOTCERT_FILE"]=CORE_PEER_TLS_ROOTCERT_FILE;e["CORE_PEER_MSPCONFIGPATH"]=CORE_PEER_MSPCONFIGPATH;e["CORE_PEER_ADDRESS"]=CORE_PEER_ADDRESS;return e
def invoke(fn,args):
 cmd=["peer","chaincode","invoke","-o",ORDERER_ADDR,"--ordererTLSHostnameOverride",ORDERER_TLS_HOSTNAME,"--tls","--cafile",ORDERER_CA,"-C",CHANNEL,"-n",CC_NAME,"--waitForEvent"]
 for a,c in PEERS: cmd+=["--peerAddresses",a,"--tlsRootCertFiles",c]
 cmd+=["-c",json.dumps({"function":fn,"Args":args})]
 s=time.perf_counter();r=subprocess.run(cmd,capture_output=True,text=True,env=env());t=(time.perf_counter()-s)*1000
 if r.returncode: raise RuntimeError(r.stderr.strip())
 return t
def query(fn,args):
 cmd=["peer","chaincode","query","-C",CHANNEL,"-n",CC_NAME,"-c",json.dumps({"function":fn,"Args":args})]
 s=time.perf_counter();r=subprocess.run(cmd,capture_output=True,text=True,env=env());t=(time.perf_counter()-s)*1000
 if r.returncode: raise RuntimeError(r.stderr.strip())
 return t,r.stdout

@dataclass
class Result:
 name:str
 lat:list=field(default_factory=list)
 fail:int=0
 def add(self,v): self.lat.append(v)
 def summary(self):
  d=sorted(self.lat);n=len(d)
  if not n:return {}
  return dict(min=min(d),max=max(d),mean=statistics.mean(d),median=statistics.median(d),
              p95=d[min(int(.95*(n-1)),n-1)],p99=d[min(int(.99*(n-1)),n-1)],stdev=statistics.pstdev(d) if n>1 else 0)

def build():
 run=uuid.uuid4().hex[:8];pbs={};fbs={}
 def submit(i):
  pid = f"PB-{uuid.uuid4().hex}"
  dev = f"DEV-{uuid.uuid4().hex[:8]}"
  t=invoke("SubmitPartialBlock",[pid,"Owner1","PubKey","EncryptedTx","Signature","EdgeA",dev]);pbs[i]=pid;return t
 def finalize(i):
  if i not in pbs: submit(i)
  bid = f"FB-{uuid.uuid4().hex}"
  t=invoke("FinalizeFullBlock",[bid,pbs[i],str(i),"true"]);fbs[i]=bid;return t
 def commit(i):
  if i not in fbs: finalize(i)
  return invoke("CommitFullBlock",[fbs[i]])
 def gp(i): return query("GetPartialBlock",[pbs[i]])[0]
 def gf(i): return query("GetFullBlock",[fbs[i]])[0]
 def gall(i): return query("GetAllFullBlocks",[])[0]
 def meta(i): return query("GetChainMeta",[])[0]
 def e2e(i): return submit(i)+finalize(i)+commit(i)
 return {"submit":submit,"finalize":finalize,"commit":commit,"get_partial":gp,"get_full":gf,"get_all":gall,"meta":meta,"e2e":e2e}

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--iterations",type=int,default=20)
 ap.add_argument("--csv")
 ap.add_argument("--functions",nargs="+",default=["submit","finalize","commit","get_partial","get_full","get_all","meta","e2e"])
 a=ap.parse_args()
 calls=build();rows=[]
 for fn in a.functions:
  r=Result(fn);print(f"\n== {fn} ==")
  for i in range(a.iterations):
   try:
    x=calls[fn](i);r.add(x);rows.append((fn,i,x));print(i+1,round(x,2),"ms")
   except Exception as e:
    r.fail+=1;rows.append((fn,i,"ERROR"))
    print("FAIL",e)
  s=r.summary()
  if s:
   print(f"mean={s['mean']:.2f} median={s['median']:.2f} p95={s['p95']:.2f} max={s['max']:.2f} stdev={s['stdev']:.2f}")
 if a.csv:
  with open(a.csv,"w",newline="") as f:
   csv.writer(f).writerows([["function","iteration","latency_ms"],*rows])
  print("CSV written:",a.csv)
