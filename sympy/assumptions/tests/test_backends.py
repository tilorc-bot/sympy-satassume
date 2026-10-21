from __future__ import annotations
import os

from sympy.assumptions.ask import Q, ask
from sympy.assumptions.wrapper import AssumptionsWrapper
from sympy.assumptions.backends import (BACKENDS, DEFAULT_BACKEND, _state,
                                        _ask_commutative_implications,
                                        _commutative_implications, _wrap_is,
                                        active_backends)
from sympy.core.cache import clear_cache
from sympy.core.expr import Expr
from sympy.core.add import Add
from sympy.core.mul import Mul
from sympy.core.numbers import Integer, pi
from sympy.core.relational import Gt, is_eq
from sympy.core.singleton import S
from sympy.core.symbol import Dummy, Symbol
from sympy.external import import_module
from sympy.functions.elementary.complexes import Abs
from sympy.functions.elementary.exponential import exp, log
from sympy.functions.elementary.miscellaneous import sqrt
from sympy.functions.elementary.trigonometric import sin
from sympy.integrals.integrals import Integral
from sympy.matrices.expressions.matexpr import MatrixSymbol
from sympy.testing.pytest import raises, skip

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
    # One of the two is wrong: the answer is None, the stored facts are
    # kept (sympy-satassume#10).
    answers = {'negative': True, 'positive': None}
    _ask = _wrap_is(lambda obj, fact: answers[fact], None)
    p = Symbol('p')
    # p's own facts: those of Symbol('p') are shared by all plain symbols
    p._assumptions = p._assumptions.copy()
    dict.__setitem__(p._assumptions, 'positive', True)  # stored alone
    before = dict(p._assumptions)
    assert _ask('negative', p) is None
    after = dict(p._assumptions)
    assert after.pop('negative') is None
    assert after == before
    assert _ask('positive', p) is None


def test_facts_of_nested_queries_removed():
    # While a backend runs, the queries it makes are answered by SymPy's
    # code, which stores its answers in the facts of the objects.  They are
    # removed when the backend returns: else a later query would read them,
    # and the answer would depend on the queries made before; also no
    # answer of the backend is stored with implications drawn from them
    # (sympy-satassume#10: 1/log(Abs(e)) positive for an even e).
    def sympy_ask(fact, obj):
        obj._assumptions.deduce_all_facts(((fact, False),))
        return False

    def backend_is(obj, fact):
        assert _ask('zero', obj) is False  # SymPy's code, stored on obj
        assert _ask('zero', b) is False
        assert b._assumptions['zero'] is False
        if fact == 'error':
            raise ValueError
        return True

    _ask = _wrap_is(backend_is, sympy_ask)
    a, b = Expr(), Expr()
    for obj in (a, b):
        obj._assumptions = obj.default_assumptions.copy()
    b_facts = dict(b._assumptions)
    assert _ask('nonnegative', a) is True
    assert a._assumptions['nonnegative'] is True
    assert a._assumptions['negative'] is False
    assert 'zero' not in a._assumptions
    assert 'positive' not in a._assumptions  # nonnegative & ~zero
    assert dict(b._assumptions) == b_facts
    a_facts = dict(a._assumptions)
    raises(ValueError, lambda: _ask('error', a))
    assert dict(a._assumptions) == a_facts
    assert dict(b._assumptions) == b_facts
    assert _state['depth'] == 0 and _state['saved'] is None


def test_satassume_answer_not_from_nested_query():
    # sympy-satassume#10: with SymPy's code answering the queries made
    # while satassume answers these, w.is_positive was True and
    # exp(y).is_zero False (wrong for e = 0 and y = -oo), and the answers
    # depended on which query came first.
    if active_backends()['old'] != 'satassume':
        return
    x, y = Symbol('x'), Symbol('y')
    e = Symbol('e', even=True)
    for query in (lambda f: f.is_zero, lambda f: ask(Q.zero(f))):
        clear_cache()
        w = 1/log(Abs(e))
        query(Integral(sqrt(pi*w/2 + x), (x, 0, 1)))
        assert w.is_nonnegative is True
        assert w.is_positive is None
        clear_cache()
        query(Integral(log(exp(y) + x), (x, 0, 1)))
        assert exp(y).is_zero is None


def test_backend_commutative_false_not_stored():
    # commutative=False is a fact of how the object is built: Mul(0, A,
    # evaluate=False) evaluates to 0, so zero=False must not be stored
    # with it (#180 final review F2), and stored alone a copy of the
    # facts would derive it again: it is not stored.
    answers = {'commutative': False, 'zero': None}
    _ask = _wrap_is(lambda obj, fact: answers[fact], None)
    A = Symbol('A', commutative=False)
    e = Mul(0, A, evaluate=False)
    # as the is_* property does before it calls _ask: e's own copy of the
    # class's default facts (else the stub would write those of every Mul)
    e._assumptions = e.default_assumptions.copy()
    before = dict(e._assumptions)
    assert _ask('commutative', e) is False
    assert dict(e._assumptions) == before
    assert _ask('zero', e) is None
    if active_backends()['old'] == 'satassume':
        e = sin(Mul(0, A, evaluate=False), evaluate=False)
        assert e.is_commutative is False
        assert e.is_zero is None
        assert e.doit() == 0


def test_class_commutative_false_implications_asked():
    # re-review R3: SymPy derives zero=False, complex=False, ... from a
    # class's is_commutative = False and puts them in the class dict, where
    # reading them never calls _ask; an old-system backend answers them.
    class NC(Expr):
        is_commutative = False

    class NCReal(Expr):
        is_commutative = False
        is_complex = False  # declared: it and its implications are kept

    class Sub(NC):
        pass

    for cls in (NC, NCReal, Sub):
        _ask_commutative_implications(cls)
    assert NC.is_commutative is False
    assert isinstance(NC.__dict__['is_zero'], property)
    assert 'zero' not in NC.default_assumptions
    assert 'commutative' not in NC.default_assumptions
    assert _commutative_implications(NC) == []
    assert NCReal.is_complex is False and NCReal.is_zero is False
    assert isinstance(Sub.__dict__['is_integer'], property)
    e = NC()
    # an instance's own copy of the default facts derives none of them
    e._assumptions = e.default_assumptions.copy()
    assert 'zero' not in e._assumptions
    if active_backends()['old'] == 'sympy':
        return
    from sympy.physics.quantum import AntiCommutator, Commutator, Dagger, Operator
    from sympy.physics.quantum.fermion import FermionOp
    # classes defined after the backend was installed
    class Late(Expr):
        is_commutative = False
    for cls in (Commutator, Late):
        assert isinstance(cls.__dict__['is_zero'], property), cls
    a, b = Operator('a'), Operator('b')
    e = Commutator(Add(b, -b, evaluate=False), a)
    assert type(e) is Commutator and e.doit() == 0
    assert e.is_commutative is False
    if active_backends()['old'] == 'satassume':
        assert e.is_zero is None
        d = FermionOp('d')
        e = AntiCommutator(d, Dagger(d))
        assert e.doit() == 1
        assert e.is_integer is None and e.is_complex is None
        assert MatrixSymbol('M', 2, 2).is_zero is False


def test_assumptions_wrapper_uses_sympy_code():
    # AssumptionsWrapper.is_* ask the new system under the wrapper's
    # assumptions, which an old-system backend never sees (#180 S6).
    calls = []
    _ask = _wrap_is(lambda obj, fact: calls.append(fact), lambda fact, obj: 'sympy',
                    (AssumptionsWrapper,))
    d = Dummy('d')
    assert _ask('integer', AssumptionsWrapper(d, Q.even(d))) == 'sympy'
    assert calls == []
    assert _ask('integer', d) is None and calls == ['integer']
    y = Symbol('y')
    assert AssumptionsWrapper(y, Q.even(y)).is_integer is True
    x = Symbol('x')
    assert is_eq(x, S.Zero, assumptions=Q.zero(x)) is True


def test_satassume_out_of_scope_uses_sympy_code():
    # satassume answers None to a query outside its scope; the backend
    # leaves such a query to SymPy's own ask (satassume#180 S3).
    if active_backends()['new'] != 'satassume':
        return
    X = MatrixSymbol('X', 2, 2)
    assert ask(Q.invertible(X), Q.fullrank(X) & Q.square(X)) is True
    assert ask(Q.symmetric(X * X.T)) is True
    from sympy.assumptions.backends.satassume import ask as backend_ask
    x = Symbol('x')
    assert backend_ask(Q.invertible(X), Q.fullrank(X) & Q.square(X)) is NotImplemented
    # An in-scope query keeps satassume's answer, None included.
    assert backend_ask(Q.positive(x), Q.real(x)) is None
    assert backend_ask(Q.positive(x), Q.positive(x)) is True


def test_satassume_out_of_scope_assumptions_only():
    # sympy-satassume#11: with only the assumptions out of scope, SymPy's
    # answer is taken only if it depends on them.  SymPy's own ask decides
    # these without Q.invertible(M), wrongly (each term is nan), where
    # satassume answers None.
    if active_backends()['new'] != 'satassume':
        return
    M = MatrixSymbol('M', 2, 2)
    a = Mul(0, S.Infinity, evaluate=False)
    b = Add(S.Infinity, S.NegativeInfinity, evaluate=False)
    c = exp(a, evaluate=False)
    for p in (Q.zero(a), Q.finite(a), Q.extended_real(b), Q.positive(c)):
        assert ask(p, Q.invertible(M)) is None
    # the in-scope assumptions decide it: satassume's answer
    x = Symbol('x')
    assert ask(Q.positive(x), Q.invertible(M) & Q.positive(x)) is True
    # SymPy's code undecided without the assumptions out of scope: the
    # query goes to SymPy's ask, which may use them
    from sympy.assumptions.backends import satassume as backend
    asked = []

    def sympy_ask(proposition, assumptions, context):
        asked.append(assumptions)
        return None
    old, backend.sympy_ask = backend.sympy_ask, sympy_ask
    try:
        assert backend.ask(Q.zero(a), Q.invertible(M) & Q.real(x)
                           ) is NotImplemented
    finally:
        backend.sympy_ask = old
    assert asked == [Q.real(x)]


def test_sympy_extras_statements():
    if not sympy_extras:
        skip('sympy_extras is not installed')
    from sympy.assumptions.backends.sympy_extras import to_statement
    x = Symbol('x')
    assert to_statement(Q.positive(x)) == Gt(x, 0, evaluate=False)
    assert to_statement(Q.prime(x)) is None
    assert to_statement(Q.positive(x) | Q.prime(x)) is None
    assert to_statement(Q.prime(x), keep=True) == Q.prime(x)


def test_number_handlers_non_number_evalf():
    # PR #8 review: a non-commutative term with number arguments has
    # is_number True, but evalf leaves it no Number (no _prec); with its
    # class-level real = False asked of the backend, the handlers reach
    # evalf: None, not AttributeError (with every backend)
    from sympy.functions.elementary.complexes import Abs
    from sympy.assumptions.refine import refine
    from sympy.physics.quantum import Commutator, Operator
    from sympy.physics.secondquant import F
    if active_backends()['new'] == 'sympy_extras':
        # it answers ask and refine itself, and its time limit fails on
        # this SymPy (sympy-satassume#9)
        skip('the handlers are not reached with sympy_extras')
    x = Symbol('x')
    for e in (Operator(1), F(1), Commutator(Operator(1), Operator(2)), Operator(S.Pi)**2):
        for p in (Q.zero, Q.nonzero, Q.positive, Q.negative, Q.real, Q.imaginary):
            assert ask(p(e)) in (None, False), (e, p)
        refine(Abs(e))
        AssumptionsWrapper(e, Q.positive(x)).is_zero
