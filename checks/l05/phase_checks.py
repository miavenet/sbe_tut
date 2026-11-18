#!/usr/bin/env python3
# [claim: WP4-CHECKS]
import sys
sys.dont_write_bytecode=True
import concurrent.futures,json
from check import R,L,Run,child,prepare,evaluate

def main():
 with Run('wp4-phases',parent=R/'manifest/evidence/wp4',timeout=40) as run:
  rc,out=child(run,'setup',[R/'tools/setup.sh','--check']);assert rc==0,out
  inc=prepare(run)
  jobs=[('frame','worked',0),('frame','completion',1),('replay','worked',0),('replay','completion',1),('release','worked',0),('release','completion',1),('allocation','worked',0)]
  # The opaque external string escape makes the deliberately allocating control observable.
  src=(L/'worked/submission.hpp').read_text();bad=run.path/'allocating-submission';bad.mkdir()
  src=src.replace('#include "api.hpp"','#include "api.hpp"\n#include <string>\nvoid escape_string(const std::string&);').replace('try{\n        need(n>=8','try{\n        std::string hidden_allocation(4096,\'x\');escape_string(hidden_allocation);\n        need(n>=8')
  (bad/'submission.hpp').write_text(src)
  def one(j):
   mode,w,want=j;rc,out=evaluate(L/w,run,mode,inc,mode+'-'+w);assert rc==want,(j,rc,out)
   return {'mode':mode,'candidate':w,'exit':rc,'output':out}
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:outcomes=list(pool.map(one,jobs))
  rc,out=evaluate(bad,run,'allocation',inc,'allocating');assert rc==1 and 'warmed bounded' in out,out
  outcomes.append({'mode':'allocation','candidate':'allocating','exit':rc,'output':out})
  for name,path,want in [('good',L/'worked',0),('bad',L/'work',1)]:
   rc,out=child(run,'migration-'+name,[R/'checks/l05/migration.py'],str(path)+'\n');assert rc==want,(rc,out)
  (run.path/'outcomes.json').write_text(json.dumps(outcomes,indent=2)+'\n')
 print(json.dumps({'status':'PASS','phase_controls':8,'migration_controls':2,'artifacts':str(run.path.relative_to(R))}));return 0
if __name__=='__main__':sys.exit(main())
