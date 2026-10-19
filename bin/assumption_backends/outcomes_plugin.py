"""pytest plugin: append one line per test phase report to $OUTCOMES_FILE.

Lines are ``nodeid<TAB>when<TAB>outcome<TAB>message``, written by the xdist
controller (or by the only process without xdist). ``outcome`` is passed,
failed, skipped, xfailed, xpassed, timeout or (for a collection report)
collect-failed / collect-skipped. Use with
``PYTHONPATH=bin/assumption_backends pytest -p outcomes_plugin``.
"""
import os

_path = os.environ.get('OUTCOMES_FILE')
_config = None


def pytest_configure(config):
    global _config
    _config = config


def _write(nodeid, when, outcome, message):
    if not _path or hasattr(_config, 'workerinput'):
        return
    message = ' '.join(message.split())[:300]
    with open(_path, 'a', encoding='utf-8') as stream:
        stream.write('%s\t%s\t%s\t%s\n' % (nodeid, when, outcome, message))


def _message(report):
    crash = getattr(report.longrepr, 'reprcrash', None)
    if crash is not None:
        return crash.message
    if isinstance(report.longrepr, tuple):
        return str(report.longrepr[-1])
    return str(report.longrepr or '')


def pytest_runtest_logreport(report):
    if report.when != 'call' and report.passed:
        return
    message = _message(report) if not report.passed else ''
    if hasattr(report, 'wasxfail'):
        outcome = 'xpassed' if report.passed else 'xfailed'
        message = report.wasxfail
    elif report.failed and 'Timeout' in message:
        outcome = 'timeout'
    else:
        outcome = report.outcome
    _write(report.nodeid, report.when, outcome, message)


def pytest_collectreport(report):
    if report.failed or (report.skipped and report.nodeid.endswith('.py')):
        _write(report.nodeid, 'collect', 'collect-' + report.outcome, _message(report))
