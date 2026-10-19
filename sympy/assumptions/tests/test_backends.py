from __future__ import annotations
import os

from sympy.assumptions.ask import Q, ask
from sympy.assumptions.backends import BACKENDS, DEFAULT_BACKEND, active_backends
from sympy.core.relational import Gt
from sympy.core.symbol import Symbol
from sympy.external import import_module
from sympy.testing.pytest import skip

sympy_extras = import_module('sympy_extras')


def test_active_backends():
    backends = active_backends()
    assert set(backends) == {'old', 'new'}
    assert set(backends.values()) <= set(BACKENDS)
    main = os.environ.get('SYMPY_ASSUMPTIONS_BACKEND') or DEFAULT_BACKEND
    for system in ('old', 'new'):
        requested = os.environ.get('SYMPY_ASSUMPTIONS_BACKEND_' + system.upper())
        assert backends[system] in (requested or main, 'sympy')


def test_ask_answers():
    x = Symbol('x')
    assert ask(Q.positive(x), Q.positive(x)) is True
    assert ask(Q.positive(x), Q.negative(x)) is False


def test_sympy_extras_statements():
    if not sympy_extras:
        skip('sympy_extras is not installed')
    from sympy.assumptions.backends.sympy_extras import to_statement
    x = Symbol('x')
    assert to_statement(Q.positive(x)) == Gt(x, 0, evaluate=False)
    assert to_statement(Q.prime(x)) is None
    assert to_statement(Q.positive(x) | Q.prime(x)) is None
    assert to_statement(Q.prime(x), keep=True) == Q.prime(x)
