#!/usr/bin/env python3
"""Run unittest and publish failures as readable GitHub check annotations.

No credentials or test fixtures are uploaded. This keeps detailed results
accessible through the GitHub API even where the Actions log CDN is unavailable.
"""
from pathlib import Path
import argparse
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def escape(value):
    return value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-p', '--pattern', default='test*.py')
    parser.add_argument('-v', action='count', default=1)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=min(2, args.v + 1)).run(suite)
    if os.environ.get('GITHUB_ACTIONS'):
        for test, message in (result.errors + result.failures)[:10]:
            print(f'::error title={escape(str(test))}::{escape(message[-16000:])}', flush=True)
        print(f'::notice title=Unittest result::{result.testsRun} tests; '
              f'{len(result.failures)} failures; {len(result.errors)} errors; '
              f'{len(result.skipped)} skipped. HOI4 is not executed.', flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
