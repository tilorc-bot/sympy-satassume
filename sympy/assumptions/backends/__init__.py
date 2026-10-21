"""Pluggable backends for SymPy's two assumption systems.

SymPy has two assumption systems:

* the *old* system, the ``expr.is_*`` properties (:mod:`sympy.core.assumptions`);
* the *new* system, :func:`sympy.assumptions.ask.ask` and what is built on it,
  such as :func:`sympy.assumptions.refine.refine`.

A backend answers the queries of one or both systems in place of SymPy's own
code. It is a module that may define

* ``ask(proposition, assumptions)``, the answer to a query of the new system
  (``True``, ``False`` or ``None``), given after ``ask`` has checked and
  sympified its arguments and merged the global assumptions; it may return
  ``NotImplemented`` to leave the query to SymPy's own code;
* ``is_(expr, fact)``, the answer to ``expr.is_<fact>`` for the old system,
  called on a miss of the cache of ``expr``;
* ``setup()``, called once when the backend is installed.

A system whose function the backend does not define stays with SymPy's own
code. The answer of the backend is returned as it is, ``None`` included;
there is no fallback to SymPy's code unless the backend returns
``NotImplemented``. The satassume backend does that for a query that
satassume answers ``None`` and that ``satassume.sympy_api.out_of_scope`` gives
a category (a relation, a matrix or custom predicate, in the proposition or the
assumptions).

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
by SymPy's own code. The facts that this code stores in the caches of objects
meanwhile (``obj._assumptions``) are removed when the backend returns: a later
``is_*`` query is answered by the backend, not from a fact of SymPy's code
that outlived the query, so an answer does not depend on which queries ran
before it (sympy-satassume#10). An answer of the backend to ``expr.is_<fact>``
is stored in the cache of ``expr`` with its implications; one that
contradicts a fact stored there is ``None``, as one of the two is wrong.
Until ``sympy`` has finished importing, SymPy's own code answers every query. The ``is_*`` properties of
:class:`~sympy.assumptions.wrapper.AssumptionsWrapper` always use SymPy's own
code: they ask the new system (so its backend) under the assumptions of the
wrapper.

Examples
========

>>> from sympy.assumptions.backends import active_backends
>>> active_backends()  # doctest: +SKIP
{'old': 'satassume', 'new': 'satassume'}
"""
from __future__ import annotations

import importlib
import os

from sympy.core.assumptions import StdFactKB, as_property, make_property
from sympy.core.basic import Basic
from sympy.core.facts import InconsistentAssumptions

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
# While one runs, 'saved' maps id(kb) to (kb, its facts) for each fact base
# that SymPy's code may write to: they are put back when the backend returns.
_state = {'old': None, 'new': None, 'names': None, 'depth': 0, 'saved': None}


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


def _run(backend_function, *args):
    """``backend_function(*args)``, the queries it makes in turn answered by
    SymPy's code (see ``_wrap_is``).  The facts that this code stores in the
    caches of objects meanwhile are SymPy's answers, not the backend's: they
    are removed when the backend returns, else a later query would read them
    from the cache, and the answer would depend on the queries made before
    (sympy-satassume#10)."""
    saved = {}
    _state['saved'] = saved
    _state['depth'] += 1
    try:
        return backend_function(*args)
    finally:
        _state['depth'] -= 1
        _state['saved'] = None
        for kb, facts in saved.values():
            dict.clear(kb)
            dict.update(kb, facts)


def _wrap_ask(backend_ask):
    def ask(proposition, assumptions):
        if _state['depth']:
            return NotImplemented
        return _run(backend_ask, proposition, assumptions)
    return ask


def _wrap_is(backend_is, sympy_ask, own=()):
    """``_ask`` of :mod:`sympy.core.assumptions` answered by ``backend_is``.
    Instances of the classes in ``own`` keep SymPy's code: their
    ``_eval_is_*`` methods are the answer (``AssumptionsWrapper`` asks the
    new system under its own assumptions, which ``backend_is`` never sees)."""
    def _ask(fact, obj):
        if _state['depth']:
            # SymPy's code writes only to obj's facts (sympy.core.assumptions
            # _ask), and every nested read of a fact not stored comes here.
            saved, kb = _state['saved'], obj._assumptions
            if saved is not None and id(kb) not in saved:
                saved[id(kb)] = (kb, dict(kb))
            return sympy_ask(fact, obj)
        if isinstance(obj, own):
            return sympy_ask(fact, obj)
        answer = _run(backend_is, obj, fact)
        kb = obj._assumptions
        if fact == 'commutative' and answer is False:
            # A fact of how obj is built, not of its value: Mul(0, A,
            # evaluate=False) is non-commutative but evaluates to 0, so
            # SymPy's implications (zero False, complex False, ...) do not
            # hold, and the answer is not stored: stored alone, a later copy
            # of kb would derive them again (InconsistentAssumptions with a
            # stored zero=None).  The backend answers every read.
            return answer
        # Store the answer with its implications, as SymPy's own code does:
        # SymPy's code (answering nested queries) skips the facts it finds
        # stored and so would never deduce from them.
        saved = dict(kb)
        try:
            kb.deduce_all_facts(((fact, answer),))
        except InconsistentAssumptions:
            # The answer contradicts a fact stored on obj (one stored at its
            # construction, or an earlier answer of the backend), so one of
            # the two is wrong: answer None, and keep the stored facts.
            dict.clear(kb)
            dict.update(kb, saved)
            if fact not in kb:
                dict.__setitem__(kb, fact, None)
            return None
        return answer
    return _ask


def _commutative_implications(cls):
    """The facts SymPy derives for the class ``cls`` from an explicit
    ``is_commutative = False`` alone: those of ``cls.default_assumptions``
    that neither ``cls`` (or a base) declares nor the other declared facts
    imply (``Commutator.is_zero = False``)."""
    defs = getattr(cls, '_explicit_class_assumptions', None)
    if not defs or defs.get('commutative') is not False:
        return []
    rest = StdFactKB({k: v for k, v in defs.items() if k != 'commutative'})
    return [k for k in cls.default_assumptions
            if k != 'commutative' and k not in defs and k not in rest]


def _ask_commutative_implications(cls, own=()):
    """Let the backend answer the class-level implications of
    ``is_commutative = False`` (:func:`_commutative_implications`), as
    :func:`_wrap_is` does for an instance's answer: that is a fact of how
    an object is built, not of its value (``Commutator(b - b, a)`` is 0),
    so they are no default facts and no class attributes but properties
    that ask (re-review R3).  ``commutative`` itself stays a class
    attribute, but leaves the default facts too: an instance's facts start
    as their copy, and a copy of a ``StdFactKB`` deduces its facts again.
    """
    if issubclass(cls, own):
        return
    implied = _commutative_implications(cls)
    for fact in implied:
        dict.__delitem__(cls.default_assumptions, fact)
        if isinstance(cls.__dict__.get(as_property(fact)), bool):
            setattr(cls, as_property(fact), make_property(fact))
    if implied:
        dict.__delitem__(cls.default_assumptions, 'commutative')


def _prepare_classes(prepare, own):
    """``_prepare_class_assumptions`` followed by
    :func:`_ask_commutative_implications`, for the classes defined from now
    on; the classes defined so far are done here."""
    def prepare_class(cls):
        prepare(cls)
        _ask_commutative_implications(cls, own)
    seen, todo = set(), [Basic]
    while todo:
        cls = todo.pop()
        if cls not in seen:
            seen.add(cls)
            _ask_commutative_implications(cls, own)
            todo.extend(cls.__subclasses__())
    return prepare_class


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
        wrapper = importlib.import_module('sympy.assumptions.wrapper')
        own = (wrapper.AssumptionsWrapper,)
        core_assumptions._ask = _wrap_is(_state['old'], core_assumptions._ask, own)
        # both callers: Basic.__init_subclass__ and ManagedProperties
        basic = importlib.import_module('sympy.core.basic')
        basic._prepare_class_assumptions = _prepare_classes(
            core_assumptions._prepare_class_assumptions, own)
        core_assumptions._prepare_class_assumptions = basic._prepare_class_assumptions
    if _state['new'] is not None:
        ask_module._backend_ask = _wrap_ask(_state['new'])
    _state['names'] = names
