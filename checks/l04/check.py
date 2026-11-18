#!/usr/bin/env python3
# [claim: WP3-CHECKS]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json,concurrent.futures
R=Path(__file__).resolve().parents[2];L=R/'labs/l04'
sys.path.insert(0,str(R/'tools'))
from harness import Run,InfraError,workspace_from_stdin,result,emit_result,generation_argv,compile_argv

def child(run,name,argv,stdin='',timeout=30):
    c=run.start(name,list(map(str,argv)),cwd=R,stdin=stdin)
    run.until(lambda:c.poll() is not None,timeout=timeout,description=name)
    rc=run.wait(c,timeout=timeout)
    if rc<0:raise InfraError(name+' terminated by signal')
    return rc,c.log.read_text(errors='replace')
def prepare(run):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[('order',L/'order-v1.xml'),('nested',L/'nested.xml')]
        got=list(pool.map(lambda j:child(run,'gen-'+j[0],generation_argv(run.path/j[0],j[1],checked=True)),jobs))
    for rc,out in got:
        if rc:raise InfraError(out)
    return [run.path/'order',run.path/'nested']
def evaluate(work,run,mode='all',includes=None,name='work'):
    if not (work/'submission.hpp').is_file():return 1,'missing submission.hpp'
    includes=includes or prepare(run)
    rc,out=child(run,name+'-compile',compile_argv(R/'checks/l04/runner.cpp',run.path/(name+'-runner'),includes=[work,L,*includes],checked=True))
    if rc:return 1,'compiler diagnostic: '+out[-2500:]
    rc,out=child(run,name+'-run',[run.path/(name+'-runner'),L/'fixtures',mode])
    if rc not in (0,1):raise InfraError(out)
    return rc,out.strip()
def main():
    code=2;detail='';path=''
    try:
        work=workspace_from_stdin()
        with Run('wp3-check',parent=R/'manifest/evidence/wp3') as run:
            path=str(run.path.relative_to(R))
            rc,out=child(run,'setup',[R/'tools/setup.sh','--check'])
            if rc:raise InfraError(out)
            code,detail=evaluate(work,run,sys.argv[1] if len(sys.argv)>1 else 'all')
    except (InfraError,OSError,KeyboardInterrupt) as e:code,detail=2,str(e)
    emit_result(result(code,[{'id':'L04','pass':code==0,'detail':detail}],artifacts=path))
    return code
if __name__=='__main__':sys.exit(main())
