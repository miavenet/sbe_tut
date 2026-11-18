#!/usr/bin/env python3
"""Deterministic offline course driver for the public tutorial."""
import argparse
import base64
import binascii
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools'))
from harness import Run, InfraError, atomic_json, report_from_output

# Tested behavior of the learner-facing prompts and transitions:
# [claim: WP5-STATE] [claim: WP5-GRADE] [claim: WP5-SCHEDULE]
# [claim: WP5-EXAM] [claim: WP5-MODEL]

MODEL = 'Optional model tutor'
GAPS = (1, 3, 7, 14)
CARD_RE = re.compile(r'^###\s+(Card|Concept)\s+(\S+)\s+·\s+(.+)$')
FIELD_RE = re.compile(r'^(Q|Key|Hint|Predict|Vocabulary|Elaborate):\s*(.*)$')
SKIPS = {'skip', "don't know", "i don't know", 'do not know', '/skip'}
COMMANDS = ':help :status :skip :hint :quit (aliases: /help /status /skip /hint /stop /retry /edit)'


def runnable(card):
    q = card.get('Q', '').lower()
    return bool(re.fullmatch(r'check\([^)]+\)', card.get('AcceptIf', '')) and
                ('submit json' not in q and
                 (re.search(r'labs/l\d\d/(?:work|independent|completion|solution|enum-work|composite-work|validation-completion)', q)
                  or 'independent workspace' in q)))


def asks_explanation(card):
    return bool(re.fullmatch(r'check\([^)]+\)', card.get('AcceptIf', '')) and
                explanation_bullets(card))


def explanation_bullets(card):
    """Only bullets explicitly marked as explanation criteria need self-report after a lab HIT."""
    return [bullet for bullet in card['Key']
            if re.match(r'^(?:\([a-z]\) )?Explain: ', bullet)]


WORKSPACE_RE = re.compile(r'labs/l\d\d/(?:validation-completion|composite-work|enum-work|independent|completion|solution|work)')
DAILY_NEW_CONCEPTS = 6
FLUENCY_WARNING = ('Try to recall before looking. This may feel harder than rereading; '
                   'familiarity is not the delayed performance we are checking.')


def card_workspace(card):
    """The workspace a runnable card names in its question, if any."""
    found = WORKSPACE_RE.findall(card.get('Q', ''))
    if found:
        return found[0]
    if 'independent workspace' in card.get('Q', '').lower():
        return f"labs/{card.get('lesson', '').replace('lesson-', 'l')}/independent"
    return None


def is_existing_workspace_path(value):
    """An absolute existing path is input to a lab, not a slash command."""
    return value.startswith('/') and Path(value).exists()


def clean_terminal(value):
    value = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', value)
    value = re.sub(r'(?m)^Source:.*$', '', value)
    value = re.sub(r'(?m)^```[^\n]*$|^</?details>.*$', '', value)
    value = re.sub(r'(?m)^#{1,6}\s+', '', value)
    value = value.replace('**', '').replace('`', '')
    return value.strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError('duplicate JSON key: ' + k)
            out[k] = v
        return out
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def plus(day, gap):
    return (dt.date.fromisoformat(day) + dt.timedelta(days=gap)).isoformat()


def parse_cards(lessons_dir, manifest_path):
    """Keep multiline prompts/keys and worked bodies; stop at any heading."""
    manifest = read_json(manifest_path)
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('cards'), dict):
        raise ValueError('invalid card manifest schema')
    metadata = manifest['cards']
    cards = {}
    for path in sorted(Path(lessons_dir).glob('*.md')):
        node = None
        field = None
        for line in path.read_text().splitlines():
            m = CARD_RE.match(line)
            if m:
                kind, cid, label = m.groups()
                if cid in cards:
                    raise ValueError('duplicate card: ' + cid)
                node = dict(id=cid, kind=kind.upper(), lesson=path.stem, body=[], Key=[],
                            Q='', Hint='', Predict='', Vocabulary='', Elaborate='')
                cards[cid] = node
                field = None
                continue
            if line.startswith('## '):
                node = None
            if node is None:
                continue
            s = line.strip()
            if s in ('<details>', '</details>') or s.startswith(('<summary>', '<details><summary>')) or s == '---':
                continue
            fm = FIELD_RE.match(s)
            if fm:
                field, val = fm.groups()
                if field == 'Key':
                    node[field] = []
                else:
                    node[field] = val
            elif field == 'Key' and s.startswith('- '):
                node[field].append(s[2:])
            elif field == 'Key' and line.startswith(('  ', '\t')) and s:
                node[field][-1] += ' ' + s
            elif field in ('Q', 'Hint', 'Predict', 'Vocabulary', 'Elaborate') and line.startswith(('  ', '\t')):
                node[field] += '\n' + s
            elif node['kind'] == 'CONCEPT' and s:
                node['body'].append(line)
    if set(metadata) != set(cards):
        raise ValueError('card manifest mismatch: missing ' + ','.join(sorted(set(cards)-set(metadata))) +
                         '; extra ' + ','.join(sorted(set(metadata)-set(cards))))
    for cid, c in cards.items():
        row = metadata[cid]
        expected = {'kind', 'lesson', 'type', 'topic', 'minutes', 'Source', 'AcceptIf', 'RejectIf'}
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError('malformed card manifest row: ' + cid)
        if row['kind'] != c['kind'] or row['lesson'] != c['lesson'] or not isinstance(row['Source'], str) or not row['Source'].strip():
            raise ValueError('malformed card manifest row: ' + cid)
        if ((c['kind'] == 'CARD' and
             (not isinstance(row['type'], str) or not row['type'] or
              not isinstance(row['topic'], str) or not row['topic'])) or
            (c['kind'] == 'CONCEPT' and (row['type'] is not None or row['topic'] is not None))):
            raise ValueError('malformed card manifest row: ' + cid)
        try:
            cost = float(row['minutes'])
        except (TypeError, ValueError):
            raise ValueError('malformed card manifest minutes: ' + cid)
        if not 0 < cost <= 7:
            raise ValueError('malformed card manifest minutes: ' + cid)
        if not isinstance(row['AcceptIf'], str) or not isinstance(row['RejectIf'], str):
            raise ValueError('malformed card manifest grade: ' + cid)
        c.update(row)
        c['minutes'] = str(row['minutes'])
        if c['kind'] == 'CARD' and (not c['Q'] or not c['Key']):
            raise ValueError('missing Q/Key: ' + c['id'])
        if c['AcceptIf'] and not re.fullmatch(r'check\([^)]+\)', c['AcceptIf']):
            if not c['RejectIf']:
                raise ValueError('regex needs RejectIf: ' + c['id'])
            regex_predicate(c['AcceptIf'], '')
            regex_predicate(c['RejectIf'], '')
    return cards


def lesson_text(lessons_dir):
    """Keep authored context and instructions without moving any answer key."""
    result = {}
    for path in sorted(Path(lessons_dir).glob('*.md')):
        lines = path.read_text().splitlines()
        pending = []
        current = None
        for line in lines:
            match = CARD_RE.match(line)
            if match:
                current = match[2]
                result[current] = {'lead': '\n'.join(pending).strip(),
                                   'heading': line, 'kind': match[1].upper(), 'raw': []}
                pending = []
            elif line.startswith('## '):
                current = None
                pending.append(line)
            elif current is None:
                pending.append(line)
            else:
                result[current]['raw'].append(line)
        if pending and result:
            # A final optional section remains accessible after the last card.
            last = next(reversed(result))
            result[last]['ending'] = '\n'.join(pending).strip()
    for item in result.values():
        ending = item.get('ending', '')
        match = re.search(r'<details>.*?</details>', ending, re.S)
        if match:
            item['ending_before'] = ending[:match.start()].strip()
            item['ending_after'] = ending[match.start():].strip()
            item.pop('ending')
        lines = item.pop('raw')
        if item['kind'] == 'CONCEPT':
            item['worked'] = item['heading'] + '\n' + '\n'.join(lines).strip()
        before, after = [], []
        hidden = False
        seen_key = False
        had_details = False
        in_question = False
        for line in lines:
            if line.startswith('Q:'):
                in_question = True
                continue
            if in_question and (line.startswith(('  ', '\t')) or not line.strip()):
                continue
            in_question = False
            if line.lstrip().startswith('<details>'):
                hidden = True
                seen_key = True
                had_details = True
                continue
            if hidden:
                if '</details>' in line:
                    hidden = False
                continue
            if re.match(r'^(Key):', line.strip()):
                seen_key = True
                continue
            (after if seen_key else before).append(line)
        # Instructions following a folded key are still needed before the task.
        item['before'] = '\n'.join(before + (after if had_details else [])).strip()
        item['after'] = '' if had_details else '\n'.join(after).strip()
    return result


def regex_predicate(expr, answer):
    """Small, explicit AND/OR grammar; never eval or substring fallback."""
    token = r'regex\(/((?:\\.|[^/])*)/([i]*)\)'
    pos, values, ops = 0, [], []
    while True:
        m = re.compile(token).match(expr, pos)
        if not m:
            raise ValueError('unsupported predicate: ' + expr)
        values.append(bool(re.search(m[1], answer, re.I if m[2] else 0)))
        pos = m.end()
        if pos == len(expr):
            break
        op = re.match(r'\s+(AND|OR)\s+', expr[pos:])
        if not op:
            raise ValueError('unsupported predicate: ' + expr)
        ops.append(op[1])
        pos += op.end()
    result = values[0]
    for op, val in zip(ops, values[1:]):
        result = result and val if op == 'AND' else result or val
    return result


class Course:
    def __init__(self, root, lessons='lessons', schedule='manifest/schedule.json'):
        self.root = Path(root).resolve()
        self.cards = parse_cards(self.root / lessons, self.root / Path(schedule).parent / 'cards.json')
        self.text = lesson_text(self.root / lessons)
        self.config = read_json(self.root / schedule)
        if self.config.get('schema_version') != 1:
            raise ValueError('unsupported schedule version')
        self.lessons = self.config['lessons']
        self.concepts = {}
        self.card_concept = {}
        self.lesson_ids = []
        all_order = []
        for lesson in self.lessons:
            lid = lesson['id']
            if lid in self.lesson_ids:
                raise ValueError('duplicate lesson')
            if any(p not in self.lesson_ids for p in lesson.get('requires', [])):
                raise ValueError('prerequisite must precede lesson')
            self.lesson_ids.append(lid)
            for concept in lesson['concepts']:
                cid = concept['id']
                if cid in self.concepts:
                    raise ValueError('duplicate concept')
                concept = dict(concept, lesson=lid)
                self.concepts[cid] = concept
                order = concept['pretests'] + [concept['worked']] + concept['completion'] + concept['independent']
                if not concept['pretests'] or not concept['completion'] or not concept['independent']:
                    raise ValueError('missing fade phase: ' + cid)
                for key, kinds in [('pretests', {'pretest'}), ('completion', {'completion'}),
                                   ('independent', {'recall', 'transfer', 'apply', 'analyze'})]:
                    for n in concept[key]:
                        if self.cards[n].get('type') not in kinds:
                            raise ValueError('wrong phase type: ' + n)
                worked = self.cards[concept['worked']]
                if worked['kind'] != 'CONCEPT' or not all(worked[k] for k in ('Predict', 'Vocabulary', 'Elaborate', 'body', 'Source')):
                    raise ValueError('worked needs vocabulary/prediction/body/elaboration/source')
                for n in order:
                    self.card_concept[n] = cid
                all_order += order
            for n in lesson['integrate']:
                if self.cards[n].get('type') != 'synthesize':
                    raise ValueError('integration needs synthesize type')
            if not lesson['integrate']:
                raise ValueError('missing integration')
            all_order += lesson['integrate']
        if len(set(all_order)) != len(all_order) or set(all_order) != set(self.cards):
            raise ValueError('schedule must cover each card/concept exactly once')
        self.objectives = self.config['objectives']
        if len({o['id'] for o in self.objectives}) != len(self.objectives) or not self.objectives:
            raise ValueError('duplicate/missing objectives')
        for obj in self.objectives:
            if not obj['production'] or not obj['transfer']:
                raise ValueError('objective needs production and varied transfer')
            for kind in ('production', 'transfer'):
                for n in obj[kind]:
                    expected = {'recall'} if kind == 'production' else {'apply', 'transfer', 'analyze'}
                    if self.cards[n].get('type') not in expected or n not in self.card_concept:
                        raise ValueError('invalid objective role: ' + n)
        material = {'config': self.config, 'cards': self.cards}
        self.fingerprint = digest(json.dumps(material, sort_keys=True).encode())

    def order(self, lesson):
        out = []
        for spec in lesson['concepts']:
            c = self.concepts[spec['id']]
            out += c['pretests'] + [c['worked']] + c['completion'] + c['independent']
        return out + lesson['integrate']


def initial_state(course):
    return dict(schema_version=1, course_hash=course.fingerprint, lesson=None,
                history_id=uuid.uuid4().hex, starters={}, baselines={},
                concept=None, phase='idle', card=None, pretests_committed={},
                pending=None, cards={}, completed=[], concepts={}, lessons={},
                objectives={o['id']: {'production': {}, 'transfer': {}, 'passed': False}
                            for o in course.objectives}, exam={'attempts': {}},
                work={}, checkpoint=None, session=None, history=[], appendix=None)


PRE_DECLUTTER_HASH = '4597c54de39dd70e0ea997584661f046c093a81f0ed760b70da3175f789737b0'
REVISED_KEYS = frozenset({'L01-INT', 'L03-INT', 'L04-R2', 'L04-R3'})
UNSUPPORTED_REVISION = ('Course revision changed; this progress file has not been modified. '
                        'Resume with its original course revision or apply a supported migration.')


def migrate_progress(course, state, today):
    """Move the audited pre-declutter contract without discarding learner work."""
    if state.get('schema_version') != 1:
        raise ValueError('unsupported progress version')
    if state.get('course_hash') == course.fingerprint:
        return state
    if state.get('course_hash') != PRE_DECLUTTER_HASH:
        raise ValueError(UNSUPPORTED_REVISION)
    updated = copy.deepcopy(state)
    known = set(course.cards)
    if (set(updated.get('cards', {})) - known or set(updated.get('completed', [])) - known
            or (updated.get('pending') and updated['pending'].get('card') not in known)):
        raise ValueError(UNSUPPORTED_REVISION)
    if any(runnable(course.cards[n]) and n not in updated.get('starters', {})
           for n in updated.get('completed', [])):
        raise ValueError(UNSUPPORTED_REVISION)
    for n, record in updated.get('starters', {}).items():
        if (n not in known or not runnable(course.cards[n]) or
                not isinstance(record, dict) or
                record.get('fingerprint') != PRE_DECLUTTER_HASH or
                not isinstance(record.get('files'), dict) or not record['files'] or
                record.get('sha256') != digest(json.dumps(record['files'], sort_keys=True).encode())):
            raise ValueError(UNSUPPORTED_REVISION)
        for name, encoded in record['files'].items():
            rel = Path(name)
            if rel.is_absolute() or '..' in rel.parts or not name or not isinstance(encoded, str):
                raise ValueError(UNSUPPORTED_REVISION)
            try:
                base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError(UNSUPPORTED_REVISION) from exc
        # The audited declutter moved runnable grading rules to cards.json unchanged.
        record['fingerprint'] = course.fingerprint
    for n in REVISED_KEYS & updated.get('cards', {}).keys():
        old = updated['cards'][n]
        updated['cards'][n] = dict(old, grade='STALE', box=1, next=today,
                                   previous_last=old.get('last'))
    if updated.get('pending') and updated['pending']['card'] in REVISED_KEYS:
        updated['pending'].update(stage='answer', confidence=None, grade=None,
                                  result=None, hint=False)
    for spec in course.objectives:
        old = updated.setdefault('objectives', {}).get(spec['id'], {})
        entry = {kind: {n: day for n, day in old.get(kind, {}).items()
                        if n in spec[kind] and n not in REVISED_KEYS}
                 for kind in ('production', 'transfer')}
        entry['passed'] = all(all(n in entry[kind] for n in spec[kind])
                              for kind in ('production', 'transfer'))
        updated['objectives'][spec['id']] = entry
    updated['course_hash'] = course.fingerprint
    return updated


def capture_starter(path, fingerprint):
    """Keep the exact pre-edit files in progress so a restored history is reproducible."""
    files = {}
    for item in path.rglob('*'):
        if item.is_symlink():
            raise ValueError('review starter cannot contain a symlink')
        if item.is_file():
            files[item.relative_to(path).as_posix()] = base64.b64encode(item.read_bytes()).decode('ascii')
    if not files:
        raise ValueError('review starter is empty: ' + str(path))
    return {'fingerprint': fingerprint, 'files': files,
            'sha256': digest(json.dumps(files, sort_keys=True).encode())}


def restore_starter(record, path, fingerprint):
    if (not record or record.get('fingerprint') != fingerprint or
            record.get('sha256') != digest(json.dumps(record.get('files', {}), sort_keys=True).encode())):
        raise ValueError('review starter unavailable or changed; restore a matching progress file or restart this lesson')
    if path.exists():
        shutil.rmtree(path)
    for name, value in record['files'].items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('invalid review starter path')
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(value, validate=True))


def archive_progress(path, today):
    """Archive the exact old bytes without replacing an earlier archive."""
    path = Path(path).resolve()
    stem = path.name[:-5] if path.name.endswith('.json') else path.name
    number = 0
    while True:
        suffix = '' if number == 0 else f'.{number}'
        archive = path.with_name(f'{stem}.{today}.bak{suffix}.json')
        try:
            os.link(path, archive)
            return archive
        except FileExistsError:
            number += 1
        except OSError:
            try:
                with path.open('rb') as source, archive.open('xb') as output:
                    output.write(source.read())
                return archive
            except FileExistsError:
                number += 1
            except BaseException:
                archive.unlink(missing_ok=True)
                raise


def reset_state(course, target, today, lesson=None):
    """Archive once, then atomically replace either the whole or one lesson state."""
    dt.date.fromisoformat(today)
    target = Path(target).resolve()
    if lesson is None:
        updated = initial_state(course)
        label = 'all progress'
    else:
        valid = course.lesson_ids
        requested = lesson.replace('\\', '/').removeprefix('./')
        matches = [lid for lid in valid if requested in (lid, lid.lower(),
                   f'lesson-{lid[1:].lower()}', f'lesson-{lid[1:].lower()}.md',
                   f'lessons/lesson-{lid[1:].lower()}.md')]
        if len(matches) != 1:
            raise ValueError(f'unknown lesson {lesson!r}; valid lessons: ' + ', '.join(valid))
        lid = matches[0]
        state = read_json(target) if target.exists() else initial_state(course)
        Driver(course, state)
        updated = copy.deepcopy(state)
        stems = {course.cards[spec['worked']]['lesson'] for spec in course.concepts.values()
                 if spec['lesson'] == lid}
        ids = {n for n, card in course.cards.items() if card['lesson'] in stems}
        concepts = {cid for cid, spec in course.concepts.items() if spec['lesson'] == lid}
        for key in ('pretests_committed', 'cards', 'work'):
            for n in ids:
                updated[key].pop(n, None)
        updated['completed'] = [n for n in updated['completed'] if n not in ids]
        for cid in concepts:
            updated['concepts'].pop(cid, None)
        updated['lessons'].pop(lid, None)
        for spec in course.objectives:
            objective = updated['objectives'][spec['id']]
            for kind in ('production', 'transfer'):
                for n in ids:
                    objective[kind].pop(n, None)
            objective['passed'] = all(all(n in objective[kind] for n in spec[kind])
                                      for kind in ('production', 'transfer'))
        for n in ids:
            updated['exam']['attempts'].pop(n, None)
        if updated['checkpoint'] and updated['checkpoint'].get('card') in ids:
            updated['checkpoint'] = None
        if updated.get('appendix') and updated['appendix'].get('card') in ids:
            updated['appendix'] = None
        if updated['pending'] and updated['pending'].get('card') in ids:
            updated.update(pending=None, lesson=None, concept=None, phase='idle', card=None)
        if not updated['pending'] and updated.get('card') in ids:
            updated.update(lesson=None, concept=None, phase='idle', card=None)
        if not updated['pending']:
            updated['session'] = None
        label = f'lesson {lid}'
    if not target.exists():
        return None, label
    archive = archive_progress(target, today)
    atomic_json(target, updated)
    return archive, label


def interleave(ids, cards, last=None):
    pool, out = list(ids), []
    while pool:
        n = next((n for n in pool if cards[n].get('topic') != last), pool[0])
        pool.remove(n)
        out.append(n)
        last = cards[n].get('topic')
    return out


def check_answer(card, answer, course, timeout=120):
    if answer.strip().lower() in SKIPS:
        return {'grade': 'MISS', 'detail': 'Explicit skip; compare your attempt with each Key bullet.'}
    expr = card['AcceptIf']
    if not expr:
        return {'grade': 'SELF', 'detail': 'Honest bullet-level self-report; no semantic auto-grade.'}
    cm = re.fullmatch(r'check\(([^)]+)\)', expr)
    if not cm:
        rejected = regex_predicate(card['RejectIf'], answer)
        ok = not rejected and regex_predicate(expr, answer)
        return {'grade': 'HIT' if ok else 'MISS', 'detail': 'Guarded surface-form check; compare the Key for meaning.'}
    path = (course.root / cm[1]).resolve()
    if not path.is_relative_to(course.root) or not path.is_file() or not os.access(path, os.X_OK):
        return {'grade': 'INFRA', 'detail': 'Check missing, outside course, or not executable.'}
    # Process supervisors own descendants and clean them on timeout/interrupt.
    scratch=course.root / 'manifest/evidence/grade'
    scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sbe-grade-',dir=scratch) as tmp:
        raw, code, child = '', None, None
        try:
            with Run('wp5-grade', parent=tmp, timeout=timeout) as run:
                child = run.start('submission', [str(path)], cwd=course.root, stdin=answer + '\n')
                try:
                    code = run.wait(child, timeout=timeout)
                except InfraError as exc:
                    # until() can observe the target's new exit between its
                    # predicate and early-exit probe. Re-enter its normal wait
                    # only for that exact race with an available target status.
                    # The second wait still enforces output caps and cleanup.
                    if str(exc).startswith('submission exited before submission exit;') and child.poll() is not None:
                        code = run.wait(child, timeout=timeout)
                    else:
                        raise
                raw = child.log.read_text()
                if code not in (0, 1, 2):
                    raise InfraError('unexpected check exit: ' + str(code))
                report = report_from_output(raw)
                if not isinstance(report, dict) or report.get('schema_version') != 1 or report.get('exit_code') != code or report.get('status') != ['HIT', 'MISS', 'INFRA'][code]:
                    raise InfraError('check result/exit mismatch')
                criteria = report['criteria']
                if not isinstance(criteria, list) or not criteria or any(not isinstance(c, dict) or not isinstance(c.get('pass'), bool) or not all(k in c for k in ('id', 'detail')) for c in criteria):
                    raise InfraError('invalid check criteria')
                if code == 0 and not all(c['pass'] for c in criteria):
                    raise InfraError('HIT contains failed criterion')
                if code == 1 and all(c['pass'] for c in criteria):
                    raise InfraError('MISS has no failed criterion')
                return dict(grade=report['status'], detail=report.get('next_action', 'Compare failed criteria, repair your work, then rerun.'), criteria=criteria, output=raw, exit_code=code)
        except (InfraError, OSError, ValueError, KeyError, IndexError, TypeError) as e:
            if child is not None and child.log.exists():
                raw = child.log.read_text(errors='replace')
                code = child.poll()
            # Temporary run paths are deliberately not retained in canonical state.
            detail = str(e).replace(tmp, '<temporary-run>')
            detail = re.sub(r'<temporary-run>/[^ ;]+', '<temporary-run>', detail)
            return {'grade': 'INFRA', 'detail': detail, 'output': raw, 'exit_code': code}


def reconcile_model_grade(executable, proposal, bullet_count):
    """A model cannot override executable results or supply schedule mutations."""
    if executable['grade'] != 'SELF':
        return executable
    if not isinstance(proposal, dict) or set(proposal) != {'covered', 'contradiction'} or not isinstance(proposal['covered'], list) or len(proposal['covered']) != bullet_count or any(type(v) is not bool for v in proposal['covered']) or type(proposal['contradiction']) is not bool:
        return {'grade': 'INFRA', 'detail': 'Invalid model proposal; use T1 bullet self-report.'}
    covered = proposal['covered']
    grade = 'MISS' if proposal['contradiction'] else ('HIT' if all(covered) else 'PARTIAL' if any(covered) else 'MISS')
    return {'grade': grade, 'detail': 'Model advisory judgment against fixed bullets; not an executable proof.'}


class Driver:
    def __init__(self, course, state, save=lambda state: None):
        self.course, self.s, self.save = course, state, save
        if state.get('schema_version') != 1 or state.get('course_hash') != course.fingerprint:
            raise ValueError('state/course version mismatch; reconcile with course owner')

    def persist(self, event, **fields):
        self.s['history'].append(dict(event=event, **fields))
        self.save(self.s)

    def appendix_view(self):
        appendix = self.s.get('appendix')
        if not appendix:
            return None
        text = self.course.text[appendix['card']]
        if appendix['answer'] is None:
            return text['ending_before'] + '\nOptional checkpoint answer (:quit to stop):'
        return ('Your optional answer: ' + appendix['answer'] + '\n' +
                text['ending_after'] + '\nType continue to save this checkpoint:')

    def appendix_act(self, answer):
        appendix = self.s['appendix']
        answer = answer.strip()
        if not answer or answer in ('/stop', ':quit'):
            return False
        if appendix['answer'] is None:
            appendix['answer'] = answer
            self.persist('appendix_attempt', card=appendix['card'])
            return True
        if answer != 'continue':
            return False
        self.s['appendix'] = None
        self.persist('appendix_finished', card=appendix['card'])
        return True

    def session(self, today, mode='session', minutes=20, fresh=False, expert=False):
        dt.date.fromisoformat(today)
        if mode not in ('session', 'quick', 'exam') or not 1 <= minutes <= 20:
            raise ValueError('mode or minute budget invalid')
        old = self.s['session']
        if old and today < old['today']:
            raise ValueError(f'Saved date is {old["today"]}. Use --today {old["today"]} or later, or --reset to start over.')
        if old and old['today'] == today and not fresh:
            if old['mode'] != mode:
                raise ValueError('use --new-session to change mode')
            return
        if self.s['pending'] and old and old['mode'] != mode:
            raise ValueError('finish pending phase before changing mode')
        # The six-new-concept cap is per calendar day: a same-day --new-session
        # keeps the concepts already introduced today.
        carried = list(old.get('new_concepts', [])) if old and old['today'] == today else []
        self.s['session'] = dict(today=today, mode=mode, budget=minutes, used=0,
                                 new_concepts=carried, last_topic=None, expert=expert)
        self.persist('session', today=today, mode=mode)

    def lesson_done(self, lid):
        lesson = next(l for l in self.course.lessons if l['id'] == lid)
        return all(n in self.s['completed'] for n in self.course.order(lesson))

    def exam_open(self):
        started = self.s['lessons'].get(self.course.lesson_ids[-1], {}).get('first_exposure')
        return bool(started and self.today >= plus(started, 7) and all(self.lesson_done(l) for l in self.course.lesson_ids))

    @property
    def today(self):
        return self.s['session']['today']

    def select(self):
        if self.s['pending']:
            return self.s['pending']['card']
        session = self.s['session']
        if session['used'] >= session['budget']:
            return None
        if session['mode'] == 'exam':
            if not self.exam_open():
                return None
            ids = []
            for o in self.course.objectives:
                for kind in ('production', 'transfer'):
                    for n in o[kind]:
                        passed = self.s['objectives'][o['id']][kind].get(n)
                        tried = self.s['exam']['attempts'].get(n)
                        last = self.s['cards'].get(n, {}).get('last')
                        if (not passed and last is not None and last < self.today
                                and (not tried or tried < self.today)):
                            ids.append(n)
            return self.pick(list(dict.fromkeys(ids)), 'exam')
        due = [n for n, st in self.s['cards'].items() if st['next'] <= self.today and st.get('last') != self.today]
        # High-confidence misses come first so a tight review budget cannot push
        # them out of their +1 day hypercorrection review.
        due.sort(key=lambda n: (not self.s['cards'][n].get('confident_miss', False),
                                self.s['cards'][n]['box'], self.s['cards'][n]['next'], n))
        review_budget = min(5, self.s['session']['budget'] / 3)
        if session['mode'] != 'quick':
            remaining_review = review_budget - session.get('review_used', 0)
            remaining_session = session['budget'] - session['used']
            if (due and not session.get('review_used', 0) and
                    float(self.course.cards[due[0]].get('minutes', 2)) <= remaining_session and
                    float(self.course.cards[due[0]].get('minutes', 2)) > remaining_review):
                eligible = due[:1]
            else:
                eligible = [n for n in due if float(self.course.cards[n].get('minutes', 2)) <= remaining_review]
                if not eligible and not session.get('review_used', 0):
                    eligible = [n for n in due
                                if float(self.course.cards[n].get('minutes', 2)) <= remaining_session][:1]
            due = eligible
        if due:
            return self.pick(due, 'review')
        if session['mode'] == 'quick':
            return None
        for lesson in self.course.lessons:
            if any(not self.lesson_done(lid) for lid in lesson.get('requires', [])):
                continue
            for spec in lesson['concepts']:
                c = self.course.concepts[spec['id']]
                ids = c['pretests'] + [c['worked']] + c['completion'] + c['independent']
                cs = self.s['concepts'].get(c['id'], {})
                if session['expert'] and not cs.get('expert_failed'):
                    ids = c['pretests'] + c['independent'] + [c['worked']] + c['completion']
                remaining = [n for n in ids if n not in self.s['completed']]
                if not remaining:
                    continue
                # Six newly introduced concepts per calendar day, never all unseen pretests.
                if c['id'] not in self.s['concepts'] and len(session['new_concepts']) >= DAILY_NEW_CONCEPTS:
                    return None
                n = remaining[0]
                if n in c['independent']:
                    remaining = interleave([x for x in remaining if x in c['independent']], self.course.cards, session['last_topic'])
                    n = remaining[0]
                return self.begin(n, 'new', lesson['id'], c['id'])
            remaining = [n for n in lesson['integrate'] if n not in self.s['completed']]
            if remaining:
                return self.begin(remaining[0], 'new', lesson['id'], None)
        return None

    def pick(self, ids, context):
        if not ids:
            return None
        if context == 'review':
            # Interleaving must not reorder a high-confidence miss behind other due cards.
            flagged = [n for n in ids if self.s['cards'].get(n, {}).get('confident_miss')]
            ids = flagged or ids
        n = interleave(ids, self.course.cards, self.s['session']['last_topic'])[0]
        cid = self.course.card_concept.get(n)
        lid = self.course.concepts[cid]['lesson'] if cid else next(l['id'] for l in self.course.lessons if n in l['integrate'])
        return self.begin(n, context, lid, cid)

    def baseline(self, rel, original):
        """One pre-edit snapshot per workspace, shared by every card that uses it.

        Several runnable cards edit the same folder (for example L05-R1..R3 in
        labs/l05/work). Capturing each card lazily would copy an earlier card's
        repairs, or edits made ahead, into a later card's review starter. The
        first card to open a workspace fixes its baseline for all of them.
        """
        baselines = self.s.setdefault('baselines', {})
        if rel not in baselines:
            # Progress saved before baselines existed: reuse the starter of the
            # first card that opened this workspace, which predates later edits.
            earlier = None
            for event in self.s.get('history', []):
                m = event.get('card')
                if (event.get('event') == 'question' and event.get('context') == 'new'
                        and m in self.s['starters'] and m in self.course.cards
                        and card_workspace(self.course.cards[m]) == rel):
                    earlier = m
                    break
            baselines[rel] = (copy.deepcopy(self.s['starters'][earlier]) if earlier
                              else capture_starter(original, self.course.fingerprint))
        return copy.deepcopy(baselines[rel])

    def begin(self, n, context, lid, cid):
        cost = float(self.course.cards[n].get('minutes', 2))
        if not 0 < cost <= 7:
            raise ValueError('card estimate must be >0 and <=7 minutes')
        session = self.s['session']
        if session['used'] + cost > session['budget']:
            return None
        session['used'] += cost
        if context == 'review':
            session['review_used'] = session.get('review_used', 0) + cost
        if cid and cid not in self.s['concepts']:
            session['new_concepts'].append(cid)
            self.s['concepts'][cid] = {'introduced': self.today}
        self.s['lessons'].setdefault(lid, {'first_exposure': self.today})
        self.s.update(lesson=lid, concept=cid, phase='answer', card=n)
        self.s['pending'] = dict(card=n, context=context, stage='answer', answer=None,
                                 confidence=None, hint=False, grade=None, flags=[], date=self.today)
        if runnable(self.course.cards[n]):
            q = self.course.cards[n]['Q']
            paths = re.findall(r'labs/l\d\d/(?:validation-completion|composite-work|enum-work|independent|completion|solution|work)', q)
            if not paths and 'independent workspace' in q.lower():
                paths = [f'labs/{lid.lower()}/independent']
            if not paths:
                previous=[v['answer'] for key,v in self.s['work'].items() if key.startswith(lid)
                          and isinstance(v.get('answer'),str) and v['answer'].startswith(f'labs/{lid.lower()}/')]
                paths=previous[-1:]
            self.s['pending']['default_workspace'] = paths[0] if paths else None
            if paths:
                self.s['pending']['original_workspace'] = paths[0]
                original = self.course.root / paths[0]
                if context == 'new' and original.is_dir() and n not in self.s['starters']:
                    self.s['starters'][n] = self.baseline(paths[0], original)
                if context in ('review', 'exam'):
                    fresh = (self.course.root / 'manifest/review-work' /
                             self.s['history_id'] / self.course.fingerprint /
                             f'{n}-{self.today}')
                    restore_starter(self.s['starters'].get(n), fresh, self.course.fingerprint)
                    self.s['pending']['default_workspace'] = str(fresh.relative_to(self.course.root))
        self.persist('question', card=n, context=context)
        return n

    def view(self):
        p = self.s['pending']
        if not p:
            return 'Session paused. ' + self.close_text()
        c = self.course.cards[p['card']]
        authored = self.course.text.get(c['id'], {})
        lesson = next(x for x in self.course.lessons if x['id'] == self.s['lesson'])
        order = self.course.order(lesson)
        title = re.search(r'^# (.+)$', self.course.text[order[0]].get('lead', ''), re.M)
        name = title.group(1) if title else self.s['lesson']
        status = f"[{self.s['lesson']} {name} · card {order.index(c['id'])+1}/{len(order)} · {max(0, self.s['session']['budget']-self.s['session']['used']):g} min left]"
        stage = p['stage']
        if stage == 'answer':
            primer = authored.get('before', c['Vocabulary']).split('\nPredict:', 1)[0]
            q = c['Q'] if c['kind'] == 'CARD' else primer + '\nPredict: ' + c['Predict']
            instructions = authored.get('before', '') if c['kind'] == 'CARD' else ''
            instructions = instructions.replace('press Enter, then Ctrl-D to submit', 'submit it on one line below')
            original = p.get('original_workspace')
            actual = p.get('default_workspace')
            if p['context'] in ('review', 'exam') and original and actual:
                instructions = instructions.replace(original, actual)
                q = q.replace(original, actual)
                instructions = f'Edit {actual} for this attempt.\n' + instructions
            prefix = '\n\n'.join(x for x in (instructions,) if x)
            hint = ' :hint' if c.get('Hint') and p['context'] != 'exam' and c.get('type') != 'pretest' else ''
            if runnable(c):
                default = p.get('default_workspace')
                prompt = (f'Do the lab now. When your edit is ready, press Enter to run the check on {default}, or type another workspace path.'
                          if default else 'Do the lab now. When your edit is ready, type the workspace path to run the check.')
            else:
                prompt = 'Type your answer from memory (:skip to say “don’t know”' + hint + ').'
            return clean_terminal(status + '\n' + (prefix + '\n' if prefix else '') + f"[{c['id']}] {q}\n{prompt}")
        if stage == 'confidence':
            return f"[{c['id']}] Your answer: {p['answer']}\nConfidence before feedback: sure / unsure?"
        if stage == 'production':
            return (f"[{c['id']}] Did you reconstruct the assessed code or schema edits without consulting "
                    "your previous implementation, worked solution, or key? Type fresh or retained. "
                    "Retained work is practice and earns no exam credit.")
        if stage == 'grade':
            return 'Attempt saved; ready to check.'
        if stage == 'infra':
            failed = '; '.join(x['detail'] for x in p['result'].get('criteria', []) if not x['pass'])
            return f"[{c['id']}] SETUP PROBLEM: {failed or p['result']['detail']}\nFix the path or environment, then type /retry, or type a corrected answer."
        if stage == 'lab_miss':
            failed = '\n'.join(x['detail'] for x in p['result'].get('criteria', []) if not x['pass'])
            return f"[{c['id']}] MISS: {failed or p['result']['detail']}\nEdit your work, then type retry; type :hint if available, or giveup to see the key."
        if stage == 'explain':
            return f"[{c['id']}] Check passed. Now type your explanation from memory:"
        if stage == 'explanation_report':
            key='\n'.join(f'{i+1}. {b}' for i,b in enumerate(explanation_bullets(c)))
            return f"[{c['id']}] Your explanation: {p['explanation']}\nKey:\n{key}\nWhich bullets did your explanation cover? Type one y/n per bullet, such as y n y; append x for any contradiction:"
        if c['kind'] == 'CONCEPT':
            worked = authored.get('worked', '\n'.join(c['body']))
            return 'Your prediction: ' + p['answer'] + '\n' + worked + '\nExplain: ' + c['Elaborate']
        key = '\n'.join(f'{i+1}. {b}' for i, b in enumerate(c['Key']))
        if stage == 'selfreport':
            return 'Your answer: ' + p['answer'] + '\nKey:\n' + key + f'\nType one letter per bullet ({len(c["Key"])} bullets here), separated by spaces, e.g. "y n y"; add " x" if you contradicted a bullet:'
        result = p['result']
        detail = result.get('detail', '')
        if p.get('explanation_report'):
            detail += f" Explanation self-report: {p['explanation_report'].count('y')}/{len(p['explanation_report'])} key bullets covered."
        if result['grade'] == 'HIT' and p.get('first_result', {}).get('grade') == 'MISS':
            detail = 'Retry passed. Your first attempt still schedules a review tomorrow.'
        failed = [x['id'] + ': ' + x['detail'] for x in result.get('criteria', []) if not x['pass']]
        if stage == 'correction':
            prompt = ('Restate the correct reasoning and identify the step you were unsure about'
                      if p.get('grade') == 'HIT' else
                      'Restate the correction and explain why your earlier answer failed')
            extra = '\n'.join(x for x in (authored.get('after', ''), authored.get('ending', '')) if x)
            gate = ''
            if c['id'] == 'L03-C1' and p.get('grade') != 'HIT':
                repair = p.get('repair_result')
                failed_repair = '; '.join(x['detail'] for x in repair.get('criteria', []) if not x['pass']) if repair else ''
                gate = ('\nThe prerequisite schema repair must pass before the reader task. '
                        'Repair the workspace, then enter its path to rerun the check. '
                        'The original miss remains recorded for review.'
                        + ('\nLast check: ' + failed_repair if failed_repair else ''))
            return 'Key:\n' + key + ('\n' + extra if extra else '') + gate + '\n' + prompt + ' (required):'
        extra = '\n'.join(x for x in (authored.get('after', ''), authored.get('ending', '')) if x)
        display_grade = p.get('grade') if p.get('grade') in ('MISS', 'PARTIAL') else result['grade']
        return ('Your answer: ' + p['answer'] + '\n' + display_grade + ': ' + (detail if result['grade'] != 'HIT' or p.get('first_result') or p.get('explanation_report') else 'Check passed.') +
                ('\nFailed: ' + '; '.join(failed) if failed else '') + '\nKey:\n' + key +
                ('\n' + extra if extra else '') +
                '\nCompare your answer with the criteria; repair any mismatch. Type continue to save this feedback checkpoint.')

    def act(self, text):
        """One durable transition per call. Blank/EOF never commits an answer."""
        p = self.s['pending']
        if not p:
            raise ValueError('no pending question')
        text = text.strip()
        if not text or text in ('/stop', ':quit'):
            return False
        c = self.course.cards[p['card']]
        stage = p['stage']
        if stage in ('correction', 'elaborate') and text.lower() in SKIPS:
            return False
        if text.lower() in SKIPS and stage != 'answer':
            text = {'confidence': 'unsure', 'selfreport': ' '.join('n' for _ in c['Key']),
                    'lab_miss': 'giveup', 'feedback': 'continue',
                    'production': 'retained',
                    'explain': 'I do not know the explanation yet.',
                    'explanation_report': ' '.join('n' for _ in explanation_bullets(c))}.get(stage, text)
        if stage == 'answer':
            if text in ('/hint', ':hint'):
                if not c.get('Hint') or p['context'] == 'exam' or c.get('type') == 'pretest' or c['kind'] == 'CONCEPT':
                    return False
                p['hint'] = True
                self.persist('hint', card=c['id'])
                return True
            p['answer'] = p.get('default_workspace') if runnable(c) and text == ':enter' else text
            if c.get('type') == 'pretest':
                self.s['pretests_committed'][c['id']] = {'answer': text, 'date': self.today}
            p['stage'] = ('production' if c['AcceptIf'] and p['context'] in ('review', 'exam')
                          and runnable(c) else 'confidence')
        elif stage == 'production':
            if text not in ('fresh', 'retained'):
                return False
            p['reconstructed'] = text == 'fresh'
            if not p['reconstructed']:
                p['hint'] = True
            p['stage'] = 'confidence'
        elif stage == 'confidence':
            confidence={'sure':'sure','unsure':'unsure','y':'sure','yes':'sure',
                        'n':'unsure','no':'unsure'}.get(text.lower())
            if confidence is None:
                return False
            p['confidence'] = confidence
            p['stage'] = 'grade'
        elif stage == 'grade':
            if c['kind'] == 'CONCEPT':
                p['stage'] = 'elaborate'
            elif c.get('type') == 'pretest':
                p['result'] = {'grade': 'ATTEMPT', 'detail': 'Compare your guess with the Key; pretests are not mastery grades.'}
                p['stage'] = 'feedback'
            else:
                p['result'] = check_answer(c, p['answer'], self.course)
                grade = p['result']['grade']
                if runnable(c) and grade == 'MISS':
                    p.setdefault('first_result', copy.deepcopy(p['result']))
                if grade == 'HIT':
                    p['executable_result'] = copy.deepcopy(p['result'])
                p['stage'] = ('infra' if grade == 'INFRA' else 'selfreport' if grade == 'SELF'
                              else 'lab_miss' if runnable(c) and grade == 'MISS'
                              else 'explain' if grade == 'HIT' and asks_explanation(c)
                              else 'selfreport' if grade == 'HIT' else 'feedback')
                if p['stage'] in ('feedback','explain'):
                    p['grade'] = p.get('first_result', {}).get('grade', grade)
        elif stage == 'infra':
            if text == 'continue':
                return False
            if text not in ('/retry', ':retry', 'retry'):
                p['answer'] = text
            p['stage'] = 'grade'
        elif stage == 'lab_miss':
            if text in ('/hint', ':hint') and c.get('Hint'):
                p['hint'] = True
                self.persist('hint', card=c['id'])
                return True
            if text in ('retry', '/retry', ':retry'):
                p['stage'] = 'grade'
            elif text == 'giveup':
                p['grade'] = p['first_result']['grade']
                p['stage'] = 'feedback'
            else:
                return False
        elif stage == 'explain':
            p['explanation'] = text
            p['stage'] = 'explanation_report'
        elif stage == 'explanation_report':
            tokens = text.lower().split()
            if len(tokens) == 1 and re.fullmatch('[yn]+', tokens[0]):
                tokens = list(tokens[0])
            contradiction = tokens[-1:] == ['x']
            ys = tokens[:-1] if contradiction else tokens
            ys = [{'yes': 'y', 'no': 'n'}.get(x, x) for x in ys]
            if len(ys) != len(explanation_bullets(c)) or any(x not in ('y', 'n') for x in ys):
                return False
            p['explanation_report'] = ys
            explanation_grade = ('MISS' if contradiction or not any(x == 'y' for x in ys)
                                 else 'HIT' if all(x == 'y' for x in ys) else 'PARTIAL')
            p['grade'] = p.get('first_result', {}).get('grade', explanation_grade)
            p['stage']='feedback'
        elif stage == 'selfreport':
            tokens = text.lower().split()
            if len(tokens) == 1 and re.fullmatch('[yn]+', tokens[0]):
                tokens = list(tokens[0])
            contradiction = tokens[-1:] == ['x']
            ys = tokens[:-1] if contradiction else tokens
            ys=[{'yes':'y','no':'n'}.get(x,x) for x in ys]
            if len(ys) != len(c['Key']) or any(x not in ('y', 'n') for x in ys):
                return False
            p['result'] = reconcile_model_grade({'grade': 'SELF'}, {'covered': [x == 'y' for x in ys], 'contradiction': contradiction}, len(ys))
            p['result']['detail'] = 'Bullet self-report: ' + text + '; no automated semantic certification.'
            p['result']['criteria'] = [dict(id=f'Key-{i+1}', **{'pass': value == 'y'}, detail=bullet)
                                       for i, (value, bullet) in enumerate(zip(ys, c['Key']))]
            if contradiction:
                p['result']['criteria'].append(dict(id='no-contradiction', **{'pass': False},
                    detail='Your x reports a contradiction; identify and correct it in your restatement.'))
            p['grade'] = p.get('first_result', {}).get('grade', p['result']['grade'])
            p['stage'] = 'feedback'
        elif stage == 'feedback':
            if text != 'continue':
                return False
            if p.get('grade') in ('MISS', 'PARTIAL') or (p.get('grade') == 'HIT' and p['confidence'] == 'unsure'):
                p['stage'] = 'correction'
            else:
                self.finish()
                return True
        elif stage in ('correction', 'elaborate'):
            if text.lower() in SKIPS or text == 'continue':
                return False
            if stage == 'correction' and c['id'] == 'L03-C1' and p.get('grade') != 'HIT':
                if text in ('/edit', ':edit'):
                    p['answer'] = None
                    self.persist('repair_edit', card=c['id'])
                    return True
                if text not in ('/retry', ':retry', 'retry'):
                    p['answer'] = text
                if not p.get('answer'):
                    return False
                p['repair_result'] = check_answer(c, p['answer'], self.course)
                if p['repair_result']['grade'] != 'HIT':
                    self.persist('repair_pending', card=c['id'])
                    return True
            p[stage] = text
            self.finish()
            return True
        else:
            raise ValueError('invalid state phase')
        self.s['phase'] = p['stage']
        self.persist('transition', card=c['id'], phase=p['stage'])
        return True

    def finish(self):
        p = self.s['pending']
        n, context = p['card'], p['context']
        c, today = self.course.cards[n], self.today
        grade = p.get('grade')
        if grade:
            old = self.s['cards'].get(n)
            success = grade == 'HIT' and p['confidence'] == 'sure' and not p['hint']
            box = min(old['box'] + 1, 4) if old and success else 1
            # First independent encounter always returns +1, even on a HIT.
            flag = bool(old and old.get('confident_miss')) or (grade != 'HIT' and p['confidence'] == 'sure')
            delayed = bool(old and old.get('last') is not None and today > old['last'])
            if success and delayed:
                flag = False
            self.s['cards'][n] = dict(box=box, next=plus(today, GAPS[box-1] if success else 1),
                                     last=today, grade=grade, confidence=p['confidence'],
                                     confident_miss=flag, hint=p['hint'])
            if context == 'exam':
                self.s['exam']['attempts'][n] = today
                for o in self.course.objectives:
                    st = self.s['objectives'][o['id']]
                    for kind in ('production', 'transfer'):
                        if n in o[kind] and success and delayed and self.exam_open():
                            st[kind][n] = today
                    st['passed'] = all(all(x in st[k] for x in o[k]) for k in ('production', 'transfer'))
            if context == 'new' and self.s['concept']:
                cid = self.s['concept']
                spec = self.course.concepts[cid]
                if self.s['session']['expert'] and n in spec['independent']:
                    cs = self.s['concepts'][cid]
                    if not success:
                        cs['expert_failed'] = True
                    if success and not cs.get('expert_failed') and all(x == n or (x in self.s['cards'] and self.s['cards'][x]['grade'] == 'HIT' and not self.s['cards'][x]['hint'] and self.s['cards'][x]['confidence'] == 'sure') for x in spec['independent']):
                        for x in [spec['worked']] + spec['completion']:
                            if x not in self.s['completed']:
                                self.s['completed'].append(x)
                        cs['bypass'] = {'date': today, 'evidence': spec['independent']}
        if n not in self.s['completed']:
            self.s['completed'].append(n)
        self.s['session']['last_topic'] = c.get('topic')
        self.s['work'][n] = {'answer': p['answer'], 'correction': p.get('correction'),
                             'elaboration': p.get('elaborate'), 'explanation': p.get('explanation'),
                             'explanation_report': p.get('explanation_report')}
        self.s['checkpoint'] = copy.deepcopy(p)
        if context == 'new' and self.course.text.get(n, {}).get('ending_before'):
            self.s['appendix'] = {'card': n, 'answer': None}
        self.s['pending'] = None
        self.s['phase'] = 'idle'
        self.persist('finished', card=n, grade=grade, context=context, date=today)

    def daily_cap_reached(self):
        session = self.s.get('session') or {}
        if session.get('mode') != 'session' or len(session.get('new_concepts', [])) < DAILY_NEW_CONCEPTS:
            return False
        return any(cid not in self.s['concepts'] for cid in self.course.concepts)

    def close_text(self):
        dates = [v['next'] for v in self.s['cards'].values()]
        waiting = sum(x <= self.today for x in dates)
        pending = self.s.get('pending')
        if pending:
            return f'Your place is saved at {pending["card"]}. Resume with the same command.' + (f' {waiting} reviews are waiting.' if waiting else '')
        session = self.s['session']
        if session['used'] >= session['budget']:
            upcoming = next((n for lesson in self.course.lessons for n in self.course.order(lesson)
                             if n not in self.s['completed']), None)
            next_text = (f' Next card: {upcoming} ({self.course.cards[upcoming].get("minutes", 2)} min).'
                         if upcoming else '')
            return (f'Budget used ({session["used"]:g}/{session["budget"]:g} min).'
                    + next_text + ' Continue with --new-session when ready.'
                    + (f' {waiting} reviews are waiting.' if waiting else ''))
        if waiting:
            return f'{waiting} reviews are waiting. Continue with the same command and --new-session when you have time.'
        if self.daily_cap_reached():
            return (f'You have introduced {DAILY_NEW_CONCEPTS} new concepts today, the daily limit. '
                    'Return tomorrow for new material; spacing the lessons is part of the course.'
                    + (f' Next review: {min(dates)}.' if dates else ''))
        if dates:
            return f'Next: run the same command on or after {min(dates)}.'
        return 'Your place is saved. Resume with the same command when you have time.'


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError(message)

    ap = Parser(description='Offline SBE tutorial. Example: python3 drive.py --today 2026-11-11 --init')
    ap.add_argument('lessons', nargs='?', default='lessons', help='lesson directory (default: lessons)')
    ap.add_argument('--root', default='.', help='course root directory (default: current directory)')
    ap.add_argument('--schedule', default='manifest/schedule.json', help='schedule file relative to root')
    ap.add_argument('--progress', default='manifest/progress.json', help='saved progress file')
    ap.add_argument('--today', required=True, help='study date in YYYY-MM-DD form; use the current local date')
    ap.add_argument('--mode', choices=['session', 'quick', 'exam'], default='session', help='session: due reviews then new work; quick: due reviews only; exam: eligible assessment cards')
    ap.add_argument('--minutes', type=int, default=20, help='estimated sitting budget, 1–20 minutes')
    ap.add_argument('--new-session', action='store_true', help='start a fresh sitting budget; retain any pending attempt')
    ap.add_argument('--expert', action='store_true', help='try independent work before scaffolds; bypass requires confident unassisted success')
    ap.add_argument('--init', action='store_true', help='explicitly initialize a new progress target')
    resets = ap.add_mutually_exclusive_group()
    resets.add_argument('--reset', action='store_true', help='archive progress and start empty')
    resets.add_argument('--reset-lesson', metavar='LESSON', help='archive progress and restart one lesson')
    ap.add_argument('--auto', help='newline-delimited responses; exhaustion is EOF, never a skip')
    ap.add_argument('--tier', choices=['T1', 'T2'], default='T1', help='T2 currently uses the same offline T1 driver; see PROTOCOL.md for model tutoring')
    a = ap.parse_args(argv)
    course = Course(a.root, a.lessons, a.schedule)
    target = Path(a.progress).resolve()
    if not target.exists() and not (a.init or a.reset or a.reset_lesson):
        raise ValueError('progress not initialized; use --init for a new progress file')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Lock the resolved target's stable sidecar, not the atomically replaced inode.
    with target.with_name(target.name + '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('progress already open in another driver')
        if a.reset or a.reset_lesson:
            archive, label = reset_state(course, target, a.today, a.reset_lesson)
            if archive is None:
                print(f'No progress file at {target}; nothing archived or reset.')
            else:
                print(f'Archived {target} to {archive}; reset {label}.')
            return 0
        previous = read_json(target) if target.exists() else None
        changed = previous is not None and previous.get('course_hash') != course.fingerprint
        state = migrate_progress(course, previous, a.today) if previous is not None else initial_state(course)
        driver = Driver(course, state, lambda s: atomic_json(target, s))
        driver.session(a.today, a.mode, a.minutes, a.new_session, a.expert)
        if changed:
            print('Course content changed. Earlier grades are due for fresh review; completed cards and answers were retained.')
        if a.tier == 'T2':
            print(f'{MODEL}: offline driver uses T1. Model conversation follows PROTOCOL.md.')
        print(f'Sitting budget: {state["session"]["budget"]} minutes. Commands: {COMMANDS}')
        print(FLUENCY_WARNING)
        answers = iter(Path(a.auto).read_text().splitlines()) if a.auto else None
        try:
            while True:
                if state.get('appendix'):
                    print(driver.appendix_view(), flush=True)
                    try:
                        answer = next(answers) if answers is not None else input('> ')
                    except (StopIteration, EOFError):
                        break
                    if answer.strip() in ('/stop', ':quit'):
                        break
                    if answer.strip() in (':help', '/help'):
                        print('Commands: ' + COMMANDS); continue
                    if answer.strip() in (':status', '/status'):
                        print(driver.close_text()); continue
                    if answer.lstrip().startswith((':', '/')) and answer.strip() not in (':skip', '/skip'):
                        print('unknown command, type :help'); continue
                    if not driver.appendix_act(answer):
                        print('Input not accepted for this phase; your checkpoint is unchanged.')
                    continue
                if not driver.select():
                    break
                p = state['pending']
                c = course.cards[p['card']]
                if p['stage'] == 'grade':
                    driver.act('check')
                    continue
                if p['stage'] == 'answer' and p['context'] == 'new' and not state['lessons'][state['lesson']].get('opening_shown'):
                    lesson = next(x for x in course.lessons if x['id'] == state['lesson'])
                    opener = course.text[course.order(lesson)[0]].get('lead', '')
                    print(clean_terminal(opener), flush=True)
                    state['lessons'][state['lesson']]['opening_shown'] = True
                    driver.persist('lesson_opening', lesson=state['lesson'])
                print(clean_terminal(driver.view()), flush=True)
                try:
                    answer = next(answers) if answers is not None else input('> ')
                except (StopIteration, EOFError):
                    break
                if answer.strip() in ('/stop', ':quit'):
                    break
                if answer.strip() in (':help', '/help'):
                    print('Commands: ' + COMMANDS)
                    continue
                if answer.strip() in (':status', '/status'):
                    lesson = next(x for x in course.lessons if x['id'] == state['lesson'])
                    order = course.order(lesson)
                    waiting = sum(v['next'] <= driver.today for v in state['cards'].values())
                    print(f'{state["lesson"]}: card {order.index(p["card"])+1} of {len(order)}; {max(0, state["session"]["budget"]-state["session"]["used"]):g} minutes left; {waiting} reviews waiting.')
                    continue
                if not answer.strip():
                    if p['stage'] == 'answer' and runnable(c) and p.get('default_workspace'):
                        answer = ':enter'
                    else:
                        print('Blank line ignored; type :quit to pause.')
                        continue
                if answer.strip() in (':skip', '/skip'):
                    answer = '/skip'
                elif (answer.lstrip().startswith((':', '/')) and
                      answer.strip() not in (':enter', ':hint', '/hint', ':retry', '/retry', '/edit') and
                      not (p['stage'] in ('answer', 'infra', 'correction') and runnable(c) and is_existing_workspace_path(answer.strip()))):
                    print('unknown command, type :help')
                    continue
                if answer.strip() == '/edit':
                    print('Type the corrected workspace path.'); continue
                if answer.strip() in (':hint', '/hint') and p['stage'] in ('answer', 'lab_miss'):
                    if driver.act(answer):
                        print(c['Hint'])
                    else:
                        print('No hint on this card.')
                elif not driver.act(answer):
                    print('Input not accepted here; your place is saved. Type :help for commands.')
        except KeyboardInterrupt:
            print('\nInterrupted; saved phase retained.')
        print(driver.close_text())
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        sys.exit(2)
