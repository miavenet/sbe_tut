"""Literal learner command execution with explicit positive and negative outcomes."""
import sys,re,json
from pathlib import Path
from harness import Run,InfraError,report_from_output
R=Path(__file__).resolve().parents[1]
ANSWERS={
 'checks/l01/chk_complete_offsets.sh':{'root_bytes':34,'group_at':42,'entry_bytes':12,'trader_at':70},
 'checks/l01/chk_recall_offsets.sh':{'header':8,'root':34,'body':71,'packet':79,'offsets':[0,8,16,20,24,32,33]},
 'checks/l04/chk_ir.py':{'quantity_offset':16,'group':'fills','data':['trader','note'],'difference':'package-info.java'},
 'checks/l04/chk_diagnose.py':{'offset':46,'field':'batches[0].label.length','action':'reject-before-commit'}}
def run_paths(paths):
 rows=[]
 with Run('lesson-commands',parent=R/'manifest/evidence/lesson-commands',timeout=300) as run:
  for path in paths:
   for block in re.findall(r'```bash\n(.*?)\n```',(R/path).read_text(),re.S):
    for cmd in block.splitlines():
     if not cmd.strip():continue
     expected=1 if 'printf' in cmd and '| checks/' in cmd and '/worked' not in cmd else 0
     answer=json.dumps(ANSWERS[cmd])+'\n' if cmd in ANSWERS else ''
     c=run.start('command-'+str(len(rows)),['bash','-c',cmd],cwd=R,stdin=answer)
     rc=run.wait(c);out=c.log.read_text()
     assert rc==expected,(path,cmd,rc,expected,out)
     if '| checks/' in cmd or cmd in ANSWERS:
      report=report_from_output(out);assert report['status']==('HIT' if rc==0 else 'MISS'),report
     elif 'dump.py' in cmd:
      expected_dump = ('trader length @70=3 end=75 remaining=4' if 'order-v0.bin' in cmd
                       else 'trader length @76=3 end=81 remaining=4')
      assert expected_dump in out,out
     else:assert json.loads(out.splitlines()[-1])['status'] in ('PASS','HIT'),out
     rows.append(dict(path=path,command=cmd,stdin=answer,exit_code=rc,expected_exit=expected,output=str(c.log.relative_to(R))))
  (run.path/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
 return len(rows),str(run.path.relative_to(R))
