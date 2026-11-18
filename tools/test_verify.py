#!/usr/bin/env python3
"""Public verifier regression tests."""
import importlib.util
from pathlib import Path
import sys
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify', ROOT / 'tools/verify.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerifierTests(unittest.TestCase):
    def test_public_course(self):
        result = verify.verify(ROOT)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['lessons'], 5)

    def test_missing_key(self):
        card = {'id':'fixture', 'kind':'CARD', 'Q':'Recall this', 'Key':[], 'Source':'local', 'body':[]}
        with self.assertRaisesRegex(ValueError, 'key'):
            verify.validate_card(card, ROOT)

    def test_missing_executable(self):
        card = {'id':'fixture', 'kind':'CARD', 'Q':'Recall this', 'Key':['answer'], 'Source':'local',
                'body':[], 'AcceptIf':'check(checks/does-not-exist.sh)'}
        with self.assertRaisesRegex(ValueError, 'executable'):
            verify.validate_card(card, ROOT)

    def test_missing_executable_on_parsed_card(self):
        card = dict(verify.Course(ROOT).cards['L03-C1'])
        card['AcceptIf'] = 'check(checks/does-not-exist.sh)'
        with self.assertRaisesRegex(ValueError, 'executable'):
            verify.validate_card(card, ROOT)

    def test_release_inventory_includes_shipped_starters(self):
        files = verify.release_files(ROOT)
        for name in ('labs/l01/work/submission.hpp',
                     'labs/l03/composite-work/order-v1.xml',
                     'labs/l04/validation-completion/submission.hpp',
                     'labs/l05/enum-work/submission.hpp'):
            self.assertIn(name, files)

    def test_lesson_metadata_residue_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='metadata-audit-',dir=ROOT) as directory:
            root=Path(directory)
            (root/'lessons').mkdir()
            (root/'lessons/lesson-01.md').write_text('### Card L01-P1 · Guess [type: pretest]\n')
            with self.assertRaisesRegex(ValueError,'lesson metadata remains'):
                verify.verify_lesson_metadata(root)

    def test_story_source_residue_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='story-metadata-audit-',dir=ROOT) as directory:
            root=Path(directory)
            (root/'lessons').mkdir()
            lesson=root/'lessons/lesson-01.md'
            lesson.write_text('A story.\nStory source URL: https://example.org/report\n')
            with self.assertRaisesRegex(ValueError,'lesson metadata remains'):
                verify.verify_lesson_metadata(root)
            lesson.write_text('A story (https://example.org/report).\n')
            with self.assertRaisesRegex(ValueError,'lesson source URL remains'):
                verify.verify_lesson_metadata(root)
            lesson.write_text('- Verified with: local probe\n')
            with self.assertRaisesRegex(ValueError,'lesson metadata remains'):
                verify.verify_lesson_metadata(root)

    def test_time_estimate_detects_card_drift(self):
        course = verify.Course(ROOT)
        verify.verify_time_estimates(course)
        course.cards['L01-P1']['minutes'] = str(float(course.cards['L01-P1']['minutes']) + 1)
        with self.assertRaisesRegex(ValueError, 'time estimate'):
            verify.verify_time_estimates(course)

    def test_judgement_cards_are_delayed_objective_transfers(self):
        course=verify.Course(ROOT)
        objectives={o['id']:o for o in course.objectives}
        self.assertIn('L04-J1',objectives['WP3-O4']['transfer'])
        self.assertIn('L05-J1',objectives['WP4-O5']['transfer'])

    def test_broken_local_markdown_link(self):
        with tempfile.TemporaryDirectory(prefix='link-audit-', dir=ROOT) as directory:
            root = Path(directory)
            (root / 'README.md').write_text('[missing](elsewhere.md)\n')
            with self.assertRaisesRegex(ValueError, 'broken Markdown link'):
                verify.verify_local_links(root)

    def test_refresh_helpers_help_does_not_write(self):
        paths=[ROOT/'manifest/schedule.json',ROOT/'README.md']
        before=[p.stat().st_mtime_ns for p in paths]
        for script in ('refresh_estimates.py',):
            got=subprocess.run([sys.executable,'-B',str(ROOT/'tools'/script),'--help'],
                               capture_output=True,text=True,check=True)
            self.assertIn('usage:',got.stdout)
        self.assertEqual(before,[p.stat().st_mtime_ns for p in paths])

    def test_refresh_estimates_matches_published_text(self):
        published=['README.md','manifest/course.md','manifest/schedule.json','labs/l02/deeper-pack.md',
                   'labs/l03/README.md','labs/l05/README.md']
        with tempfile.TemporaryDirectory(prefix='estimate-refresh-',dir=ROOT) as directory:
            root=Path(directory)
            for name in ['drive.py','tools/refresh_estimates.py','tools/harness.py','manifest/cards.json']+published:
                (root/name).parent.mkdir(parents=True,exist_ok=True)
                (root/name).write_bytes((ROOT/name).read_bytes())
            shutil.copytree(ROOT/'lessons',root/'lessons')
            script=[sys.executable,'-B',str(root/'tools/refresh_estimates.py')]
            subprocess.run(script,capture_output=True,text=True,check=True)
            for name in published:
                self.assertEqual((root/name).read_bytes(),(ROOT/name).read_bytes(),name)
            readme=root/'README.md'
            readme.write_text(readme.read_text().replace('takes an estimated 8 hours','takes an estimated 99 hours'))
            course=root/'manifest/course.md'
            course.write_text(course.read_text().replace('first-pass lessons 239,','first-pass lessons 1,'))
            subprocess.run(script,capture_output=True,text=True,check=True)
            for name in published:
                self.assertEqual((root/name).read_bytes(),(ROOT/name).read_bytes(),name)


if __name__ == '__main__':
    unittest.main()
