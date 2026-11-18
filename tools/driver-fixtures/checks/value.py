#!/usr/bin/env python3
"""Synthetic check only: JSON value=42, or workspace containing answer.json."""
import json
from pathlib import Path
import sys
try:
    raw = sys.stdin.read().strip()
    obj = json.loads(raw) if raw.startswith('{') else {'workspace': raw}
    if 'workspace' in obj:
        obj = json.loads((Path(obj['workspace']) / 'answer.json').read_text())
    ok = type(obj.get('value')) is int and obj['value'] == 42
    code = 0 if ok else 1
    detail = 'value equals 42' if ok else 'value must equal 42; correct the submitted value'
except (OSError, ValueError, KeyError, TypeError):
    code, ok, detail = 2, False, 'cannot read submitted JSON/workspace'
print(json.dumps({'schema_version': 1, 'status': ['HIT', 'MISS', 'INFRA'][code], 'exit_code': code,
                  'criteria': [{'id': 'value', 'pass': ok, 'detail': detail}], 'next_action': detail}))
sys.exit(code)
