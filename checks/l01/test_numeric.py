#!/usr/bin/env python3
# [claim: WP1-NUMERIC]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'checks/l01'))
from check import Run,child
from numeric import EXPECTED
sys.path.insert(0,str(R/'tools'))
from harness import report_from_output
n=0
with Run('wp1-numeric',parent=R/'manifest/evidence/wp1',timeout=10) as run:
    for mode in ('completion','recall'):
        expected=EXPECTED[mode];bad=json.loads(json.dumps(expected));bad[next(iter(bad))]+=1
        tests=[(json.dumps(expected),0),(json.dumps(dict(reversed(list(expected.items())))),0),(json.dumps(bad),1),('I am sure: 34 and 70',1),('',2),('{"header":8,"header":8}',1)]
        if mode=='recall':
            bad=json.loads(json.dumps(expected));bad['offsets'][0]=False;tests.append((json.dumps(bad),1))
        script=R/('checks/l01/chk_complete_offsets.sh' if mode=='completion' else 'checks/l01/chk_recall_offsets.sh')
        for answer,want in tests:
            rc,out=child(run,'case-'+str(n),[script],stdin=answer,learner=True)
            assert rc==want and report_from_output(out)['exit_code']==want,(mode,answer,rc,out)
            assert ('\nSETUP PROBLEM\n' if want==2 else '\nHIT\n' if want==0 else '\nMISS\n') in out
            if answer==json.dumps(bad):
                assert 'expected' in out and 'actual' in out,out
            n+=1
print(json.dumps({'status':'PASS','numeric_cases':n},sort_keys=True))
