#!/usr/bin/env python3
# [claim: WP4-COMMANDS]
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from lesson_commands import run_paths
count,artifacts=run_paths(['lessons/lesson-05.md'])
result={'status':'PASS','commands':count}
result['artifacts']=artifacts
print(json.dumps(result,sort_keys=True))
