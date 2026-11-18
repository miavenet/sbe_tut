#!/usr/bin/env python3
# [claim: WP3-CHECKS] [claim: WP3-IRANSWER] [claim: WP3-DIAGANSWER] [claim: WP3-INSPECT]
import sys
sys.dont_write_bytecode=True
import json,concurrent.futures
from check import R,L,Run,child
sys.path.insert(0,str(R/'tools'))
from harness import report_from_output

def main():
    with Run('wp3-phases',parent=R/'manifest/evidence/wp3',timeout=40) as run:
        jobs=[('order','worked',0),('order','completion',1),('validate','worked',0),('validate','validation-completion',1),('nested','worked',0),('nested','independent',1)]
        def one(j):
            mode,work,want=j;rc,out=child(run,mode+'-'+work,[R/f'checks/l04/chk_{mode}.sh'],f'labs/l04/{work}\n')
            assert rc==want,(j,rc,out)
            assert report_from_output(out)['status']==('HIT' if want==0 else 'MISS')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(one,jobs))
        answers={
            'ir':{'quantity_offset':16,'group':'fills','data':['trader','note'],'difference':'package-info.java'},
            'diagnose':{'offset':46,'field':'batches[0].label.length','action':'reject-before-commit'}}
        n=0
        for kind,answer in answers.items():
            cases=[(answer,0),({},1),('I confidently insist all bytes are correct',1)]
            raws=[('',2),('   \n',2),('x'*70000,2),('not json',1)]
            first=next(iter(answer));raws.append((json.dumps(answer).replace(json.dumps(answer[first]),'0.0',1) if False else json.dumps(answer).replace(f'"{first}": '+json.dumps(answer[first]),f'"{first}": {answer[first]}.0',1) if isinstance(answer[first],int) else None,1))
            raws.append((json.dumps(answer)[:-1]+f', "{first}": '+json.dumps(answer[first])+'}',1))
            for j,(raw,want) in enumerate(r for r in raws if r[0] is not None):
                rc,out=child(run,kind+'raw'+str(j),[R/f'checks/l04/chk_{kind}.py'],raw);assert rc==want,(kind,raw[:60],rc,out);n+=1
            for key in answer:
                wrong=answer.copy();wrong[key]=0 if isinstance(wrong[key],str) else 'wrong';cases.append((wrong,1))
            for i,(a,want) in enumerate(cases):
                rc,out=child(run,kind+str(i),[R/f'checks/l04/chk_{kind}.py'],json.dumps(a)+'\n');assert rc==want,(kind,a,rc,out);n+=1
        rc,out=child(run,'dump',[sys.executable,'-B',R/'checks/l04/dump.py',L/'fixtures/order-v1.bin']);assert rc==0 and 'trader length @76=3 end=81 remaining=4' in out
        rc,out=child(run,'diff',[sys.executable,'-B',R/'checks/l04/dump.py','--diff',L/'fixtures/nested.bin',L/'fixtures/nested-bad-length.bin']);assert rc==0 and json.loads(out)=={'differences':[{'offset':46,'left':2,'right':255},{'offset':47,'left':0,'right':255}]},out
    print(json.dumps({'status':'PASS','phases':6,'answer_attacks':n,'dump_diff':True,'artifacts':str(run.path.relative_to(R))}));return 0
if __name__=='__main__':sys.exit(main())
