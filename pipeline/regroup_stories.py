#!/usr/bin/env python3
"""
Re-run the story grouping (assign_stories in collect_day.py) on daily history files
that are already saved, without downloading GDELT again or calling the model.

Only story_id changes in the .jsonl; in the .summary.json only the fields computed
from stories are rewritten (summarize()), and story_grouping_version records the
grouping used. Classification fields and their versions are left as they are.

Usage:
  python pipeline/regroup_stories.py data/gkg/2026/11/*.jsonl
  python pipeline/regroup_stories.py data/gkg/2026/11/2026-11-20.jsonl --dry-run
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_day import PIPELINE_VERSION, assign_stories, summarize  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--dry-run', action='store_true', help='print the change, write nothing')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    for path in sorted(args.files):
        day = os.path.basename(path)[:10]
        with open(path, encoding='utf-8') as f:
            lines = [json.loads(line) for line in f if line.strip()]
        before = len({r['story_id'] for r in lines})
        before_rel = len({r['story_id'] for r in lines if r['relevant'] == 'yes'})
        assign_stories(lines, day)
        after = len({r['story_id'] for r in lines})
        after_rel = len({r['story_id'] for r in lines if r['relevant'] == 'yes'})
        print(f'{day}: {len(lines)} records, stories {before} -> {after}, relevant stories {before_rel} -> {after_rel}')
        if args.dry_run:
            continue
        with open(path, 'w', encoding='utf-8') as f:
            for r in lines:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        spath = path.replace('.jsonl', '.summary.json')
        if os.path.exists(spath):
            with open(spath, encoding='utf-8') as f:
                summary = json.load(f)
            summary.update(summarize(lines, day))
            summary['story_grouping_version'] = PIPELINE_VERSION
            with open(spath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
