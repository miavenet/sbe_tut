#!/usr/bin/env python3
"""Recalculate published card-time estimates after lesson edits."""
import argparse
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drive import Course

argparse.ArgumentParser(description=__doc__).parse_args()


def replace_one(path, pattern, replacement):
    text = path.read_text()
    changed, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise ValueError(f'estimate text missing in {path.relative_to(ROOT)}')
    path.write_text(changed)


course = Course(ROOT)
cards = sum(float(c.get('minutes', 2)) for c in course.cards.values())
exam_ids = {n for o in course.objectives for kind in ('production', 'transfer') for n in o[kind]}
exam = sum(float(course.cards[n].get('minutes', 2)) for n in exam_ids)
review_cards = [c for c in course.cards.values() if c['kind'] == 'CARD' and c.get('type') != 'pretest']
reviews = sum(float(c.get('minutes', 2)) for c in review_cards)
if any(x != int(x) for x in (cards, exam, reviews)):
    raise ValueError('published minute totals require whole-minute card estimates')
cards, exam, reviews = map(int, (cards, exam, reviews))
first = cards + int(course.config.get('estimated_primer_minutes', 0))
setup = int(course.config['estimated_setup_minutes'])
core = setup + first + exam
readme = ROOT / 'README.md'
listed = core + reviews
lesson_minutes = {}
for lesson in course.lessons:
    cost = sum(float(course.cards[n].get('minutes', 2)) for n in course.order(lesson))
    if lesson['id'] == 'L01':
        cost += float(course.config.get('estimated_primer_minutes', 0))
    if cost != int(cost):
        raise ValueError('published lesson minutes require whole-minute estimates')
    lesson_minutes[lesson['id']] = int(cost)
if len(lesson_minutes) != 5:
    raise ValueError('course.md lists five lesson estimates')
hours = round(listed / 60)
replace_one(readme, r'takes an estimated \d+ hours', f'takes an estimated {hours} hours')
manifest = ROOT / 'manifest/course.md'
per_lesson = list(lesson_minutes.values())
lesson_list = ', '.join(map(str, per_lesson[:-1])) + f' and {per_lesson[-1]}'
replace_one(manifest,
            r'Time cost: an estimated \d+ hours of listed work \(\d+ estimated minutes: setup \d+,(\s+)'
            r'first-pass lessons \d+, one encounter with all \d+ graded reviews \d+, and(\s+)'
            r'the delayed exam \d+\)\. First-pass lessons take about \d+, \d+, \d+, \d+ and \d+(\s+)minutes\.',
            lambda m: (f'Time cost: an estimated {hours} hours of listed work ({listed} estimated minutes: setup {setup},{m[1]}'
                       f'first-pass lessons {first}, one encounter with all {len(review_cards)} graded reviews {reviews}, and{m[2]}'
                       f'the delayed exam {exam}). First-pass lessons take about {lesson_list}{m[3]}minutes.'))
schedule = ROOT / 'manifest/schedule.json'
replace_one(schedule, r'"estimated_core_minutes": \d+', f'"estimated_core_minutes": {core}')
replace_one(schedule, r'"estimated_review_sweep_minutes": \d+', f'"estimated_review_sweep_minutes": {reviews}')
replace_one(ROOT / 'labs/l02/deeper-pack.md', r'\d+-minute core', f"{lesson_minutes['L02']}-minute core")
replace_one(ROOT / 'labs/l03/README.md', r'Budget: \d+ minutes estimated',
            f"Budget: {lesson_minutes['L03']} minutes estimated")
replace_one(ROOT / 'labs/l05/README.md', r'about \d+ minutes in four',
            f"about {lesson_minutes['L05']} minutes in four")
print(f'Refreshed estimates: first pass {first}, exam {exam}, review sweep {reviews}, setup {setup} minutes.')
