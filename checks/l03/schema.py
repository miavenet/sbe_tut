#!/usr/bin/env python3
# [claim: WP2-CHECKS]
import sys
sys.dont_write_bytecode=True
from check import R,L,Run,child,compatible,exercise_contract,generation_argv,workspace_from_stdin,result,InfraError
from harness import emit_result
import json,xml.etree.ElementTree as E

def main():
    code=2;detail='';path=''
    try:
        work=workspace_from_stdin()
        with Run('wp2-schema',parent=R/'manifest/evidence/wp2') as run:
            path=str(run.path.relative_to(R))
            rc,diag=child(run,'setup',[R/'tools/setup.sh','--check'])
            if rc:raise InfraError(diag)
            try:
                errors=compatible(L/'order-v0.xml',work/'order-v1.xml')
                if not exercise_contract(work/'order-v1.xml',L/'order-v1.xml'):
                    errors.append('exercise contract: retain exactly the supplied v1 fields, groups and data')
                code=int(bool(errors));detail='; '.join(errors) if errors else 'optional append contract passed'
                if not errors:
                    rc,diag=child(run,'generate',generation_argv(run.path/'gen',work/'order-v1.xml'))
                    if rc:code,detail=1,diag[-2000:]
            except (ValueError,OSError,E.ParseError,StopIteration,AttributeError) as e:code,detail=1,str(e)
    except (InfraError,OSError,KeyboardInterrupt) as e:code,detail=2,str(e)
    emit_result(result(code,[{'id':'schema-append','pass':code==0,'detail':detail}],artifacts=path,next_action='Restore old field/type definitions; append optional fields with sinceVersion=1.'))
    return code
if __name__=='__main__':sys.exit(main())
