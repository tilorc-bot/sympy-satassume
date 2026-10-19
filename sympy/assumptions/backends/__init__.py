"""Pluggable backends for SymPy's two assumption systems.

SymPy has two assumption systems:

* the *old* system, the ``expr.is_*`` properties (:mod:`sympy.core.assumptions`);
* the *new* system, :func:`sympy.assumptions.ask.ask` and what is built on it,
  such as :func:`sympy.assumptions.refine.refine`.

A backend answers the queries of one or both systems in place of SymPy's own
code. It is a module that may define

* ``ask(proposition, assumptions)``, the answer to a query of the new system
  (``True``, ``False`` or ``None``), given after ``ask`` has checked and
  sympified its arguments and merged the global assumptions;
* ``is_(expr, fact)``, the answer to ``expr.is_<fact>`` for the old system,
  called on a miss of the cache of ``expr``;
* ``setup()``, called once when the backend is installed.

A system whose function the backend does not define stays with SymPy's own
code. The answer of the backend is returned as it is, ``None`` included;
there is no fallback to SymPy's code.

The backend is chosen when ``sympy`` is imported, from the environment
variable ``SYMPY_ASSUMPTIONS_BACKEND``:

* ``satassume`` (the default): both systems are answered by satassume;
* ``sympy``: SymPy's own code, unchanged;
* ``sympy_extras``: the new system is answered by
  :func:`sympy_extras.assumptions.ask` (the old system stays SymPy's).

``SYMPY_ASSUMPTIONS_BACKEND_OLD`` and ``SYMPY_ASSUMPTIONS_BACKEND_NEW``
choose the backend of one system only.

While a backend runs, any query it makes in turn (for instance a backend
reading ``x.is_positive`` of a symbol, or calling ``sympy.ask``) is answered
by SymPy's own code. Until ``sympy`` has finished importing, SymPy's own code
answers every query.

Examples
========

>>> from sympy.assumptions.backends import active_backends
>>> active_backends()  # doctest: +SKIP
{'old': 'satassume', 'new': 'satassume'}
"""
from __future__ import annotations

import importlib
import os

__all__ = ['BACKENDS', 'DEFAULT_BACKEND', 'active_backends', 'xfail_key']

#: The names of the backends and the modules that implement them.
BACKENDS = {
    'sympy': None,
    'satassume': 'sympy.assumptions.backends.satassume',
    'sympy_extras': 'sympy.assumptions.backends.sympy_extras',
}

DEFAULT_BACKEND = 'satassume'

_ENV = 'SYMPY_ASSUMPTIONS_BACKEND'

# The backend function of each system once installed, and the depth of the
# backend calls running: a query made while a backend runs uses SymPy's code.
_state = {'old': None, 'new': None, 'names': None, 'depth': 0}


def _requested(system=None):
    var = _ENV if system is None else '%s_%s' % (_ENV, system.upper())
    name = os.environ.get(var, '')
    if name and name not in BACKENDS:
        raise ValueError('%s=%r: the backends are %s'
                         % (var, name, ', '.join(sorted(BACKENDS))))
    return name


def active_backends():
    """The names of the backends answering the old (``expr.is_*``) and the
    new (``ask``) assumption systems.

    Examples
    ========

    >>> from sympy.assumptions.backends import active_backends
    >>> sorted(active_backends())
    ['new', 'old']
    """
    if _state['names'] is None:
        return {'old': 'sympy', 'new': 'sympy'}
    return dict(_state['names'])


def xfail_key():
    """The name of the list of expected test failures of the active
    backends (see ``sympy/testing/assumption_backend_xfails``): the backend
    name when it was chosen with ``SYMPY_ASSUMPTIONS_BACKEND`` alone, else
    ``old-<name>.new-<name>``."""
    names = active_backends()
    if _requested('old') or _requested('new'):
        return 'old-%s.new-%s' % (names['old'], names['new'])
    return _requested() or DEFAULT_BACKEND


def _wrap_ask(backend_ask):
    def ask(proposition, assumptions):
        if _state['depth']:
            return NotImplemented
        _state['depth'] += 1
        try:
            return backend_ask(proposition, assumptions)
        finally:
            _state['depth'] -= 1
    return ask


def _wrap_is(backend_is, sympy_ask):
    def _ask(fact, obj):
        if _state['depth']:
            return sympy_ask(fact, obj)
        _state['depth'] += 1
        try:
            answer = backend_is(obj, fact)
        finally:
            _state['depth'] -= 1
        dict.__setitem__(obj._assumptions, fact, answer)
        return answer
    return _ask


def _load(name):
    try:
        module = importlib.import_module(BACKENDS[name])
    except ImportError as exc:
        raise ImportError('the %r assumptions backend needs a package that is '
                          'not installed (%s); set %s=sympy to use the '
                          'assumptions of SymPy' % (name, exc, _ENV)) from exc
    setup = getattr(module, 'setup', None)
    if setup is not None:
        setup()
    return module


def _install():
    """Install the chosen backends; called at the end of ``import sympy``."""
    ask_module = importlib.import_module('sympy.assumptions.ask')
    core_assumptions = importlib.import_module('sympy.core.assumptions')
    main = _requested() or DEFAULT_BACKEND
    names, modules = {}, {}
    for system, function in (('old', 'is_'), ('new', 'ask')):
        name = _requested(system) or main
        names[system] = name
        if BACKENDS[name] is None:
            continue
        if name not in modules:
            modules[name] = _load(name)
        _state[system] = getattr(modules[name], function, None)
        if _state[system] is None:
            if _requested(system):
                raise ValueError('the %r assumptions backend does not answer '
                                 'the %s assumption system' % (name, system))
            names[system] = 'sympy'
    if _state['old'] is not None:
        core_assumptions._ask = _wrap_is(_state['old'], core_assumptions._ask)
    if _state['new'] is not None:
        ask_module._backend_ask = _wrap_ask(_state['new'])
    _state['names'] = names
