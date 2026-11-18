#!/usr/bin/env python3
# [claim: WP3-CHECKS]
import sys
sys.dont_write_bytecode=True
import json,concurrent.futures
from check import R,L,Run,child,prepare,evaluate,InfraError
sys.path.insert(0,str(R/'tools'))
from harness import report_from_output

def main():
    with Run('wp3-acceptance',parent=R/'manifest/evidence/wp3',timeout=40) as run:
        rc,out=child(run,'setup',[R/'tools/setup.sh','--check']);assert rc==0,out
        inc=prepare(run)
        candidates=[('worked',L/'worked',0),('alternative',L/'fixtures/alternative',0),('starter',L/'work',1),('completion',L/'completion',1),('independent',L/'independent',1)]
        candidates += [(p.name,p,1) for p in sorted((L/'fixtures/faults').iterdir())]
        def one(job):
            name,path,want=job;rc,out=evaluate(path,run,includes=inc,name=name)
            assert rc==want,(name,rc,want,out)
            return dict(name=name,exit_code=rc,detail=out)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:outcomes=list(pool.map(one,candidates))
        # Exercise real stdin boundary, not only a Python internal function.
        for name,stdin,want in [('stdin-good','labs/l04/worked\n',0),('stdin-json','{"workspace":"labs/l04/fixtures/alternative"}\n',0),('stdin-bad','labs/l04/work\n',1),('stdin-missing','\n',2)]:
            rc,out=child(run,name,[R/'checks/chk_l04_order.sh'],stdin);assert rc==want,(name,rc,out)
            result=report_from_output(out);assert result['status']=={0:'HIT',1:'MISS',2:'INFRA'}[want]
        (run.path/'outcomes.json').write_text(json.dumps(outcomes,indent=2)+'\n')
    print(json.dumps({'status':'PASS','correct':2,'wrong':len(candidates)-2,'stdin_outcomes':[0,0,1,2],'artifacts':str(run.path.relative_to(R))}));return 0
if __name__=='__main__':sys.exit(main())
