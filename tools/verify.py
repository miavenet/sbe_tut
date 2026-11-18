#!/usr/bin/env python3
"""Local structural checks for the public tutorial."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import unquote

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drive import Course

JAR_SHA256 = 'f60becdb567519a2ed3824ffe285f93adb2159b39ede0b234fc8b1f13736236a'
CHECK_RE = re.compile(r'^check\(([^)]+)\)$')
LOCAL_LINK = re.compile(r'(?<!!)\[[^]]+\]\(([^)]+)\)')


def release_files(root):
    files = set()
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        parts = set(rel.parts)
        if (parts & {'third_party', 'evidence', 'review-starters', 'review-work', '__pycache__', '.git'}
                or rel.as_posix() in {'manifest/progress.json', 'manifest/progress.json.lock'}
                or path.suffix in {'.jar', '.pyc', '.bak', '.jsonl'}
                or (path.name.startswith('progress') and path.suffix in {'.json', '.md'})
                or '.bak.' in path.name
                or path.name.startswith('.download.')):
            continue
        files.add(rel.as_posix())
    return files


def validate_card(card, root):
    if card['kind'] != 'CARD':
        return
    if not card['Q'].strip() or not card['Key'] or not card['Source'].strip():
        raise ValueError('missing question, key, or source on ' + card['id'])
    for name in CHECK_RE.findall(card.get('AcceptIf', '')):
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError('missing executable check: ' + name)


def verify_time_estimates(course):
    first = sum(float(c.get('minutes', 2)) for c in course.cards.values())
    exam = {n for obj in course.objectives for kind in ('production', 'transfer') for n in obj[kind]}
    exam_minutes = sum(float(course.cards[n].get('minutes', 2)) for n in exam)
    reviews = [c for c in course.cards.values() if c['kind'] == 'CARD' and c.get('type') != 'pretest']
    review_minutes = sum(float(c.get('minutes', 2)) for c in reviews)
    if (first + exam_minutes + course.config['estimated_setup_minutes'] +
            course.config.get('estimated_primer_minutes', 0) != course.config['estimated_core_minutes']):
        raise ValueError('core time estimate does not match card costs')
    if review_minutes != course.config['estimated_review_sweep_minutes']:
        raise ValueError('review time estimate does not match card costs')


def verify_local_links(root):
    for name in release_files(root):
        if not name.endswith('.md'):
            continue
        path = root / name
        for raw in LOCAL_LINK.findall(path.read_text()):
            target = raw.split('#', 1)[0]
            if not target or re.match(r'^[a-z]+://|^mailto:', target):
                continue
            linked = (path.parent / unquote(target)).resolve()
            if not linked.exists():
                raise ValueError(f'broken Markdown link in {name}: {raw}')


def verify_card_sources(course):
    for card in course.cards.values():
        lesson = course.root / 'lessons' / (card['lesson'] + '.md')
        for raw in LOCAL_LINK.findall(card['Source']):
            target = raw.split('#', 1)[0]
            if not target or re.match(r'^[a-z]+://|^mailto:', target):
                continue
            if not (lesson.parent / unquote(target)).resolve().exists():
                raise ValueError(f'broken card source in {card["id"]}: {raw}')


def verify_lesson_metadata(root):
    for path in (root / 'lessons').glob('*.md'):
        body = path.read_text()
        if (re.search(r'(?im)^[ \t]*(?:[-*][ \t]+)?(?:Source(?: URL)?|Story source(?: URL)?|AcceptIf|RejectIf|Concepts|Stretch|StretchKey|Verification(?: notes?)?|Verified(?: with)?):|\[(?:type|topic|box|objective|minutes|assessment):', body)
                or re.search(r'(?m)^### (?:CARD|CONCEPT) ', body)):
            raise ValueError('lesson metadata remains: ' + path.name)
        before_reading = re.split(r'(?im)^##? Further reading\s*$', body, maxsplit=1)[0]
        if re.search(r'https?://', before_reading):
            raise ValueError('lesson source URL remains: ' + path.name)


def verify(root):
    root = Path(root).resolve()
    if (root / 'claims.tsv').exists() or (root / 'lesson-rewrite-claims.md').exists():
        raise ValueError('claims belong only under manifest/')
    verify_local_links(root)
    course = Course(root)
    verify_card_sources(course)
    verify_lesson_metadata(root)
    verify_time_estimates(course)
    for card in course.cards.values():
        validate_card(card, root)
    jar = root / 'labs/lib/sbe-all-1.42.0.jar'
    if jar.exists() and hashlib.sha256(jar.read_bytes()).hexdigest() != JAR_SHA256:
        raise ValueError('SBE jar hash mismatch')
    for name in ('README.md', 'PROTOCOL.md', 'manifest/course.md', 'manifest/claims.tsv'):
        if not (root / name).is_file():
            raise ValueError('missing public course file: ' + name)
    for link in root.rglob('*'):
        if link.is_symlink() and not link.exists():
            raise ValueError('broken symlink: ' + str(link.relative_to(root)))
    return {'status':'PASS', 'cards':len(course.cards), 'lessons':len(course.lessons),
            'jar':'verified' if jar.exists() else 'setup-required'}


def main():
    try:
        print(json.dumps(verify(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT),sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
