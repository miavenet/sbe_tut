#!/usr/bin/env python3
# [claim: WP4-PERFORMANCE]
import sys
sys.dont_write_bytecode=True
import json
from check import R,L,Run,child,prepare,compile_argv
with Run('wp4-load',parent=R/'manifest/evidence/wp4') as run:
    rc,out=child(run,'setup',[R/'tools/setup.sh','--check']);assert rc==0,out
    inc=prepare(run)
    rc,out=child(run,'compile',compile_argv(R/'checks/l05/performance.cpp',run.path/'load',includes=[L/'worked',L,*inc],checked=True));assert rc==0,out
    rc,out=child(run,'load',[run.path/'load']);assert rc==0,out
    rows=[json.loads(line) for line in out.splitlines()];assert len(rows)==4
    for r in rows:
        assert len(r['samples_ns'])==r['offered_per_tick']*50
        assert r['accepted']+r['rejected']==len(r['samples_ns']) and r['bytes']==86*r['accepted']
        assert r['p50_offer_ns']<=r['p99_offer_ns'] and r['backlog_max']<=2
    stable=[{k:v for k,v in row.items() if k not in ('samples_ns','p50_offer_ns','p99_offer_ns')} for row in rows]
print(json.dumps({'status':'PASS','configurations':stable,'scope':'offer-call latency, two-slot single-threaded simulation; no throughput target','artifacts':str(run.path.relative_to(R))}))
