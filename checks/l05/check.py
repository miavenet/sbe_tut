#!/usr/bin/env python3
# [claim: WP4-CHECKS]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json,concurrent.futures
R=Path(__file__).resolve().parents[2];L=R/'labs/l05'
sys.path.insert(0,str(R/'tools'))
from harness import Run,InfraError,workspace_from_stdin,result,emit_result,generation_argv,compile_argv

def child(run,name,argv,stdin='',timeout=30,cwd=None):
    c=run.start(name,list(map(str,argv)),cwd=cwd or R,stdin=stdin)
    run.until(lambda:c.poll() is not None,timeout=timeout,description=name)
    rc=run.wait(c,timeout=timeout)
    if rc<0:raise InfraError(name+' signal')
    return rc,c.log.read_text(errors='replace')
def prepare(run):
    jobs=[('order',L/'order-v1.xml',{}),('control',L/'control.xml',{}),('tolerant',L/'order-v1.xml',{'sbe.decode.unknown.enum.values':'true'})]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        got=list(pool.map(lambda j:child(run,'gen-'+j[0],generation_argv(run.path/j[0],j[1],checked=True,properties=j[2])),jobs))
    for rc,out in got:
        if rc:raise InfraError(out)
    return [run.path/'order',run.path/'control']
def evaluate(work,run,mode='all',includes=None,name='work'):
    if not (work/'submission.hpp').is_file():return 1,'missing submission.hpp'
    includes=includes or prepare(run)
    rc,out=child(run,name+'-compile',compile_argv(R/'checks/l05/runner.cpp',run.path/(name+'-runner'),includes=[work,L,*includes],checked=True,flags=[str(R/'checks/l05/alloc.cpp'),str(R/'checks/l05/escape.cpp')]))
    if rc:return 1,'compiler diagnostic: '+out[-3000:]
    wd=run.path/name;wd.mkdir()
    rc,out=child(run,name+'-run',[run.path/(name+'-runner'),L/'fixtures',mode],cwd=wd)
    if rc not in (0,1):raise InfraError(out)
    return rc,out.strip()
def main():
    code=2;detail='';path=''
    try:
        work=workspace_from_stdin()
        with Run('wp4-check',parent=R/'manifest/evidence/wp4') as run:
            path=str(run.path.relative_to(R));rc,out=child(run,'setup',[R/'tools/setup.sh','--check'])
            if rc:raise InfraError(out)
            code,detail=evaluate(work,run,sys.argv[1] if len(sys.argv)>1 else 'all')
            if code==0 and (len(sys.argv)==1 or sys.argv[1]=='all'):
                from migration import grade
                ok,why=grade(work/'migration.json');code=0 if ok else 1;detail+='; migration: '+why
    except (InfraError,OSError,KeyboardInterrupt) as e:code,detail=2,str(e)
    emit_result(result(code,[{'id':'L05','pass':code==0,'detail':detail}],artifacts=path,next_action='Repair the named criterion; infrastructure failures are ungraded.'))
    return code
if __name__=='__main__':sys.exit(main())
