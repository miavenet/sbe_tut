#!/usr/bin/env python3
"""Offline Lesson 1 session: real MISS, edit, retry, HIT, and completion."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from drive import Course, explanation_bullets

course=Course(ROOT)
lesson=course.lessons[0]
with tempfile.TemporaryDirectory(prefix='scripted-session-', dir=ROOT) as folder:
    tmp=Path(folder)
    progress=tmp/'progress.json'
    answers=tmp/'answers.txt'
    workspace=tmp/'workspace'
    shutil.copytree(ROOT/'labs/l01/work',workspace)
    misses=hits=0
    events=[]
    for step in range(160):
        state=json.loads(progress.read_text()) if progress.exists() else None
        if state and all(card in state['completed'] for card in course.order(lesson)):
            break
        pending=state.get('pending') if state else None
        if state and state.get('appendix'):
            action='checkpoint' if state['appendix']['answer'] is None else 'continue'
        elif not pending:
            action='guess'
        elif pending['stage']=='answer':
            card=pending['card']
            if card=='L01-C1':
                action='{"root_bytes":34,"group_at":42,"entry_bytes":12,"trader_at":70}'
            elif card=='L01-R1':
                action='{"header":8,"root":34,"body":71,"packet":79,"offsets":[0,8,16,20,24,32,33]}'
            elif card=='L01-C2':
                action=str(workspace)
            elif card in ('L01-I1','L01-T1'):
                action='labs/l01/worked'
            else:
                action='guess'
        elif pending['stage']=='confidence':
            action='sure'
        elif pending['stage'] in ('selfreport','explanation_report'):
            bullets=(explanation_bullets(course.cards[pending['card']])
                     if pending['stage']=='explanation_report' else course.cards[pending['card']]['Key'])
            action=' '.join('y' for _ in bullets)
        elif pending['stage']=='explain':
            action='The field belongs to the fixed block; the remaining bytes are the tail.'
        elif pending['stage']=='lab_miss':
            misses+=1
            events.append(pending['card']+' MISS')
            if pending['card']=='L01-C2':
                for file in ('submission.hpp','layout.json'):
                    shutil.copy2(ROOT/'labs/l01/worked'/file,workspace/file)
                action='retry'
            else:
                action='giveup'
        elif pending['stage']=='feedback':
            if pending['result']['grade']=='HIT':
                hits+=1
                events.append(pending['card']+' HIT')
            action='continue'
        elif pending['stage'] in ('correction','elaborate'):
            action='The repaired byte now agrees with the schema and fixture.'
        else:
            raise AssertionError((pending['card'],pending['stage'],pending.get('result')))
        answers.write_text(action+'\n')
        cmd=[sys.executable,'-B','drive.py','--today','2026-11-11','--minutes','20',
             '--progress',str(progress),'--auto',str(answers),'--new-session']
        if not state:
            cmd.append('--init')
        run=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        assert run.returncode==0,(step,run.stderr,run.stdout[-800:])
    else:
        raise AssertionError('Lesson 1 did not finish within 160 scripted steps')
    assert 'L01-C2 MISS' in events and 'L01-C2 HIT' in events
    print(json.dumps({'status':'PASS','steps':step,'lesson_1_cards':len(course.order(lesson)),
                      'misses':misses,'hits':hits,'lab_retry':True}))
