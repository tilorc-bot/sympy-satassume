from __future__ import annotations
import os

from sympy.assumptions.ask import Q, ask
from sympy.assumptions.backends import (BACKENDS, DEFAULT_BACKEND, _state,
                                        _wrap_is, active_backends)
from sympy.core.cache import clear_cache
from sympy.core.numbers import Integer
from sympy.core.relational import Gt
from sympy.core.singleton import S
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


def test_backend_answers_stored_with_deductions():
    # A backend answer is stored with its implications: SymPy's code, which
    # answers the queries made while a backend runs, skips stored facts and
    # so cannot deduce from them.  Before, the nested query below cached
    # even=None and (-1)**n recursed forever.  The first object makes the
    # backend cache its answers, so for the second one it reads none of
    # SymPy's facts (which would store even=True).
    for _ in range(2):
        clear_cache()
        n = Integer(123456789012)
        assert n.is_odd is False
        assert n.is_zero is False
    _state['depth'] += 1
    try:
        assert n.is_even is True
    finally:
        _state['depth'] -= 1
    assert S.NegativeOne**n == 1


def test_backend_answer_inconsistent_with_stored_facts():
    # Such an answer is stored without its implications, and a None answer
    # keeps the stored value.
    answers = {'negative': True, 'positive': None}
    _ask = _wrap_is(lambda obj, fact: answers[fact], None)
    p = Symbol('p')
    dict.__setitem__(p._assumptions, 'positive', True)  # stored alone
    before = dict(p._assumptions)
    assert _ask('negative', p) is True
    assert _ask('positive', p) is None
    after = dict(p._assumptions)
    assert after.pop('negative') is True
    assert after == before


def test_sympy_extras_statements():
    if not sympy_extras:
        skip('sympy_extras is not installed')
    from sympy.assumptions.backends.sympy_extras import to_statement
    x = Symbol('x')
    assert to_statement(Q.positive(x)) == Gt(x, 0, evaluate=False)
    assert to_statement(Q.prime(x)) is None
    assert to_statement(Q.positive(x) | Q.prime(x)) is None
    assert to_statement(Q.prime(x), keep=True) == Q.prime(x)
