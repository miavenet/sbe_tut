#!/usr/bin/env python3
# [claim: WP2-CHECKS]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json,struct,concurrent.futures
R=Path(__file__).resolve().parents[2];L=R/'labs/l03'
sys.path.insert(0,str(R/'tools'))
from harness import Run,InfraError,workspace_from_stdin,result,emit_result,generation_argv,compile_argv,atomic_json
from evolution import compatible,exercise_contract

def child(run,name,argv,stdin='',timeout=30):
    c=run.start(name,list(map(str,argv)),cwd=R,stdin=stdin)
    run.until(lambda:c.poll() is not None,timeout=timeout,description=name+' completion')
    code=run.wait(c,timeout=timeout)
    if code<0:raise InfraError(name+': terminated by signal '+str(code))
    return code,c.log.read_text(errors='replace')

def oracle(k,v):
    n=2 if k==0 else k-1
    b=struct.pack('<HHHHQqIi8scB',34+4*v,1,91,v,0x1122334455667788+k,12345-20000*k,100+k,0 if k%2 else -2147483648,b'BONDXYZQ' if k%2 else b'AAPL\0\0\0\0',b'S' if k%2 else b'B',(1 if k%2==0 else 2)+(4 if k==0 else 0))
    if v:b+=struct.pack('<I',0xffffffff if k==3 else 0xcafebabe+k)
    b+=struct.pack('<HH',12+v,n)
    for j in range(n):
        b+=struct.pack('<qI',12340+5*j+k,60 if j==0 else 40)
        if v:b+=bytes([7+2*j])
    for s in ((b'pat' if k==0 else b'' if k==1 else b'auditor'),(b'hi' if k==0 else b'archive payload' if k==2 else b'')):
        b+=struct.pack('<H',len(s))+s
    return b

def fixtures(path):
    path.mkdir()
    for k in range(4):
        for v in range(2):(path/f'case-{k}-v{v}.bin').write_bytes(oracle(k,v))
    for v in range(2):
        if oracle(0,v)!=(L/f'fixtures/order-v{v}.bin').read_bytes():raise InfraError('immutable Java fixture disagrees with independent oracle')
    # Synthetic compatible v2: four unknown root bytes, two unknown bytes per entry.
    b=oracle(3,1);future=struct.pack('<HHHH',42,1,91,2)+b[8:46]+b'ROOT'+struct.pack('<HH',15,2)
    for j in range(2):future+=b[50+j*13:63+j*13]+bytes([0xD0+j,0xE0+j])
    future+=b[76:];(path/'future.bin').write_bytes(future)
    tape=b''
    for frame in (oracle(2,0),oracle(0,1),future):tape+=struct.pack('<I',len(frame))+frame
    (path/'archive.bin').write_bytes(tape)

def evaluate(work,run,mode='all',prepared=None):
    if not (work/'submission.hpp').is_file() or not (work/'order-v1.xml').is_file():
        return 1,'missing submission.hpp or order-v1.xml'
    try:errors=compatible(L/'order-v0.xml',work/'order-v1.xml')
    except Exception as e:return 1,'schema parse: '+str(e)
    if errors:return 1,'; '.join(errors)
    if not exercise_contract(work/'order-v1.xml',L/'order-v1.xml'):
        return 1,'exercise contract: implement only the supplied v1 fields/groups/data'
    if prepared is None:
        jobs=[('v0',L/'order-v0.xml'),('v1',work/'order-v1.xml')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda job:child(run,'gen-'+job[0],generation_argv(run.path/job[0],job[1])),jobs))
        for rc,out in results:
            if rc:return 1,'schema generation: '+out[-2000:]
        prepared=(run.path/'v0',run.path/'v1')
    inc=[work,L,*prepared]
    rc,out=child(run,'compile',compile_argv(R/'checks/l03/runner.cpp',run.path/'runner',includes=inc))
    if rc<0:raise InfraError('compiler signal')
    if rc:return 1,'compilation: '+out[-3000:]
    fixtures(run.path/'fixtures')
    rc,out=child(run,'execute',[run.path/'runner',run.path/'fixtures',mode])
    if rc not in (0,1):raise InfraError('runner unexpected exit '+str(rc))
    return rc,out

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'all';code=2;detail='';path=''
    try:
        work=workspace_from_stdin()
        with Run('wp2-check',parent=R/'manifest/evidence/wp2',timeout=30) as run:
            path=str(run.path.relative_to(R))
            rc,diag=child(run,'setup',[R/'tools/setup.sh','--check'])
            if rc:raise InfraError(diag)
            code,detail=evaluate(work,run,mode)
    except (InfraError,OSError,KeyboardInterrupt) as e:code,detail=2,str(e)
    emit_result(result(code,[{'id':'L03-'+mode,'pass':code==0,'detail':detail}],artifacts=path,next_action='Use the first failed field/cursor criterion; repair the submitted workspace, then rerun. INFRA is ungraded.'))
    return code
if __name__=='__main__':sys.exit(main())
