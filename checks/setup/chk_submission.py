#!/usr/bin/env python3
"""ABI conformance fixture, not an SBE objective: execute submitted main.cpp."""
import json
import shutil
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from harness import Run, InfraError, workspace_from_stdin, compile_argv, result

def main():
    try:
        work = workspace_from_stdin()
        if not (shutil.which('clang++') or shutil.which('g++')):
            raise InfraError('C++17 compiler is missing; install clang++ or g++')
        if not (work/'main.cpp').is_file():
            raise InfraError('workspace/main.cpp is missing')
        with Run('abi-submission', timeout=5) as run:
            c = run.start('compile', compile_argv(work/'main.cpp', run.path/'answer'))
            compile_code = run.wait(c)
            if compile_code < 0 or compile_code in (126, 127):
                raise InfraError('compiler could not run')
            if compile_code != 0:
                return result(1, [{'id':'compile','pass':False,'detail':'Fix the compiler diagnostic in '+str(c.log)}])
            c = run.start('answer', [str(run.path/'answer')])
            code = run.wait(c)
            if code < 0:
                raise InfraError('submission ended by unexpected signal')
            ok = code == 0 and c.log.read_bytes() == b'42\n'
            report = result(0 if ok else 1, [{'id':'value','pass':ok,'detail':'Expected 42 followed by newline; check the computed value.'}])
        run.dispose()
        return report
    except (InfraError, OSError) as e:
        return result(2, [{'id':'infrastructure','pass':False,'detail':str(e)}])
if __name__ == '__main__':
    report=main();print(json.dumps(report,sort_keys=True));sys.exit(report['exit_code'])
