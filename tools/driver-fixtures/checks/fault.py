#!/usr/bin/env python3
"""Hostile check modes for testing the driver's process supervisor."""
import json
import os
import signal
import sys
import time
mode = sys.stdin.read().strip()
if mode == 'timeout':
    time.sleep(20)
elif mode == 'signal':
    os.kill(os.getpid(), signal.SIGTERM)
elif mode == 'noise':
    sys.stdout.write('x' * 1100000)
elif mode == 'mismatch':
    print(json.dumps({'schema_version': 1, 'exit_code': 1, 'status': 'MISS', 'criteria': []}))
elif mode == 'false-hit':
    print(json.dumps({'schema_version': 1, 'exit_code': 0, 'status': 'HIT', 'criteria': [{'id': 'x', 'pass': False, 'detail': 'failed'}]}))
elif mode == 'null-report':
    print('null')
elif mode == 'bad-criteria':
    print(json.dumps({'schema_version': 1, 'exit_code': 0, 'status': 'HIT', 'criteria': ['passed']}))
else:
    print('not a JSON result')
