#!/usr/bin/env python3
# [claim: WP1-NUMERIC] [claim: WP1-WIRE]
"""Documented structured-answer ABI: exact JSON object for the selected card."""
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from harness import result,emit_result
EXPECTED={
 'completion':{'root_bytes':34,'group_at':42,'entry_bytes':12,'trader_at':70},
 'recall':{'header':8,'root':34,'body':71,'packet':79,'offsets':[0,8,16,20,24,32,33]}
}
def exact(a,b):
    if type(a) is not type(b):return False
    if isinstance(b,dict):return a.keys()==b.keys() and all(exact(a[k],b[k]) for k in b)
    if isinstance(b,list):return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b))
    return a==b

def differences(actual, expected, path=''):
    if isinstance(expected, dict) and isinstance(actual, dict):
        out=[]
        for key in expected:
            name=f'{path}.{key}' if path else key
            out += differences(actual[key],expected[key],name) if key in actual else [f'{name}: missing; expected {expected[key]!r}']
        out += [f'{path + "." if path else ""}{key}: unexpected field, actual {actual[key]!r}' for key in actual if key not in expected]
        return out
    if isinstance(expected,list) and isinstance(actual,list):
        out=[]
        for i,value in enumerate(expected):
            name=f'{path}[{i}]'
            out += differences(actual[i],value,name) if i<len(actual) else [f'{name}: missing; expected {value!r}']
        out += [f'{path}[{i}]: unexpected value {actual[i]!r}' for i in range(len(expected),len(actual))]
        return out
    return [] if exact(actual,expected) else [f'{path}: expected {expected!r}, actual {actual!r}']

def main():
    if len(sys.argv)!=2 or sys.argv[1] not in EXPECTED:
        emit_result(result(2,[{'id':'configuration','pass':False,'detail':'unknown numeric card'}]));return 2
    raw=sys.stdin.read(65537)
    if not raw.strip() or len(raw)>65536:
        emit_result(result(2,[{'id':'input','pass':False,'detail':'missing/oversized answer; no grade'}]));return 2
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate key')
            d[k]=v
        return d
    try:actual=json.loads(raw,object_pairs_hook=unique);parse_error=None
    except ValueError as exc:actual=None;parse_error='not valid JSON: '+str(exc)
    ok=exact(actual,EXPECTED[sys.argv[1]])
    detail='exact numeric values/types/keys match' if ok else parse_error or '; '.join(differences(actual,EXPECTED[sys.argv[1]]))
    res=result(0 if ok else 1,[{'id':'numeric-layout','pass':ok,'detail':detail}],next_action='Separately self-grade the explanation against its Key; numeric HIT alone does not grade why.')
    emit_result(res);return res['exit_code']
if __name__=='__main__':sys.exit(main())
