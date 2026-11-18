#!/usr/bin/env python3
"""Toolchain version warnings and genuine jar minimum."""
import os
from pathlib import Path
import subprocess
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Run

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='setup-test-',dir=ROOT) as name:
    fake=Path(name)
    for tool in ('java','javac'):
        script=fake/tool
        script.write_text("#!/bin/sh\nprintf '%s\\n' '"+('openjdk version "21.0.1"' if tool=='java' else 'javac 21.0.1')+"' >&2\n")
        script.chmod(0o755)
    env=dict(os.environ,PATH=str(fake)+os.pathsep+os.environ['PATH'])
    env.pop('JAVA_HOME',None)
    completed=subprocess.run(['bash','tools/setup.sh','--check'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert completed.returncode==0 and 'WARNING: tested with' in completed.stdout and 'SETUP PASS' in completed.stdout,completed
    for tool in ('java','javac'):
        script=fake/tool
        script.write_text("#!/bin/sh\nprintf '%s\\n' '"+('openjdk version "11.0.1"' if tool=='java' else 'javac 11.0.1')+"' >&2\n")
    completed=subprocess.run(['bash','tools/setup.sh','--check'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert completed.returncode==2 and 'class-file major 61' in completed.stderr and 'macOS:' in completed.stderr and 'Linux:' in completed.stderr,completed
    selected=fake/'selected'
    (selected/'bin').mkdir(parents=True)
    for tool in ('java','javac'):
        script=selected/'bin'/tool
        script.write_text("#!/bin/sh\nprintf '%s\\n' selected-jdk\n")
        script.chmod(0o755)
    prior=os.environ.get('JAVA_HOME')
    prior_path=os.environ.get('PATH')
    try:
        os.environ['JAVA_HOME']=str(selected)
        os.environ['PATH']=env['PATH']
        with Run('selected-jdk',parent=fake,timeout=5) as run:
            for tool in ('java','javac'):
                child=run.start(tool,[tool,'-version'],cwd=ROOT)
                assert run.wait(child)==0
                assert 'selected-jdk' in child.log.read_text()
    finally:
        if prior is None:os.environ.pop('JAVA_HOME',None)
        else:os.environ['JAVA_HOME']=prior
        if prior_path is None:os.environ.pop('PATH',None)
        else:os.environ['PATH']=prior_path
print('setup tests: 3 passed')
