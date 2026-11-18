#!/usr/bin/env python3
# [claim: WP4-MIGRATION] [claim: WP4-CHECKS]
"""Structural contract gate; narrative meaning is explicitly bullet self-report."""
import sys
sys.dont_write_bytecode=True
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from harness import workspace_from_stdin,result,emit_result,InfraError

def _grade(path):
    try:d=json.loads(path.read_text())
    except (OSError,ValueError):return False,'supply valid migration.json'
    if not isinstance(d,dict):return False,'migration.json must be an object'
    fixed={'proposal_only':True,'envelope_bytes':32,'payload_limit':1408,'reserved':0,'msg_type':60000,'msg_type_status':'proposed-unallocated','schema_id':91,'template_id':1,'versions':[0,1,2],'version_2_policy':'fixed-optional-tails-only','source_exponent':-2,'target_scale':10000,'conversion_multiplier':100,'overflow_policy':'reject-before-multiply'}
    for k,v in fixed.items():
        if type(d.get(k)) is not type(v) or d[k]!=v:return False,'repair '+k
    for k in ('null_policy','legacy_reader','archive_policy','deployment','dedup'):
        if not isinstance(d.get(k),str) or not d[k].strip():return False,'write rationale: '+k
    required={'price','quantity','side','stopPrice','symbol','orderId','flags'}
    if not isinstance(d.get('mapped'),dict) or set(d['mapped'])!=required or not all(isinstance(v,str) and v.strip() for v in d['mapped'].values()):return False,'mapped fields'
    omitted={'timestamps','external identifiers','execution instructions','venue extensions'}
    if not isinstance(d.get('omitted'),list) or len(d['omitted'])!=len(omitted) or not all(isinstance(x,str) for x in d['omitted']) or set(d['omitted'])!=omitted:return False,'omitted fields inventory'
    toy={'fills','trader','note','clientTag'}
    if not isinstance(d.get('toy_only'),list) or len(d['toy_only'])!=len(toy) or not all(isinstance(x,str) for x in d['toy_only']) or set(d['toy_only'])!=toy:return False,'toy-only inventory'
    want={'frame_codec':'CODE','replay_fixture':'CODE','frame_layout':'SPEC','leader_election':'PLAN','snapshots':'PLAN'}
    if d.get('status')!=want:return False,'CODE/SPEC/PLAN distinction'
    if d.get('seams')!={'encode':'labs/l05/codec.hpp','validate':'labs/l05/worked/submission.hpp','record':'checks/l05/runner.cpp','replay':'checks/l05/runner.cpp'}:return False,'course seam inventory'
    return True,'structural contract passes; review rationale against L05-T2 key'
def grade(path):
    try:return _grade(path)
    except (TypeError,KeyError,ValueError):return False,"malformed migration structure"
def main():
    try:
        work=workspace_from_stdin();ok,why=grade(work/'migration.json');code=0 if ok else 1
    except (InfraError,OSError) as e:code,why=2,str(e)
    emit_result(result(code,[{'id':'migration-structure','pass':code==0,'detail':why}]));return code
if __name__=='__main__':sys.exit(main())
