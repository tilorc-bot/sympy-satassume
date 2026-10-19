#!/usr/bin/env python
"""Summaries of test runs and the lists of expected failures of the
assumptions backends.

    xfails.py summary RUNDIR [BASEDIR]
        counts of the outcomes in RUNDIR (written by run_chunks.sh); with
        BASEDIR (a run of the ``sympy`` backend), the failures that are new.

    xfails.py make BACKEND RUNDIR BASEDIR [PREVIOUS] > FILE
        the list of expected failures of BACKEND: the tests failing in
        RUNDIR (a run with --no-backend-xfails) and not in BASEDIR. Tags of
        tests already listed in PREVIOUS (an earlier list) are kept, the
        others are derived from the failure message.

See sympy/testing/assumption_backend_xfails/README.md.
"""
from __future__ import annotations
import collections
import datetime
import glob
import os
import re
import sys

FAILED = ('failed', 'timeout')
RANK = ['passed', 'skipped', 'xpassed', 'xfailed', 'failed', 'timeout']

TAGS = """\
# Tags (the cause of the failure):
#   none        the backend answers None where SymPy answers True/False
#   wrong       the backend gives the opposite True/False answer
#   extra       the backend decides a fact SymPy leaves None, changing results
#   agree       every recorded answer agrees with SymPy (likely an answer
#               cached by an earlier test in the same process: order dependent)
#   unrecorded  no backend call recorded for the test itself (cached answers)
#   engine-exc  an exception inside the backend
#   timeout     the test exceeds the 60 s per-test limit (not run)
#   recursion   RecursionError (not run: slow, and it has crashed xdist workers)
#   assert      an assertion fails (cause not analysed further)
#   exc-<name>  the exception <name> is raised (cause not analysed further)
"""


def load(rundir):
    tests, modules, messages = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(rundir, 'outcomes', '*.tsv'))):
        with open(path, encoding='utf-8') as stream:
            for line in stream:
                nodeid, when, outcome, message = line.rstrip('\n').split('\t', 3)
                if when == 'collect':
                    modules[nodeid] = outcome
                    messages[nodeid] = message
                elif RANK.index(outcome) >= RANK.index(tests.get(nodeid, 'passed')):
                    tests[nodeid] = outcome
                    messages[nodeid] = message
    return tests, modules, messages


def tag_of(outcome, message):
    if outcome == 'timeout':
        return 'timeout'
    if 'RecursionError' in message or 'maximum recursion depth' in message:
        return 'recursion'
    match = re.match(r'([A-Za-z_][\w.]*(?:Error|Exception|Failed|Exit))\b', message)
    if match and not match.group(1).endswith('AssertionError'):
        return 'exc-' + match.group(1).rsplit('.', 1)[-1]
    if re.match(r'(AssertionError: )?assert None (is|==)', message):
        return 'none'
    return 'assert'


def read_list(path):
    tags = {}
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as stream:
            for line in stream:
                line = line.strip()
                if line and not line.startswith('#'):
                    tag, nodeid = line.split(None, 1)
                    tags[nodeid] = tag
    return tags


def new_failures(rundir, basedir):
    tests, modules, messages = load(rundir)
    base_tests, base_modules, _ = load(basedir)
    new = {k: v for k, v in tests.items()
           if v in FAILED and base_tests.get(k) not in FAILED}
    new_modules = {k: v for k, v in modules.items()
                   if v == 'collect-failed' and base_modules.get(k) != 'collect-failed'}
    return new, new_modules, messages


def summary(rundir, basedir=None):
    tests, modules, messages = load(rundir)
    print('tests', len(tests), dict(collections.Counter(tests.values()).most_common()))
    print('collection', dict(collections.Counter(modules.values()).most_common()))
    backend = [k for k, v in tests.items() if v in ('xfailed', 'xpassed')
               and 'assumptions backend' in messages[k]]
    counts = collections.Counter(tests[k] for k in backend)
    not_run = sum('[NOTRUN]' in messages[k] for k in backend)
    print('backend xfails: xfailed %d (of them not run %d), xpassed %d' % (
        counts['xfailed'], not_run, counts['xpassed']))
    unexpected = sorted(k for k, v in tests.items() if v in FAILED)
    unexpected += sorted(k for k, v in modules.items() if v == 'collect-failed')
    print('unexpected failures', len(unexpected))
    for k in unexpected[:50]:
        print('  ', tests.get(k, modules.get(k)), k, messages[k][:120])
    if basedir:
        new, new_modules, _ = new_failures(rundir, basedir)
        print('new vs base: tests', len(new), dict(collections.Counter(new.values())),
              'modules', len(new_modules))
        by_module = collections.Counter('/'.join(k.split('/')[:2]) for k in new)
        print('new by module', dict(by_module.most_common()))


def make(backend, rundir, basedir, previous=None):
    new, new_modules, messages = new_failures(rundir, basedir)
    old_tags = read_list(previous)
    entries = []
    for nodeid in list(new_modules) + list(new):
        outcome = new.get(nodeid, 'failed')
        tag = old_tags.get(nodeid) or tag_of(outcome, messages[nodeid])
        if outcome == 'timeout':
            tag = 'timeout'
        entries.append((nodeid, tag))
    counts = collections.Counter(tag for _, tag in entries)
    print('# Expected failures of the test suite with SYMPY_ASSUMPTIONS_BACKEND=%s.' % backend)
    print('# Generated by bin/assumption_backends/xfails.py on %s from the run in' % datetime.date.today())
    print('# %s against the sympy backend run in %s.' % (rundir, basedir))
    print('# %d test ids and %d test modules that fail at collection (an entry without'
          % (len(new), len(new_modules)))
    print('# "::" is a module: its collection error is reported as a skip).')
    print('# Tag counts: %s' % ', '.join('%s %d' % kv for kv in counts.most_common()))
    print('#')
    print(TAGS, end='')
    print('#')
    print('# Format: TAG NODEID')
    width = max([len(tag) for _, tag in entries] + [1])
    for nodeid, tag in sorted(entries):
        print('%-*s %s' % (width, tag, nodeid))


if __name__ == '__main__':
    command, args = sys.argv[1], sys.argv[2:]
    {'summary': summary, 'make': make}[command](*args)
