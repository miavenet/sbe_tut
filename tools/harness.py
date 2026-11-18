#!/usr/bin/env python3
"""Process and fixture helpers used by the course checks."""
import atexit
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / 'labs/lib/sbe-all-1.42.0.jar'
OPEN = '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED'
SCHEMA_VERSION = 1

class InfraError(RuntimeError):
    """A broken environment or watchdog is exit 2, never a learner miss."""


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(f.read()).hexdigest()


def atomic_json(path, value):
    path = Path(path).resolve()
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('x') as f:
            json.dump(value, f, indent=2, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def java_argv(main, *args, classpath=None, properties=None, jvm_args=()):
    if properties or jvm_args:
        raise ValueError('Runtime wrapper has a fixed JVM configuration; use raw Java only in declared fault probes')
    return [str(ROOT / 'tools/sbe_tool.sh'), '--run',
            os.pathsep.join(map(str, classpath or [])), str(main)] + list(map(str, args))


def generation_argv(output, *schemas, language='Cpp', checked=False, ir=False, properties=None):
    props = dict(properties or {})
    props.update({'sbe.output.dir': str(output), 'sbe.target.language': language})
    if checked: props['sbe.generate.precedence.checks'] = 'true'
    if ir: props['sbe.generate.ir'] = 'true'
    return [str(ROOT / 'tools/sbe_tool.sh')] + [f'-D{k}={v}' for k,v in sorted(props.items())] + list(map(str, schemas))


def compile_argv(source, output, *, includes=(), checked=False, flags=()):
    return [str(ROOT / 'tools/compile.sh')] + (['--checked'] if checked else []) + [
        '-I' + str(p) for p in includes] + list(flags) + [str(source), '-o', str(output)]


def workspace_from_stdin(stream=None):
    """One literal path, or JSON {workspace: path}; never shell text/code."""
    text = (stream or sys.stdin).read(65537).strip()
    if not text or len(text) > 65536:
        raise InfraError('missing/oversized workspace reference')
    try:
        value = json.loads(text) if text.startswith('{') else text
        path = Path(value['workspace'] if isinstance(value, dict) else value).expanduser().resolve(strict=True)
    except (ValueError, KeyError, TypeError, OSError) as e:
        raise InfraError('invalid workspace reference: ' + str(e)) from e
    if not path.is_dir():
        raise InfraError('workspace must be a directory')
    return path


def result(code, criteria, **details):
    if code not in (0, 1, 2):
        raise ValueError('check exit must be 0 HIT, 1 MISS, or 2 INFRA')
    return dict(schema_version=1, status=['HIT', 'MISS', 'INFRA'][code],
                exit_code=code, criteria=criteria, **details)


def emit_result(report):
    """Machine record followed by concise learner feedback."""
    print(json.dumps(report, sort_keys=True))
    print('SETUP PROBLEM' if report['status'] == 'INFRA' else report['status'])
    for criterion in report['criteria']:
        if criterion['pass']:
            continue
        detail = str(criterion['detail']).replace('\\n', '\n')
        for line in re.split(r'\n|; ', detail):
            line = line.strip()
            if not line or re.match(r'^(?:at\s+\S+\(|#\d+\s+|In file included from )', line):
                continue
            print(f"{criterion['id']}: {line}")


def report_from_output(output):
    for line in output.splitlines():
        if not line.startswith('{'):
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get('schema_version') == 1:
            return value
    raise ValueError('check produced no machine-readable result')


class Ports:
    """Cooperative block lock plus actual TCP/UDP bind checks; never evicts."""
    offsets = {'archive': 1, 'ingress': 2, 'consensus': 3, 'log': 4, 'catchup': 5}

    def __init__(self, base=None, nodes=3):
        if not 1 <= nodes <= 3:
            raise ValueError('1..3 members per block')
        lock_root = ROOT / 'manifest/evidence/ports'
        lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.sockets, self.lock = [], None
        self.map = {}
        for candidate in ([base] if base is not None else range(20000, 50000, 300)):
            if candidate not in range(20000, 50000, 300):
                raise InfraError('base must be 20000 + 300*k, k=0..99')
            lock = (lock_root / str(candidate)).open('a+')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                endpoints = {f'node{n}.{name}': candidate + 100*n + off
                             for n in range(nodes) for name, off in self.offsets.items()}
                for port in endpoints.values():
                    for socktype in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
                        sock = socket.socket(socket.AF_INET, socktype)
                        self.sockets.append(sock)
                        sock.bind(('127.0.0.1', port))
                self.lock, self.base, self.map = lock, candidate, endpoints
                return
            except (BlockingIOError, OSError):
                self.release_bindings()
                lock.close()
        raise InfraError('no free owned port block; existing listeners were left alone')

    def release_bindings(self):
        for sock in self.sockets:
            sock.close()
        self.sockets = []

    def close(self):
        self.release_bindings()
        if self.lock:
            self.lock.close()
            self.lock = None


class Child:
    def __init__(self, run, name, argv, cwd, env, stdin, cap):
        self.name, self.run, self.cap = name, run, cap
        self.total, self.tail = 0, b''
        self.log = run.path / (name + '.log')
        self.status_path = run.path / (name + '.process.json')
        self.token = uuid.uuid4().hex
        self.started = time.monotonic()
        # The supervisor stays alive after the target exits, anchoring the process
        # group until cleanup. EOF on its control pipe also cleans up on parent death.
        cmd = [sys.executable, '-B', str(Path(__file__).resolve()), '--supervise',
               str(self.status_path), self.token, json.dumps(argv), stdin]
        self.proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        self.identity = {'pid': self.proc.pid, 'token': self.token, 'started_monotonic': self.started}
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()
        self.meta = dict(argv=argv, cwd=str(cwd), environment=env,
                         identity=self.identity, output_cap=cap)
        atomic_json(run.path / (name + '.launch.json'), self.meta)

    def _drain(self):
        with self.log.open('wb') as out:
            while True:
                chunk = self.proc.stdout.read1(4096)
                if not chunk:
                    break
                remaining = max(0, self.cap - self.total)
                out.write(chunk[:remaining])
                out.flush()
                self.total += len(chunk)
                self.tail = (self.tail + chunk)[-8192:]
        self.proc.stdout.close()

    def status(self):
        try:
            value = json.loads(self.status_path.read_text())
            if value['token'] != self.token:
                raise InfraError('child identity mismatch')
            return value
        except FileNotFoundError:
            return {}

    def poll(self):
        return self.status().get('exit_code')

    def events(self):
        # Events should use a dedicated atomic JSON file for high-volume logs.
        events = []
        if self.log.exists():
            for line in self.log.read_text(errors='replace').splitlines():
                try:
                    event = json.loads(line)
                    if isinstance(event, dict) and 'event' in event:
                        events.append(event)
                except ValueError:
                    pass
        return events

    def stop(self, grace=1.0):
        if self.proc.poll() is None:
            # Popen owns this unreaped supervisor PID; it cannot be reused here.
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                if self.proc.poll() is None:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)
        self.proc.stdin.close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise InfraError('output pipe held by escaped process; fixture must not detach')
        (self.run.path / (self.name + '.tail.log')).write_bytes(self.tail)
        atomic_json(self.run.path / (self.name + '.capture.json'), {
            'bytes_seen': self.total, 'truncated': self.total > self.cap,
            'sha256': sha256(self.log), 'supervisor_exit': self.proc.returncode,
            'target': self.status(), 'elapsed_s': time.monotonic() - self.started})


class Run:
    def __init__(self, package, *, parent=None, timeout=30, output_cap=1024*1024, ports=False):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', package):
            raise ValueError('invalid package/run name')
        if timeout <= 0 or output_cap < 1:
            raise ValueError('positive timeout and output cap required')
        self.package, self.timeout, self.output_cap = package, timeout, output_cap
        if parent is None:
            parent=ROOT / 'manifest/evidence/misc'
        Path(parent).mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix=package + '-', dir=parent)).resolve()
        self.token = uuid.uuid4().hex
        self.children, self.old_handlers = {}, {}
        self.ports, self.closed = None, False
        self.closing = False
        atomic_json(self.path / 'owner.json', {'schema_version': 1, 'token': self.token,
                                             'pid': os.getpid(), 'package': package})
        if ports:
            self.ports = Ports()
            atomic_json(self.path / 'ports.json', {'base': self.ports.base, 'endpoints': self.ports.map})
        atexit.register(self.close)

    def __enter__(self):
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                self.old_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, self._interrupt)
        return self

    def _interrupt(self, sig, frame):
        if self.closing:
            return  # Repeated TERM/INT must not interrupt owned-child cleanup.
        raise KeyboardInterrupt('signal ' + str(sig))

    def __exit__(self, *exc):
        self.close()

    def start(self, name, argv, *, cwd=None, env=None, stdin='', output_cap=None):
        if self.closed or name in self.children or not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            raise InfraError('closed run, duplicate or invalid child name')
        if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError('argv must be a nonempty list of strings, never shell text')
        # Explicit baseline avoids inheriting credentials/JAVA_TOOL_OPTIONS.
        child_env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C',
                     'LC_ALL': 'C', 'TMPDIR': str(self.path)}
        if os.environ.get('JAVA_HOME'):
            child_env['JAVA_HOME'] = os.environ['JAVA_HOME']
            child_env['PATH'] = str(Path(child_env['JAVA_HOME']) / 'bin') + os.pathsep + child_env['PATH']
        if os.environ.get('CXX'):
            child_env['CXX'] = os.environ['CXX']
        child_env.update(env or {})
        if self.ports:
            self.ports.release_bindings()  # Keep advisory lock until all children stop.
        child = Child(self, name, list(argv), Path(cwd or self.path).resolve(),
                      child_env, stdin, output_cap or self.output_cap)
        self.children[name] = child
        return child

    def until(self, predicate, *, timeout=None, description='barrier', children=()):
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            for child in children:
                if child.total > child.cap:
                    raise InfraError(f'{child.name}: output cap exceeded; artifacts: {self.path}')
            if predicate():
                return
            for child in children:
                if child.poll() is not None or child.proc.poll() is not None:
                    # Completion can occur between the predicate and this poll.
                    # Recheck the semantic barrier before calling it an early exit.
                    if predicate():
                        if any(c.total > c.cap for c in children):
                            raise InfraError(f'output cap exceeded; artifacts: {self.path}')
                        return
                    raise InfraError(f'{child.name} exited before {description}; artifacts: {self.path}')
            if time.monotonic() >= deadline:
                raise InfraError(f'timeout awaiting {description}; artifacts: {self.path}')
            time.sleep(0.01)

    def wait_event(self, child, event, *, timeout=None, **fields):
        self.until(lambda: any(e.get('event') == event and all(e.get(k) == v for k,v in fields.items())
                               for e in child.events()), timeout=timeout,
                   description=event, children=(child,))

    def wait(self, child, *, timeout=None):
        # A normal exit is the predicate, not an early-exit failure.
        self.until(lambda: child.poll() is not None, timeout=timeout,
                   description=child.name + ' exit', children=(child,))
        code = child.poll()
        self.stop(child)
        if child.total > child.cap:
            raise InfraError(f'{child.name}: output cap exceeded; artifacts: {self.path}')
        return code

    def stop(self, child):
        if self.children.get(child.name) is not child:
            raise InfraError('refusing to signal a process not owned by this run')
        child.stop()

    def close(self):
        if self.closed:
            return
        self.closing = True
        errors = []
        for child in reversed(list(self.children.values())):
            try:
                child.stop()
            except Exception as e:
                errors.append(str(e))
        if self.ports:
            self.ports.close()
        for sig, handler in self.old_handlers.items():
            signal.signal(sig, handler)
        self.closed = True
        atexit.unregister(self.close)
        atomic_json(self.path / 'cleanup.json', {'closed': True, 'errors': errors,
                                                'pids': [c.proc.pid for c in self.children.values()]})
        if errors:
            raise InfraError('; '.join(errors))

    def dispose(self):
        self.close()
        if json.loads((self.path / 'owner.json').read_text())['token'] != self.token:
            raise InfraError('refusing deletion: ownership marker changed')
        shutil.rmtree(self.path)  # Only explicit disposal; recovery dirs otherwise persist.


def supervise(status_path, token, argv, stdin):
    ending = [False]
    signal.signal(signal.SIGTERM, lambda *_: ending.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: ending.__setitem__(0, True))
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE)
    state = {'token': token, 'pid': proc.pid, 'exit_code': None}
    atomic_json(status_path, state)
    # Input is bounded by the caller; avoid blocking the supervisor on a full pipe.
    def feed():
        try:
            proc.stdin.write(stdin.encode())
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    threading.Thread(target=feed, daemon=True).start()
    while not ending[0]:
        code = proc.poll()
        if code is not None and state['exit_code'] is None:
            state['exit_code'] = code
            atomic_json(status_path, state)
        if select.select([sys.stdin], [], [], 0.02)[0] and not os.read(0, 1):
            ending[0] = True
    os.killpg(os.getpgrp(), signal.SIGTERM)
    try:
        proc.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    # Keep group identity anchored through the final kill, even with grandchildren.
    os.killpg(os.getpgrp(), signal.SIGKILL)


if __name__ == '__main__':
    if len(sys.argv) == 6 and sys.argv[1] == '--supervise':
        supervise(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), sys.argv[5])
    else:
        print('Import tools/harness.py for the course process and fixture helpers', file=sys.stderr)
        sys.exit(2)
