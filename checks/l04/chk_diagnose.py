#!/usr/bin/env python3
# [claim: WP3-DIAGANSWER]
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from harness import result,emit_result
EXPECTED={'offset':46,'field':'batches[0].label.length','action':'reject-before-commit'}
def exact(a,b):
    if type(a) is not type(b):return False
    if isinstance(b,dict):return a.keys()==b.keys() and all(exact(a[k],b[k]) for k in b)
    if isinstance(b,list):return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b))
    return a==b
def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise ValueError('duplicate key')
        d[k]=v
    return d
raw=sys.stdin.read(65537)
if not raw.strip() or len(raw)>65536:
    emit_result(result(2,[{'id':'input','pass':False,'detail':'missing/oversized answer; no grade'}]));sys.exit(2)
try:
    ok=exact(json.loads(raw,object_pairs_hook=unique),EXPECTED)
    code=0 if ok else 1
except (ValueError,TypeError):code=1
emit_result(result(code,[{'id':'Capture diagnosis','pass':code==0,'detail':'Trace the first affected field and reject before committing a result.'}]))
sys.exit(code)
