#!/usr/bin/env python3
"""WP5 acceptance; synthetic inputs only, no canonical progress writes."""
import argparse
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('driver', ROOT / 'drive.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
FIX = ROOT / 'tools/driver-fixtures'
EVIDENCE = None
PROBES = []
REAL_CHECK = d.check_answer


def recorded_check(card, answer, course, timeout=30):
    result = REAL_CHECK(card, answer, course, timeout)
    PROBES.append(dict(card=card['id'], predicate=card['AcceptIf'], stdin=answer,
                       timeout=timeout, result=copy.deepcopy(result)))
    return result


d.check_answer = recorded_check


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wp5-tests-',dir=ROOT)
        self.base = Path(self.tmp.name)
        self.course = d.Course(ROOT, 'tools/driver-fixtures/lessons', 'tools/driver-fixtures/schedule.json')
        self.state = d.initial_state(self.course)
        self.path = self.base / 'progress.json'
        self.driver = d.Driver(self.course, self.state, lambda s: d.atomic_json(self.path, s))
        self.driver.session('2026-11-10')

    def tearDown(self):
        if EVIDENCE:
            (EVIDENCE / (self.id().split('.')[-1] + '.json')).write_text(json.dumps(self.state, indent=2, sort_keys=True)+'\n')
        self.tmp.cleanup()

    def finish(self, driver=None, answer=None, confidence='sure', report=None):
        driver = driver or self.driver
        p = driver.s['pending']
        c = self.course.cards[p['card']]
        if p['stage'] == 'answer':
            driver.act(answer if answer is not None else '{"value":42}')
        if p['stage'] == 'production':
            driver.act('fresh')
        if p['stage'] == 'confidence':
            driver.act(confidence)
        if p['stage'] == 'grade':
            driver.act('check')
        if p['stage'] == 'infra':
            return
        if p['stage'] == 'selfreport':
            driver.act(report or ' '.join('y' for _ in c['Key']))
        if p['stage'] == 'feedback':
            driver.act('continue')
        if driver.s['pending'] and p['stage'] in ('correction','elaborate'):
            driver.act('I must account for all items; my earlier guess omitted one.')

    def to_recall(self):
        while self.driver.select() != 'L01-C1-R':
            self.finish()

    def complete_course(self):
        guard=0
        while not all(self.driver.lesson_done(l) for l in self.course.lesson_ids):
            guard+=1
            self.assertLess(guard,100)
            if not self.driver.select():
                self.driver.session(self.driver.today, fresh=True)
                continue
            self.finish()

    def test_pretest_before_worked_and_eof(self):
        self.assertEqual(self.driver.select(), 'L01-C1-P')
        self.assertNotIn('42.', self.driver.view())
        before=copy.deepcopy(self.state)
        self.assertFalse(self.driver.act(''))
        self.assertEqual(before,self.state)
        self.assertFalse(self.state['pretests_committed'])
        self.driver.act('41')
        self.assertEqual(self.state['pretests_committed']['L01-C1-P']['answer'],'41')
        self.assertNotIn('42.',self.driver.view())
        self.driver.act('sure'); self.driver.act('check')
        self.assertIn('42.',self.driver.view())
        self.driver.act('continue')
        self.assertEqual(self.driver.select(),'L01-C1-W')
        self.assertNotIn('40 + 2 = 42',self.driver.view())
        self.driver.act('forty-two'); self.driver.act('sure'); self.driver.act('check')
        self.assertIn('40 + 2 = 42',self.driver.view())

    def test_every_transition_resume(self):
        self.driver.select()
        for action in ['41','sure','check','continue']:
            self.driver.act(action)
            saved=d.read_json(self.path)
            fresh=d.Driver(self.course,saved)
            self.assertEqual(self.driver.view(),fresh.view())
            self.assertEqual(self.state,saved)
        self.driver.select()
        for action in ['42','sure','check','my explanation']:
            self.driver.act(action)
            self.assertEqual(self.state,d.read_json(self.path))

    def test_day_two_no_repeated_pretest(self):
        self.driver.select(); self.driver.act('41')
        self.driver.session('2026-11-11')
        self.assertEqual(self.driver.select(),'L01-C1-P')
        self.assertEqual(self.state['pending']['stage'],'confidence')
        self.finish()
        self.assertEqual(self.driver.select(),'L01-C1-W')
        self.assertEqual(len(self.state['pretests_committed']),1)

    def test_fade_order_and_prerequisites(self):
        ids=[]
        for _ in range(11):
            ids.append(self.driver.select()); self.finish()
        self.assertEqual(ids[:5],['L01-C1-P','L01-C1-W','L01-C1-C','L01-C1-R','L01-C1-T'])
        self.assertEqual(ids[-1],'L01-I')
        self.assertFalse(any(x.startswith('L02') for x in ids))
        self.assertEqual(self.driver.select(),'L02-C1-P')

    def test_skip_is_attempt_and_miss_restatement(self):
        self.driver.select(); self.finish(answer='/skip')
        self.assertIn('L01-C1-P',self.state['pretests_committed'])
        self.to_recall()
        self.driver.act("don't know"); self.driver.act('sure'); self.driver.act('check')
        self.assertEqual(self.state['pending']['grade'],'MISS')
        self.driver.act('continue')
        self.assertEqual(self.state['phase'],'correction')
        self.assertFalse(self.driver.act('continue'))
        self.assertFalse(self.driver.act(''))
        self.assertFalse(self.driver.act('/skip'))
        self.assertEqual(self.state['pending']['stage'], 'correction')
        self.assertTrue(self.driver.act('The value is 42; I forgot the final two.'))
        self.assertEqual(self.state['work']['L01-C1-R']['correction'],
                         'The value is 42; I forgot the final two.')
        st=self.state['cards']['L01-C1-R']
        self.assertEqual(st['next'],'2026-11-11')
        self.assertTrue(st['confident_miss'])

    def test_spacing_growth_and_low_confidence(self):
        self.to_recall(); self.finish()
        n='L01-C1-R'
        self.assertEqual(self.state['cards'][n]['next'],'2026-11-11')
        for day,next_day in [('2026-11-11','2026-11-14'),('2026-11-14','2026-11-21'),('2026-11-21','2026-12-05')]:
            self.driver.session(day,mode='quick',fresh=True)
            self.driver.begin(n,'review','L01','L01-C1')
            self.finish()
            self.assertEqual(self.state['cards'][n]['next'],next_day)
        self.driver.session('2026-12-05',mode='quick',fresh=True)
        self.driver.begin(n,'review','L01','L01-C1'); self.finish(confidence='unsure')
        self.assertEqual(self.state['cards'][n]['next'],'2026-12-06')

    def test_flag_until_delayed_success(self):
        self.to_recall(); self.finish(answer='{"value":41}')
        n='L01-C1-R'
        self.driver.begin(n,'review','L01','L01-C1'); self.finish()
        self.assertTrue(self.state['cards'][n]['confident_miss'])
        self.driver.session('2026-11-11',fresh=True)
        self.driver.begin(n,'review','L01','L01-C1'); self.finish()
        self.assertFalse(self.state['cards'][n]['confident_miss'])

    def test_overdue_review_priority_and_interleaving(self):
        self.complete_course()
        self.driver.session('2026-11-20',mode='quick',fresh=True,minutes=2)
        before={k:v['next'] for k,v in self.state['cards'].items()}
        n=self.driver.select(); self.assertEqual(self.state['pending']['context'],'review')
        first=self.course.cards[n]['topic']; self.finish()
        n=self.driver.select(); self.assertNotEqual(self.course.cards[n]['topic'],first); self.finish()
        self.assertIsNone(self.driver.select())
        self.assertTrue(any(v['next']==before[k] for k,v in self.state['cards'].items()))

    def test_normal_sitting_caps_review_minutes(self):
        self.complete_course()
        self.driver.session('2026-11-20',fresh=True,minutes=15)
        reviewed=0
        while self.driver.select():
            self.assertEqual(self.state['pending']['context'],'review')
            self.finish();reviewed+=1
        self.assertEqual(reviewed,5)
        self.assertEqual(self.state['session']['review_used'],5)

    def test_budget_and_six_concepts(self):
        self.driver.session('2026-11-10',fresh=True,minutes=1)
        self.driver.select(); self.finish()
        self.assertIsNone(self.driver.select())
        self.assertEqual(self.state['session']['used'],1)
        self.driver.session('2026-11-10',fresh=True,minutes=20)
        # Zero elapsed estimates are not allowed in real schedules; use many tiny
        # positive estimates to make the concept-count cap independently testable.
        for c in self.course.cards.values(): c['minutes']='0.1'
        self.complete_course()
        self.assertLessEqual(len(self.state['session']['new_concepts']),6)
        # Add one seventh concept, then demonstrate select refuses it.
        self.state['session']['new_concepts']=['x'+str(i) for i in range(6)]
        self.state['concepts'].pop('L05-C1')
        for n in self.course.order(self.course.lessons[-1]):
            self.state['completed'].remove(n)
        self.assertIsNone(self.driver.select())

    def test_selfreport_paraphrase_contradiction_partial(self):
        self.to_recall(); self.finish()
        self.driver.select()
        self.driver.act('twenty-one pairs make forty-two, with both members counted')
        self.driver.act('sure'); self.driver.act('check')
        self.assertEqual(self.state['phase'],'selfreport')
        self.driver.act('y y x')
        self.assertEqual(self.state['pending']['grade'],'MISS')
        self.finish()
        self.driver.begin('L01-C1-T','review','L01','L01-C1')
        self.finish(answer='Only first criterion',report='y n')
        self.assertEqual(self.state['cards']['L01-C1-T']['grade'],'PARTIAL')

    def test_confidence_and_yes_no_spellings(self):
        self.driver.select();self.driver.act('guess')
        self.assertFalse(self.driver.act('maybe'))
        self.assertEqual(self.state['pending']['stage'],'confidence')
        self.assertTrue(self.driver.act('YES'))
        self.assertEqual(self.state['pending']['confidence'],'sure')
        self.driver.act('check');self.driver.act('continue')
        self.to_recall();self.finish();self.driver.select()
        self.driver.act('an explanation');self.driver.act('nO');self.driver.act('check')
        self.assertEqual(self.state['pending']['confidence'],'unsure')
        self.assertEqual(self.state['pending']['stage'],'selfreport')
        self.assertTrue(self.driver.act('YES yes'))

    def test_submitted_work_positive_negative(self):
        card=self.course.cards['L01-C1-R']
        work=self.base/'work'; work.mkdir()
        for value,grade in [(42,'HIT'),(41,'MISS')]:
            (work/'answer.json').write_text(json.dumps({'value':value}))
            result=d.check_answer(card,str(work),self.course)
            self.assertEqual(result['grade'],grade,result)
        self.assertEqual(d.check_answer(card,'{"value":true}',self.course)['grade'],'MISS')
        self.assertEqual(d.check_answer(card,'missing/path',self.course)['grade'],'INFRA')

    def test_confirmed_exit_race_recovery(self):
        original=d.Run.wait
        raised=[]
        def race(run,child,**kwargs):
            code=original(run,child,**kwargs)
            if not raised:
                raised.append(True)
                raise d.InfraError('submission exited before submission exit; artifacts: synthetic-race')
            return code
        with patch.object(d.Run,'wait',race):
            result=d.check_answer(self.course.cards['L01-C1-R'],'{"value":42}',self.course)
        self.assertEqual(result['grade'],'HIT',result)
        self.assertEqual(len(raised),1)

    def test_infra_timeout_signal_noise_and_invalid_report(self):
        card=dict(self.course.cards['L01-C1-R'],AcceptIf='check(tools/driver-fixtures/checks/fault.py)')
        for answer in ['timeout','signal','noise','mismatch','false-hit','invalid','null-report','bad-criteria']:
            result=d.check_answer(card,answer,self.course,timeout=0.3 if answer=='timeout' else 5)
            self.assertEqual(result['grade'],'INFRA',(answer,result))
        card['AcceptIf']='check(/tmp/absent-check)'
        self.assertEqual(d.check_answer(card,'42',self.course)['grade'],'INFRA')

    def test_infra_preserves_attempt_and_schedule(self):
        self.to_recall()
        self.driver.act('missing/path'); self.driver.act('sure'); self.driver.act('check')
        self.assertEqual(self.state['phase'],'infra')
        self.assertNotIn('L01-C1-R',self.state['cards'])
        self.assertNotIn('Key:',self.driver.view())
        self.assertFalse(self.driver.act('continue'))
        self.driver.act('/retry')
        self.assertEqual(self.state['phase'],'grade')
        self.assertEqual(self.state['pending']['answer'],'missing/path')

    def test_guarded_regex_and_model_attacks(self):
        card=dict(self.course.cards['L01-C1-R'],AcceptIf=r'regex(/shared|same/i)',RejectIf=r'regex(/not shared|not the same/i)')
        for answer,expected in [('same storage','HIT'),('shared but not shared','MISS'),('NOT the same','MISS')]:
            self.assertEqual(d.check_answer(card,answer,self.course)['grade'],expected)
        with self.assertRaises(ValueError): d.regex_predicate('always true','x')
        for case in d.read_json(FIX/'model-attacks.json'):
            result=d.reconcile_model_grade({'grade':case['executable']},case['proposal'],2)
            self.assertEqual(result['grade'],case['expected'],case['name'])
        self.assertEqual(d.reconcile_model_grade({'grade':'SELF'},None,2)['grade'],'INFRA')

    def test_confidence_and_feedback_interruptions(self):
        self.to_recall()
        self.driver.act('{"value":41}')
        self.assertIn('[L01-C1-R] Your answer: {"value":41}',self.driver.view())
        self.assertNotIn('Key:',self.driver.view())
        for action in ['sure','check','continue']:
            self.driver.act(action)
            loaded=d.read_json(self.path)
            resumed=d.Driver(self.course,loaded)
            self.assertEqual(resumed.view(),self.driver.view())
            self.assertFalse(resumed.act(''))
            self.assertNotIn('L01-C1-R',loaded['cards'])
        self.driver.act('Forty-one omitted one; I will count all forty-two.')
        self.assertEqual(self.state['cards']['L01-C1-R']['grade'],'MISS')

    def test_keyboard_interrupt_at_answer_and_confidence(self):
        for responses,stage in [([KeyboardInterrupt()],'answer'),(['41',KeyboardInterrupt()],'confidence')]:
            path=self.base/('interrupt-'+stage+'.json')
            output=io.StringIO()
            with patch('builtins.input',side_effect=responses),redirect_stdout(output):
                rc=d.main(['tools/driver-fixtures/lessons','--root',str(ROOT),'--schedule','tools/driver-fixtures/schedule.json','--today','2026-11-10',
                           '--progress',str(path),'--init'])
            self.assertEqual(rc,0)
            self.assertEqual(d.read_json(path)['pending']['stage'],stage)
            self.assertNotIn('Key:',output.getvalue())
            if EVIDENCE: (EVIDENCE/('interrupt-'+stage+'.txt')).write_text(output.getvalue())

    def test_help_and_fixture_arithmetic(self):
        output=io.StringIO()
        with redirect_stdout(output),self.assertRaises(SystemExit) as cm:
            d.main(['--help'])
        self.assertEqual(cm.exception.code,0)
        for flag in ['--today','--mode','--minutes','--new-session','--init','--tier']:
            self.assertIn(flag,output.getvalue())
        self.assertEqual(40+2,42)
        self.assertEqual(21*2,42)
        self.assertEqual(42+1,43)
        if EVIDENCE: (EVIDENCE/'help.txt').write_text(output.getvalue())

    def test_exam_lock_and_every_objective_offline(self):
        self.complete_course()
        self.assertFalse(any(x['passed'] for x in self.state['objectives'].values()))
        self.driver.session('2026-11-16',mode='exam',fresh=True)
        self.assertFalse(self.driver.exam_open()); self.assertIsNone(self.driver.select())
        self.driver.session('2026-11-17',mode='exam',fresh=True)
        self.assertTrue(self.driver.exam_open())
        seen=[]
        while self.driver.select():
            n=self.state['pending']['card']; seen.append(n)
            self.assertFalse(self.driver.act('/hint'))
            self.finish()
        self.assertEqual(len(seen),12)
        self.assertTrue(all(x['passed'] for x in self.state['objectives'].values()))
        self.assertEqual(len({self.course.cards[n]['topic'] for n in seen}),2)
        self.assertIsNone(self.driver.select())

    def test_exam_failed_objective_stays_due(self):
        self.complete_course()
        self.driver.session('2026-11-17',mode='exam',fresh=True)
        n=self.driver.select(); self.finish(answer='/skip')
        self.assertEqual(self.state['cards'][n]['next'],'2026-11-18')
        while self.driver.select(): self.finish()
        self.assertFalse(all(x['passed'] for x in self.state['objectives'].values()))
        self.driver.session('2026-11-17',mode='exam',fresh=True)
        self.assertIsNone(self.driver.select())
        self.driver.session('2026-11-18',mode='exam',fresh=True)
        self.assertEqual(self.driver.select(),n); self.finish()
        self.assertTrue(all(x['passed'] for x in self.state['objectives'].values()))

    def test_expert_demonstration_and_fallback(self):
        self.driver.session('2026-11-10',fresh=True,expert=True)
        self.driver.select(); self.finish()
        self.assertEqual(self.driver.select(),'L01-C1-R'); self.finish()
        self.assertEqual(self.driver.select(),'L01-C1-T'); self.finish()
        self.assertIn('bypass',self.state['concepts']['L01-C1'])
        self.assertIn('L01-C1-W',self.state['completed'])
        self.driver.select(); self.finish() # second pretest
        self.assertEqual(self.driver.select(),'L01-C2-R'); self.finish(answer='{"value":41}')
        self.assertEqual(self.driver.select(),'L01-C2-W')

    def test_parser_multiline_folded_and_reject_unguarded(self):
        card=self.course.cards['L01-C1-T']
        self.assertEqual(len(card['Key']),2)
        p=self.base/'lesson.md'
        p.write_text('### Card X · Recall\nQ: first\n  second\n<details>\nKey:\n- one\n  continued\n</details>\n')
        manifest=self.base/'cards.json'
        row={'kind':'CARD','lesson':'lesson','type':'recall','topic':'test','minutes':1,
             'Source':'test','AcceptIf':'','RejectIf':''}
        manifest.write_text(json.dumps({'schema_version':1,'cards':{'X':row}}))
        parsed=d.parse_cards(self.base,manifest)['X']
        self.assertEqual(parsed['Q'],'first\nsecond')
        self.assertEqual(parsed['Key'],['one continued'])
        row['AcceptIf']='regex(/x/)'
        manifest.write_text(json.dumps({'schema_version':1,'cards':{'X':row}}))
        with self.assertRaisesRegex(ValueError,'regex needs RejectIf'): d.parse_cards(self.base,manifest)
        row['RejectIf']='regex(/not x/)'
        manifest.write_text(json.dumps({'schema_version':1,'cards':{'X':row}}))
        self.assertEqual(d.parse_cards(self.base,manifest)['X']['AcceptIf'],'regex(/x/)')
        manifest.write_text(json.dumps({'schema_version':1,'cards':{}}))
        with self.assertRaisesRegex(ValueError,'manifest mismatch'): d.parse_cards(self.base,manifest)
        manifest.write_text(json.dumps({'schema_version':1,'cards':{'X':row,'Y':row}}))
        with self.assertRaisesRegex(ValueError,'manifest mismatch'): d.parse_cards(self.base,manifest)
        del row['minutes']
        manifest.write_text(json.dumps({'schema_version':1,'cards':{'X':row}}))
        with self.assertRaisesRegex(ValueError,'malformed card manifest'): d.parse_cards(self.base,manifest)

    def test_engagement_stories_and_contrasts_reach_driver(self):
        course=d.Course(ROOT)
        samples=[('L01-LAYOUT','Why the map has this shape'),
                 ('L02-OWNERSHIP','Why this is your job'),
                 ('L03-CONTRACT','Why the rules exist'),
                 ('L04-BOUNDS','A true story: Heartbleed'),
                 ('L05-FRAME','Imagine a damaged message')]
        for cid,phrase in samples:
            state=d.initial_state(course)
            driver=d.Driver(course,state)
            driver.session('2026-11-10')
            driver.begin(cid,'new',cid[:3],cid)
            self.assertIn(phrase,driver.view(),cid)
        for cid in ('L01-SEMANTICS','L02-OWNERSHIP','L03-CONTRACT','L04-CURSOR','L05-FRAME'):
            self.assertIn('|---|',course.text[cid]['worked'],cid)

    def test_invalid_registry_and_drift_fail_closed(self):
        shutil.copytree(FIX,self.base/'course')
        cfg=d.read_json(self.base/'course/schedule.json')
        cfg['lessons'][0]['concepts'][0]['completion']=[]
        (self.base/'course/schedule.json').write_text(json.dumps(cfg))
        with self.assertRaises(ValueError): d.Course(self.base/'course',schedule='schedule.json')
        self.state['course_hash']='changed'
        with self.assertRaises(ValueError): d.Driver(self.course,self.state)
        self.state['course_hash']=self.course.fingerprint
        with self.assertRaisesRegex(ValueError,'Saved date is 2026-11-10.*--reset'):
            self.driver.session('2026-11-09')

    def test_atomic_alias_and_determinism(self):
        alias=self.base/'progress.md'; alias.symlink_to('progress.json')
        self.driver.save=lambda s:d.atomic_json(alias,s)
        self.driver.select(); self.finish()
        self.assertTrue(alias.is_symlink())
        self.assertEqual(d.read_json(alias),self.state)
        state2=d.initial_state(self.course)
        state2['history_id']=self.state['history_id']
        second=d.Driver(self.course,state2)
        second.session('2026-11-10'); second.select(); self.finish(second)
        self.assertEqual(self.state,state2)

    def test_cli_eof_t2_resume_and_lock(self):
        args=[sys.executable,str(ROOT/'drive.py'),'tools/driver-fixtures/lessons','--root',str(ROOT),'--schedule','tools/driver-fixtures/schedule.json',
              '--progress',str(self.base/'cli.json'),'--today','2026-11-10','--init',
              '--auto',str(FIX/'answers-empty.txt')]
        with d.Run('wp5-cli',parent=self.base,timeout=10) as run:
            child=run.start('eof',args,cwd=ROOT)
            self.assertEqual(run.wait(child),0)
            output=child.log.read_text()
            self.assertNotIn('Key:',output)
            self.assertIn('Your place is saved',output)
            state=d.read_json(self.base/'cli.json')
            self.assertFalse(state['pretests_committed'])
            args[-1]=str(FIX/'answers-pretest.txt')
            child=run.start('resume',args+['--tier','T2'],cwd=ROOT)
            self.assertEqual(run.wait(child),0)
            self.assertIn(d.MODEL,child.log.read_text())
            state=d.read_json(self.base/'cli.json')
            self.assertEqual(state['pending']['card'],'L01-C1-W')
            self.assertEqual(state['pending']['stage'],'answer')
            lock=(self.base/'cli.json.lock').open('a')
            try:
                d.fcntl.flock(lock,d.fcntl.LOCK_EX|d.fcntl.LOCK_NB)
                child=run.start('locked',args,cwd=ROOT)
                self.assertEqual(run.wait(child),2)
                self.assertIn('already open',child.log.read_text())
            finally: lock.close()
            if EVIDENCE:
                for name,c in run.children.items():
                    (EVIDENCE/('cli-'+name+'.txt')).write_text(c.log.read_text())
                (EVIDENCE/'cli-output.txt').write_text(output)

    def test_cli_commands_reprompt_and_status(self):
        script=self.base/'commands.txt'
        script.write_text(':help\n:status\n:bogus\n/foo\n\n:skip\nsure\ncontinue\n:quit\n')
        output=io.StringIO()
        with redirect_stdout(output):
            rc=d.main(['tools/driver-fixtures/lessons','--root',str(ROOT),
                       '--schedule','tools/driver-fixtures/schedule.json',
                       '--today','2026-11-10','--progress',str(self.base/'commands.json'),
                       '--init','--auto',str(script)])
        self.assertEqual(rc,0)
        shown=output.getvalue()
        self.assertEqual(shown.count('unknown command, type :help'),2)
        self.assertIn('card 1 of 11',shown)
        self.assertIn('Blank line ignored',shown)
        saved=d.read_json(self.base/'commands.json')
        self.assertEqual(saved['pretests_committed']['L01-C1-P']['answer'],'/skip')

    def test_runnable_miss_retry_hit_keeps_first_grade(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10',minutes=15)
        driver.begin('L01-C2','new','L01','L01-SEMANTICS')
        self.assertTrue(d.runnable(course.cards['L01-C2']))
        self.assertIn('labs/l01/work',driver.view())
        driver.act('labs/l01/work');driver.act('sure')
        miss={'grade':'MISS','detail':'wrong byte','criteria':[{'id':'wire-1','pass':False,'detail':'byte 28: observed aa, expected 00'}]}
        hit={'grade':'HIT','detail':'all passed','criteria':[{'id':'wire-1','pass':True,'detail':'pass'}]}
        with patch.object(d,'check_answer',side_effect=[miss,hit]):
            driver.act('check')
            self.assertEqual(state['pending']['stage'],'lab_miss')
            self.assertNotIn('Key:',driver.view())
            driver.act('retry');driver.act('check')
        self.assertEqual(state['pending']['stage'],'selfreport')
        driver.act('y y y')
        self.assertEqual(state['pending']['grade'],'MISS')
        self.assertIn('Key:',driver.view())
        driver.act('continue');driver.act('I omitted the stop slot.')
        self.assertEqual(state['cards']['L01-C2']['grade'],'MISS')
        self.assertEqual(state['cards']['L01-C2']['next'],'2026-11-11')

    def test_missed_lab_review_does_not_starve_lesson(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        order=course.order(course.lessons[0])
        state['completed']=order[:order.index('L01-C2')+1]
        state['cards']['L01-C2']={'box':1,'next':'2026-11-11','last':'2026-11-10',
                                   'grade':'MISS','confidence':'sure','confident_miss':True,'hint':False}
        state['starters']['L01-C2']=d.capture_starter(ROOT/'labs/l01/work',course.fingerprint)
        driver.session('2026-11-11',minutes=15)
        self.assertEqual(driver.select(),'L01-C2')
        with patch.object(d,'check_answer',return_value={'grade':'MISS','detail':'still wrong',
                 'criteria':[{'id':'wire','pass':False,'detail':'wrong byte'}]}):
            driver.act('labs/l01/work');driver.act('fresh');driver.act('sure');driver.act('check')
        driver.act('giveup');driver.act('continue');driver.act('Still need to repair the byte.')
        self.assertEqual(state['cards']['L01-C2']['next'],'2026-11-12')
        self.assertEqual(driver.select(),'L01-I1')

    def test_runnable_review_uses_fresh_workspace(self):
        course_root=self.base/'real-course'
        shutil.copytree(ROOT/'lessons',course_root/'lessons')
        (course_root/'manifest').mkdir()
        shutil.copy2(ROOT/'manifest/schedule.json',course_root/'manifest/schedule.json')
        shutil.copy2(ROOT/'manifest/cards.json',course_root/'manifest/cards.json')
        shutil.copytree(ROOT/'labs/l01/work',course_root/'labs/l01/work')
        course=d.Course(course_root)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10',minutes=15)
        driver.begin('L01-C2','new','L01','L01-SEMANTICS')
        self.assertIn('L01-C2', state['starters'])
        original=(course_root/'labs/l01/work/submission.hpp').read_bytes()
        (course_root/'labs/l01/work/submission.hpp').write_text('changed after first encounter')
        state['pending']=None
        state['cards']['L01-C2']={'box':1,'next':'2026-11-11','last':'2026-11-10',
                                   'grade':'MISS','confidence':'sure','confident_miss':True,'hint':False}
        driver.session('2026-11-11',minutes=15,fresh=True)
        self.assertEqual(driver.select(),'L01-C2')
        fresh=course_root/state['pending']['default_workspace']/'submission.hpp'
        self.assertEqual(fresh.read_bytes(),original)
        self.assertIn(state['history_id'], str(fresh))
        self.assertIn(course.fingerprint, str(fresh))
        shown=driver.view()
        self.assertIn('Edit '+state['pending']['default_workspace'], shown)
        self.assertNotIn('printf \'%s\\n\' labs/l01/work |', shown)

    def test_review_starters_are_history_bound_and_restorable(self):
        course_root=self.base/'restorable-course'
        shutil.copytree(ROOT/'lessons',course_root/'lessons')
        (course_root/'manifest').mkdir()
        shutil.copy2(ROOT/'manifest/schedule.json',course_root/'manifest/schedule.json')
        shutil.copy2(ROOT/'manifest/cards.json',course_root/'manifest/cards.json')
        shutil.copytree(ROOT/'labs/l01/work',course_root/'labs/l01/work')
        course=d.Course(course_root)
        a=d.initial_state(course)
        b=d.initial_state(course)
        self.assertNotEqual(a['history_id'],b['history_id'])
        driver=d.Driver(course,a)
        driver.session('2026-11-10')
        driver.begin('L01-C2','new','L01','L01-SEMANTICS')
        saved=copy.deepcopy(a)
        a['pending']=None
        a['cards']['L01-C2']={'box':1,'next':'2026-11-11','last':'2026-11-10'}
        driver.session('2026-11-11',fresh=True)
        driver.begin('L01-C2','review','L01','L01-SEMANTICS')
        restored=course_root/a['pending']['default_workspace']
        shutil.rmtree(restored)
        saved['pending']=None
        saved['cards']['L01-C2']={'box':1,'next':'2026-11-11','last':'2026-11-10'}
        again=d.Driver(course,saved)
        again.session('2026-11-11',fresh=True)
        again.begin('L01-C2','review','L01','L01-SEMANTICS')
        self.assertTrue((restored/'submission.hpp').is_file())
        bdriver=d.Driver(course,b)
        bdriver.session('2026-11-11')
        with self.assertRaisesRegex(ValueError,'review starter unavailable'):
            bdriver.begin('L01-C2','review','L01','L01-SEMANTICS')

    def test_l01_explanations_precede_keys(self):
        course=d.Course(ROOT)
        for cid, count in [('L01-C1', 2), ('L01-R1', 1)]:
            state=d.initial_state(course)
            driver=d.Driver(course,state)
            driver.session('2026-11-10')
            driver.begin(cid,'new','L01','L01-LAYOUT')
            driver.act('labs/l01/work' if d.runnable(course.cards[cid]) else '{}')
            driver.act('sure')
            with patch.object(d,'check_answer',return_value={'grade':'HIT','detail':'pass','criteria':[]}):
                driver.act('check')
            self.assertEqual(state['pending']['stage'],'explain')
            self.assertNotIn('Key:', driver.view())
            driver.act('My own explanation before seeing the key.')
            self.assertEqual(driver.view().count('Explain:'), count)
            self.assertTrue(driver.act(' '.join(['y']*count)))

    def test_explanation_contradiction_is_miss(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10')
        driver.begin('L01-C1','new','L01','L01-LAYOUT')
        driver.act('{}');driver.act('sure')
        with patch.object(d,'check_answer',return_value={'grade':'HIT','detail':'pass','criteria':[]}):
            driver.act('check')
        driver.act('An explanation.');self.assertTrue(driver.act('y y x'))
        self.assertEqual(state['pending']['grade'],'MISS')

    def test_real_concept_primer_precedes_prediction(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10',minutes=15)
        driver.begin('L01-LAYOUT','new','L01','L01-LAYOUT')
        shown=driver.view()
        self.assertIn('22 00 01 00',shown)
        self.assertIn('Predict:',shown)
        self.assertNotIn('42..45  fills dimensions',shown)

    def test_checked_explanation_is_collected_before_key(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10',minutes=15)
        driver.begin('L03-R2','new','L03','L03-ACTING')
        driver.act('labs/l03/work')
        driver.act('sure')
        with patch.object(d,'check_answer',return_value={'grade':'HIT','detail':'pass','criteria':[]}):
            driver.act('check')
        self.assertEqual(state['pending']['stage'],'explain')
        self.assertNotIn('Key:',driver.view())
        driver.act('The writer chooses the root length.')
        self.assertIn('Key:',driver.view())
        self.assertEqual(driver.view().count('Explain:'),1)
        self.assertFalse(driver.act('y y'))
        driver.act('y');driver.act('continue')
        self.assertEqual(state['work']['L03-R2']['explanation'],
                         'The writer chooses the root length.')
        self.assertEqual(state['cards']['L03-R2']['grade'],'HIT')
        driver.begin('L03-R2','review','L03','L03-ACTING')
        driver.act('labs/l03/work');driver.act('fresh');driver.act('sure')
        with patch.object(d,'check_answer',return_value={'grade':'HIT','detail':'pass','criteria':[]}):
            driver.act('check')
        driver.act('I only know the code.');driver.act('n')
        self.assertIn('MISS',driver.view())
        driver.act('continue');driver.act('The header tells the root size.')
        self.assertEqual(state['cards']['L03-R2']['grade'],'MISS')

    def test_lab_key_marks_only_explanation_bullets_in_all_lessons(self):
        course=d.Course(ROOT)
        expected={'L01-C1','L01-R1','L02-T1','L03-R2','L04-R1','L04-C3','L05-R1','L05-R2','L05-R3'}
        self.assertEqual({c['id'] for c in course.cards.values()
                          if c['kind']=='CARD' and d.asks_explanation(c)},expected)
        for cid in expected:
            self.assertEqual(len(d.explanation_bullets(course.cards[cid])),
                             2 if cid == 'L01-C1' else 1)

    def test_absolute_existing_workspace_path_is_lab_input(self):
        workspace=self.base/'workspace'
        workspace.mkdir()
        self.assertTrue(d.is_existing_workspace_path(str(workspace)))
        self.assertFalse(d.is_existing_workspace_path('/not-an-existing-workspace-command'))

    def test_cli_accepts_absolute_correction_workspace(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10')
        driver.begin('L03-C1','new','L03','L03-CONTRACT')
        state['pending'].update(stage='correction', grade='MISS',
                                result={'grade':'MISS','detail':'schema repair required','criteria':[]})
        progress=self.base/'correction.json'
        d.atomic_json(progress,state)
        workspace=self.base/'workspace'
        workspace.mkdir(exist_ok=True)
        answers=self.base/'correction-answers.txt'
        answers.write_text(str(workspace)+'\n:quit\n')
        hit={'grade':'HIT','detail':'passed','criteria':[]}
        output=io.StringIO()
        with patch.object(d,'check_answer',return_value=hit) as check, redirect_stdout(output):
            self.assertEqual(d.main(['--root',str(ROOT),'--today','2026-11-10',
                                     '--progress',str(progress),'--auto',str(answers)]),0)
        self.assertNotIn('unknown command',output.getvalue())
        check.assert_called_once()

    def test_close_counts_due_reviews_in_plain_words(self):
        self.state['cards']={f'card-{n}':{'next':'2026-11-10','confident_miss':False}
                             for n in range(3)}
        self.assertIn('3 reviews are waiting',self.driver.close_text())
        self.state['cards'].clear()
        self.assertIn('Your place is saved',self.driver.close_text())

    def test_exam_excludes_same_day_review_and_credit(self):
        self.complete_course()
        n='L01-C1-R'
        self.driver.session('2026-11-17',mode='exam',fresh=True)
        self.state['cards'][n]['last']='2026-11-17'
        ids=[]
        for obj in self.course.objectives:
            ids += obj['production']+obj['transfer']
        self.assertIn(n,ids)
        self.assertNotEqual(self.driver.select(),n)
        self.state['pending']=None
        self.driver.begin(n,'exam','L01','L01-C1')
        self.finish()
        self.assertFalse(any(n in st['production'] for st in self.state['objectives'].values()))

    def test_retained_executable_exam_gets_no_credit(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        state['completed']=list(course.cards)
        state['lessons']={lid:{'first_exposure':'2026-11-01'} for lid in course.lesson_ids}
        state['cards']['L03-R2']={'last':'2026-11-01','box':1,'next':'2026-11-02',
                                  'grade':'HIT','confidence':'sure','hint':False}
        state['starters']['L03-R2']=d.capture_starter(ROOT/'labs/l03/work',course.fingerprint)
        driver.session('2026-11-17',mode='exam')
        driver.begin('L03-R2','exam','L03','L03-ACTING')
        driver.act('labs/l03/work')
        self.assertEqual(state['pending']['stage'],'production')
        driver.act('retained')
        self.assertTrue(state['pending']['hint'])
        driver.act('sure')
        with patch.object(d,'check_answer',return_value={'grade':'HIT','detail':'pass','criteria':[]}):
            driver.act('check')
        self.assertEqual(state['pending']['stage'],'explain')
        driver.act('The reader must use the acting block length and version.')
        driver.act(' '.join('y' for _ in d.explanation_bullets(course.cards['L03-R2'])));driver.act('continue')
        self.assertFalse(any('L03-R2' in st['production'] for st in state['objectives'].values()))

    def test_unknown_revision_keeps_progress_untouched(self):
        self.to_recall();self.finish()
        prior=copy.deepcopy(self.state)
        prior['course_hash']='older-course-hash'
        saved=copy.deepcopy(prior)
        with self.assertRaisesRegex(ValueError,'has not been modified'):
            d.migrate_progress(self.course,prior,'2026-11-11')
        self.assertEqual(prior,saved)

    def test_pre_declutter_progress_preserves_answer_schedule_and_review_starter(self):
        course=d.Course(ROOT)
        prior=d.read_json(FIX/'pre-declutter-state.json')
        saved=copy.deepcopy(prior)
        migrated=d.migrate_progress(course,prior,'2026-11-12')
        self.assertEqual(prior,saved)
        self.assertEqual(migrated['pending']['answer'],saved['pending']['answer'])
        self.assertEqual(migrated['pending']['stage'],saved['pending']['stage'])
        self.assertEqual(migrated['cards']['L01-C2'],saved['cards']['L01-C2'])
        self.assertEqual(migrated['cards']['L01-INT']['grade'],'STALE')
        self.assertEqual(migrated['cards']['L01-INT']['next'],'2026-11-12')
        self.assertEqual(migrated['cards']['L01-INT']['last'],saved['cards']['L01-INT']['last'])
        self.assertIn('L01-C2',migrated['completed'])
        self.assertEqual(migrated['starters']['L01-C2']['sha256'],
                         saved['starters']['L01-C2']['sha256'])
        self.assertFalse(migrated['objectives']['WP3-O4']['passed'])
        driver=d.Driver(course,migrated)
        migrated['pending']=None
        driver.session('2026-11-12',minutes=15,fresh=True)
        try:
            self.assertEqual(driver.pick(['L01-C2'],'review'),'L01-C2')
            path=ROOT/migrated['pending']['default_workspace']
            self.assertEqual((path/'submission.hpp').read_bytes(),
                             (ROOT/'labs/l01/work/submission.hpp').read_bytes())
        finally:
            shutil.rmtree(ROOT/'manifest/review-work'/migrated['history_id'],ignore_errors=True)

    def test_pre_declutter_corrupt_starter_is_rejected_before_mutation(self):
        course=d.Course(ROOT)
        prior=d.read_json(FIX/'pre-declutter-state.json')
        prior['starters']['L01-C2']['sha256']='bad'
        saved=copy.deepcopy(prior)
        with self.assertRaisesRegex(ValueError,'has not been modified'):
            d.migrate_progress(course,prior,'2026-11-12')
        self.assertEqual(prior,saved)

    def test_pre_declutter_missing_completed_starter_is_rejected(self):
        course=d.Course(ROOT)
        prior=d.read_json(FIX/'pre-declutter-state.json')
        del prior['starters']['L01-C2']
        saved=copy.deepcopy(prior)
        with self.assertRaisesRegex(ValueError,'has not been modified'):
            d.migrate_progress(course,prior,'2026-11-12')
        self.assertEqual(prior,saved)

    def test_long_due_card_reachable_in_normal_sitting(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        state['completed']=list(course.cards)
        state['cards']['L03-T1']={'box':1,'next':'2026-11-11','last':'2026-11-10'}
        state['cards']['L01-R1']={'box':1,'next':'2026-11-12','last':'2026-11-11'}
        driver.session('2026-11-13',minutes=15)
        # The workspace has not been captured, so selection reaches the review
        # but fails explicitly instead of silently reusing repaired work.
        with self.assertRaisesRegex(ValueError,'review starter unavailable'):
            driver.select()

    def test_schema_prerequisite_requires_repaired_check(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10')
        driver.begin('L03-C1','new','L03','L03-CONTRACT')
        driver.act('labs/l03/completion');driver.act('sure')
        miss={'grade':'MISS','detail':'fields wrong','criteria':[{'id':'schema','pass':False,'detail':'clientTag missing'}]}
        hit={'grade':'HIT','detail':'passed','criteria':[{'id':'schema','pass':True,'detail':'passed'}]}
        with patch.object(d,'check_answer',side_effect=[miss,miss,hit]):
            driver.act('check');driver.act('giveup');driver.act('continue')
            self.assertEqual(state['pending']['stage'],'correction')
            driver.act('labs/l03/completion')
            self.assertNotIn('L03-C1',state['completed'])
            self.assertIn('clientTag missing',driver.view())
            driver.act('labs/l03/worked')
        self.assertIn('L03-C1',state['completed'])
        self.assertEqual(state['cards']['L03-C1']['grade'],'MISS')

    def test_required_repair_cards_have_executable_checks(self):
        course=d.Course(ROOT)
        self.assertEqual(course.cards['L03-R1']['AcceptIf'],
                         'check(checks/l03/chk_schema.sh)')
        self.assertEqual(course.cards['L05-R4']['AcceptIf'],
                         'check(checks/l05/chk_frame.sh)')
        self.assertTrue(d.runnable(course.cards['L03-R1']))
        self.assertTrue(d.runnable(course.cards['L05-R4']))

    def test_missing_hint_does_not_record_assistance(self):
        course=d.Course(ROOT)
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10')
        driver.begin('L02-R1','new','L02','L02-INITIALIZATION')
        self.assertFalse(course.cards['L02-R1']['Hint'])
        self.assertFalse(driver.act('/hint'))
        self.assertFalse(state['pending']['hint'])

    def test_confident_miss_reviews_first_under_tight_budget(self):
        self.complete_course()
        # An ordinary earlier-named box-1 miss and a later-named confident miss are both due.
        for n in self.state['cards']:
            self.state['cards'][n]['next'] = '2026-12-31'
        self.state['cards']['L01-C1-R'].update(next='2026-11-20', box=1, grade='MISS',
                                               confidence='unsure', confident_miss=False)
        self.state['cards']['L05-C1-R'].update(next='2026-11-20', box=1, grade='MISS',
                                               confidence='sure', confident_miss=True)
        self.state['session']['last_topic'] = 'topic1'
        self.driver.session('2026-11-20', mode='quick', fresh=True, minutes=1)
        self.assertEqual(self.driver.select(), 'L05-C1-R')
        self.finish()
        self.assertIsNone(self.driver.select())   # the one-minute budget is spent on the flagged card

    def test_six_new_concepts_per_day_survive_new_session(self):
        self.driver.session('2026-11-10', fresh=True)
        self.state['session']['new_concepts'] = ['x'+str(i) for i in range(6)]
        self.driver.session('2026-11-10', fresh=True)
        self.assertEqual(len(self.state['session']['new_concepts']), 6)
        self.assertIsNone(self.driver.select())
        self.assertIn('daily limit', self.driver.close_text())
        self.assertIn('Return tomorrow', self.driver.close_text())
        self.driver.session('2026-11-11', fresh=True)
        self.assertEqual(self.state['session']['new_concepts'], [])
        self.assertEqual(self.driver.select(), 'L01-C1-P')

    def shared_workspace_course(self, name):
        course_root=self.base/name
        shutil.copytree(ROOT/'lessons',course_root/'lessons')
        (course_root/'manifest').mkdir()
        shutil.copy2(ROOT/'manifest/schedule.json',course_root/'manifest/schedule.json')
        shutil.copy2(ROOT/'manifest/cards.json',course_root/'manifest/cards.json')
        shutil.copytree(ROOT/'labs/l05/work',course_root/'labs/l05/work')
        return course_root, d.Course(course_root)

    def test_shared_workspace_starters_stay_pristine(self):
        course_root, course = self.shared_workspace_course('shared-course')
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10',minutes=20)
        source=course_root/'labs/l05/work/submission.hpp'
        pristine=source.read_bytes()
        driver.begin('L05-R1','new','L05','L05-FRAME')
        # The learner repairs R1 and also edits ahead into R2's and R3's TODOs.
        source.write_text('learner solved R1, R2 and R3 here')
        state['pending']=None
        driver.begin('L05-R2','new','L05','L05-REPLAY')
        state['pending']=None
        for n in ('L05-R1','L05-R2'):
            self.assertEqual(base64_file(state['starters'][n],'submission.hpp'),pristine)
        self.assertEqual(state['baselines']['labs/l05/work']['sha256'],state['starters']['L05-R2']['sha256'])
        state['cards']['L05-R2']={'box':1,'next':'2026-11-11','last':'2026-11-10',
                                   'grade':'HIT','confidence':'sure','confident_miss':False,'hint':False}
        driver.session('2026-11-11',minutes=20,fresh=True)
        driver.begin('L05-R2','review','L05','L05-REPLAY')
        fresh=course_root/state['pending']['default_workspace']/'submission.hpp'
        self.assertEqual(fresh.read_bytes(),pristine)

    def test_legacy_progress_without_baselines_reuses_first_starter(self):
        course_root, course = self.shared_workspace_course('legacy-shared-course')
        state=d.initial_state(course)
        driver=d.Driver(course,state)
        driver.session('2026-11-10',minutes=20)
        driver.begin('L05-R1','new','L05','L05-FRAME')
        state['pending']=None
        state.pop('baselines',None)               # shape of a progress file saved before this fix
        first=copy.deepcopy(state['starters']['L05-R1'])
        (course_root/'labs/l05/work/submission.hpp').write_text('edited after R1 opened')
        driver.begin('L05-R3','new','L05','L05-RELEASE')
        self.assertEqual(state['starters']['L05-R3'],first)
        self.assertEqual(state['starters']['L05-R1'],first)

    def test_cli_shows_fluency_warning(self):
        output=io.StringIO()
        script=self.base/'quit.txt'; script.write_text(':quit\n')
        with redirect_stdout(output):
            rc=d.main(['tools/driver-fixtures/lessons','--root',str(ROOT),
                       '--schedule','tools/driver-fixtures/schedule.json',
                       '--today','2026-11-10','--progress',str(self.base/'fluency.json'),
                       '--init','--auto',str(script)])
        self.assertEqual(rc,0)
        self.assertIn('Try to recall before looking. This may feel harder than rereading',output.getvalue())


def base64_file(record, name):
    return d.base64.b64decode(record['files'][name])


def main():
    global EVIDENCE
    ap=argparse.ArgumentParser()
    ap.add_argument('--evidence')
    args=ap.parse_args()
    if args.evidence:
        parent=Path(args.evidence).resolve()
        allowed=(ROOT/'manifest/evidence/wp5').resolve()
        if not parent.is_relative_to(allowed):
            ap.error('evidence must remain in manifest/evidence/wp5/')
        parent.mkdir(parents=True,exist_ok=True)
        EVIDENCE=Path(tempfile.mkdtemp(prefix='driver-',dir=parent))
        print('Evidence: '+str(EVIDENCE))
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(DriverTests)
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    log=stream.getvalue()
    print(log,end='')
    summary=dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
                 failures=len(result.failures),errors=len(result.errors))
    if EVIDENCE:
        (EVIDENCE/'tests.log').write_text(log)
        (EVIDENCE/'summary.json').write_text(json.dumps(summary,sort_keys=True)+'\n')
        (EVIDENCE/'check-probes.json').write_text(json.dumps(PROBES,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,sort_keys=True))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    sys.exit(main())
