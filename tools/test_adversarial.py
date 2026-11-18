#!/usr/bin/env python3
"""Regression cases for permissive oracles found by adversarial review."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'checks/l01'))
from oracle import LAYOUT, layout_matches
sys.path.insert(0, str(ROOT / 'checks/l05'))
from migration import grade as migration_grade
sys.path.insert(0, str(ROOT / 'checks/l03'))
from evolution import compatible, exercise_contract


class OracleTests(unittest.TestCase):
    def test_semantically_equivalent_decimal_and_optional_marker(self):
        layout = {k: copy.deepcopy(v) for k, v in LAYOUT.items() if k != 'source'}
        layout['price_decimal'] = '123.450'
        self.assertTrue(layout_matches(layout))

    def test_numeric_price_decimal_rejected(self):
        for bad in (123.45, 123, 123.4500):
            layout = {k: copy.deepcopy(v) for k, v in LAYOUT.items() if k != 'source'}
            layout['price_decimal'] = bad
            self.assertFalse(layout_matches(layout), bad)

    def test_boolean_offset_does_not_equal_zero(self):
        layout = copy.deepcopy(LAYOUT)
        layout['root_offsets']['orderId'] = False
        self.assertFalse(layout_matches(layout))

    def test_deleted_extensions_fail_schema_exercise_contract(self):
        base = ROOT / 'labs/l03'
        worked = base / 'worked/order-v1.xml'
        deleted = ROOT / 'checks/l03/fixtures/deleted-extensions/order-v1.xml'
        renamed = ROOT / 'checks/l03/fixtures/renamed-extension/order-v1.xml'
        self.assertFalse(compatible(base / 'order-v0.xml', deleted))
        self.assertTrue(exercise_contract(worked, base / 'order-v1.xml'))
        self.assertFalse(exercise_contract(deleted, base / 'order-v1.xml'))
        self.assertFalse(compatible(base / 'order-v0.xml', renamed))
        self.assertFalse(exercise_contract(renamed, base / 'order-v1.xml'))


class MigrationTests(unittest.TestCase):
    def _grade(self, mutate):
        import json, tempfile
        d = json.loads((ROOT / 'labs/l05/worked/migration.json').read_text())
        mutate(d)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'migration.json'
            f.write_text(json.dumps(d))
            return migration_grade(f)[0]

    def test_good_passes(self):
        self.assertTrue(self._grade(lambda d: None))

    def test_toy_only_non_list_rejected(self):
        self.assertFalse(self._grade(lambda d: d.update(toy_only={'fills': 1, 'trader': 1, 'note': 1, 'clientTag': 1})))
        self.assertFalse(self._grade(lambda d: d.update(toy_only='fills')))
        self.assertFalse(self._grade(lambda d: d.pop('toy_only')))

    def test_duplicates_rejected(self):
        self.assertFalse(self._grade(lambda d: d.update(toy_only=d['toy_only'] + [d['toy_only'][0]])))
        self.assertFalse(self._grade(lambda d: d.update(omitted=d['omitted'] + [d['omitted'][0]])))

    def test_unhashable_and_non_object_rejected(self):
        self.assertFalse(self._grade(lambda d: d.update(omitted=[[1], 'a', 'b', 'c'])))
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'm.json'
            f.write_text('[]')
            self.assertFalse(migration_grade(f)[0])


if __name__ == '__main__':
    unittest.main()
