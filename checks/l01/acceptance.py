#!/usr/bin/env python3
# [claim: WP1-CHECKS]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'checks/l01'))
from check import setup,grade,Run,child,InfraError,compile_argv
sys.path.insert(0,str(R/'tools'))
from harness import report_from_output

def main():
    total=0
    for lesson in ('l01','l02'):
        with Run('wp1-accept-'+lesson,parent=R/'manifest/evidence/wp1',timeout=25) as run:
            gen,cases=setup(run,lesson)
            candidates=[('worked',R/f'labs/{lesson}/worked',0),('alternative',R/f'labs/{lesson}/fixtures/alternative',0)]+[(n,R/f'labs/{lesson}/{n}',1) for n in ('completion','independent','work')]
            candidates += [(p.name,p,1) for p in sorted((R/f'labs/{lesson}/fixtures/faults').iterdir())]
            # Independent compilations run at normal priority, four at a time.
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures=[pool.submit(grade,run,lesson,work,gen,cases,name=name) for name,work,want in candidates]
                for (name,work,want),future in zip(candidates,futures):
                    got=future.result()
                    (run.path/(name+'.result.json')).write_text(json.dumps(got,indent=2)+'\n')
                    failed=[c['id'] for c in got['criteria'] if not c['pass']]
                    print(f'{lesson}/{name}: expected={want} observed={got["exit_code"]} failed={failed}',flush=True)
                    assert got['exit_code']==want,(name,got)
                    if want:
                        assert 'compile' not in failed and 'runtime' not in failed,(name,got)
                        criterion='layout' if name=='annotation' else 'market-1' if name=='market-width' else 'market-0' if name=='market-endian' else 'alloc-loop' if name=='allocating' else 'audit-0' if name=='retained-view' or (lesson=='l02' and name=='independent') else 'wire-2' if name in ('empty-data','empty-group') else 'wire-0'
                        assert criterion in failed,(name,criterion,got)
                    total+=1
            if lesson=='l02':
                ownership=grade(run,lesson,R/'checks/l02/fixtures/copied-audit-pointer',gen,cases,
                                name='copied-ownership',mode='ownership')
                assert ownership['exit_code']==0 and not any(c['id'].startswith('copied-audit-') for c in ownership['criteria']),ownership
                total+=1
                copied=grade(run,lesson,R/'checks/l02/fixtures/copied-audit-pointer',gen,cases,name='copied-audit-pointer')
                assert copied['exit_code']==1 and 'copied-audit-0' in [c['id'] for c in copied['criteria'] if not c['pass']],copied
                print('l02/copied-audit-pointer: expected=1 observed=1 failed=[copied-audit-0]',flush=True);total+=1
                child(run,'allocator-calibration-compile',compile_argv(R/'checks/l02/allocator_probe.cpp',run.path/'allocator-probe',flags=[str(R/'checks/l02/alloc.cpp'),str(R/'checks/l02/escape.cpp')]))
                _,calibration=child(run,'allocator-calibration',[run.path/'allocator-probe'])
                assert calibration=='NEW_FAMILIES 8\n';total+=1
                disconnected=run.path/'disconnected.cpp'
                disconnected.write_text((R/'checks/l02/alloc.cpp').read_text().replace('measuring=true','measuring=false'))
                got=grade(run,lesson,R/'labs/l02/worked',gen,cases,name='counter-disconnected',allocator=disconnected)
                (run.path/'counter-disconnected.result.json').write_text(json.dumps(got,indent=2)+'\n')
                assert got['exit_code']==1 and [c['id'] for c in got['criteria'] if not c['pass']]==['alloc-control']
                print('l02/counter-disconnected: expected=1 observed=1 failed=[alloc-control]',flush=True);total+=1
            # Malformed references are infrastructure, never learner errors.
            script=R/('checks/chk_l01_wire.sh' if lesson=='l01' else 'checks/chk_l02_buffers.sh')
            rc,out=child(run,'missing-reference',[script],learner=True)
            assert rc==2 and report_from_output(out)['status']=='INFRA';total+=1
    print(json.dumps({'status':'PASS','suite':'WP1','passed':total},sort_keys=True))
if __name__=='__main__':main()
