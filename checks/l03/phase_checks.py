#!/usr/bin/env python3
# [claim: WP2-CHECKS]
import sys
sys.dont_write_bytecode=True
import json,shutil
from check import R,L,Run,child
with Run('wp2-phases',parent=R/'manifest/evidence/wp2') as run:
    work=run.path/'completion';shutil.copytree(L/'completion',work)
    shutil.copyfile(L/'order-v1.xml',work/'order-v1.xml')
    cases=[('schema-good','checks/l03/chk_schema.sh',work,0),('schema-bad','checks/l03/chk_schema.sh',L/'completion',1),('reader-not-yet','checks/l03/chk_matrix.sh',work,1),('matrix-good','checks/l03/chk_matrix.sh',L/'independent',0),('archive-not-yet','checks/l03/chk_archive.sh',L/'independent',1),('archive-good','checks/l03/chk_archive.sh',L/'worked',0)]
    for name,script,workspace,want in cases:
        rc,out=child(run,name,[R/script],stdin=str(workspace)+'\n')
        assert rc==want,(name,rc,out)
        print(name+': observed exit '+str(rc))
print(json.dumps({'status':'PASS','cases':len(cases),'artifacts':str(run.path.relative_to(R))},sort_keys=True))
