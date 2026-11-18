#!/usr/bin/env python3
# [claim: WP4-CHECKS]
import sys
sys.dont_write_bytecode=True
import json,concurrent.futures,tempfile
from check import R,L,Run,child,prepare,evaluate,InfraError,compile_argv
sys.path.insert(0,str(R/'tools'))
from harness import report_from_output
from migration import grade
from oracle import build

def main():
    with Run('wp4-acceptance',parent=R/'manifest/evidence/wp4',timeout=45) as run:
        rc,out=child(run,'setup',[R/'tools/setup.sh','--check']);assert rc==0,out
        inc=prepare(run);build(run.path/'oracle')
        rc,out=child(run,'hash-compile',compile_argv(R/'checks/l05/checksum_probe.cpp',run.path/'hash-probe',includes=[L]));assert rc==0,out
        rc,out=child(run,'hash-probe',[run.path/'hash-probe']);assert rc==0,out
        vectors=json.loads((run.path/'oracle/vectors.json').read_text())
        assert [list(map(int,line.split())) for line in out.splitlines()]==[[len(bytes.fromhex(v['hex'])),v['hash']] for v in vectors]
        assert (run.path/'oracle/envelope.bin').read_bytes()==(L/'fixtures/envelope.bin').read_bytes()
        candidates=[('worked',L/'worked',0),('alternative',L/'fixtures/alternative',0),('starter',L/'work',1),('completion',L/'completion',1),('independent',L/'independent',1)]
        candidates += [(p.name,p,1) for p in sorted((L/'fixtures/faults').iterdir())]
        def one(job):
            name,path,want=job;rc,out=evaluate(path,run,includes=inc,name=name)
            assert rc==want,(name,rc,want,out)
            if want:assert 'FAIL criterion=' in out,(name,'negative fixture must compile/run',out)
            return dict(name=name,exit_code=rc,detail=out)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:outcomes=list(pool.map(one,candidates))
        rc,out=evaluate(L/'worked',run,'frame',inc,'frame-reference');assert rc==0,(rc,out)
        rc,out=evaluate(L/'enum-work',run,'frame',inc,'frame-unknown-fallback');assert rc==1 and 'FAIL criterion=' in out,(rc,out)
        rc,out=evaluate(L/'worked',run,includes=[run.path/'tolerant',run.path/'control'],name='tolerant-application');assert rc==0,out
        for tolerant in (False,True):
            dest=run.path/('enum-'+str(tolerant));rc,out=child(run,dest.name+'-compile',compile_argv(R/'checks/l05/enum_probe.cpp',dest,includes=[run.path/('tolerant' if tolerant else 'order')],flags=['-DTOLERANT'] if tolerant else []));assert rc==0,out
            rc,out=child(run,dest.name,[dest]);assert rc==0,out
            assert ('SBE_UNKNOWN' if tolerant else 'unknown throws:') in out
        rc,out=child(run,'alloc-families-compile',compile_argv(R/'checks/l05/allocator_probe.cpp',run.path/'alloc-probe',flags=[str(R/'checks/l05/alloc.cpp'),str(R/'checks/l05/escape.cpp')]))
        assert rc==0,out
        rc,out=child(run,'alloc-families',[run.path/'alloc-probe']);assert rc==0 and 'NEW_FAMILIES 8' in out,out
        for name,stdin,want in [('stdin-good','labs/l05/worked\n',0),('stdin-json','{"workspace":"labs/l05/fixtures/alternative"}\n',0),('stdin-bad','labs/l05/work\n',1),('stdin-missing','\n',2)]:
            rc,out=child(run,name,[R/'checks/chk_l05_sequencer.sh'],stdin);assert rc==want,(name,rc,out)
            assert report_from_output(out)['status']=={0:'HIT',1:'MISS',2:'INFRA'}[want]
        assert grade(L/'worked/migration.json')[0] and not grade(L/'work/migration.json')[0]
        base=json.loads((L/'worked/migration.json').read_text());migration_attacks=[]
        for key,val in [('reserved',1),('conversion_multiplier',1000000),('proposal_only',False),('msg_type',1),('payload_limit',65535),('versions',[0,1,2,3]),('status',{})]:
            d=dict(base);d[key]=val;p=run.path/(key+'.json');p.write_text(json.dumps(d));assert not grade(p)[0];migration_attacks.append(key)
        (run.path/'outcomes.json').write_text(json.dumps(outcomes,indent=2)+'\n')
    print(json.dumps({'status':'PASS','correct':2,'wrong':len(candidates)-2,'stdin_outcomes':[0,0,1,2],'enum_modes':2,'allocator_families':8,'migration_attacks':migration_attacks,'artifacts':str(run.path.relative_to(R))}));return 0
if __name__=='__main__':sys.exit(main())
