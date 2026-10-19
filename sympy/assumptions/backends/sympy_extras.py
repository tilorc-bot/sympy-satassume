"""The sympy-extras backend: ``ask`` is answered by
:func:`sympy_extras.assumptions.ask`.

sympy-extras (https://github.com/Upabjojr/sympy-extras) states assumptions
as relations and set memberships, in the manner of Mathematica: ``x > 0``
rather than ``Q.positive(x)``, ``element(x, S.Integers)`` rather than
``Q.integer(x)``. The proposition is translated to such statements and the
answer of sympy-extras is returned as it is. A proposition containing a
predicate that has no such statement (``Q.finite``, ``Q.prime``, the matrix
predicates, ...) gets the answer ``None``. Predicates of the assumptions
without such a statement are passed on unchanged: sympy-extras accepts them
and gives them to ``sympy.ask``, which then runs SymPy's own code.

Only the new assumption system is answered by this backend. Answering
``expr.is_*`` with it is not practical: most facts of the old system
(``commutative``, ``finite``, ``extended_real``, ...) have no statement, and
the others cost a call of sympy-extras per cache miss. See the README of
this repository for the measurements.
"""
from __future__ import annotations

from sympy.assumptions.ask import Q
from sympy.assumptions.assume import AppliedPredicate
from sympy.core.numbers import Integer
from sympy.core.relational import Eq, Ge, Gt, Le, Lt, Ne
from sympy.core.singleton import S
from sympy.logic.boolalg import And, Equivalent, ITE, Implies, Not, Or, Xor
from sympy.sets.contains import Contains

from sympy_extras.assumptions import ask as _extras_ask

_zero = Integer(0)


def _element(e, domain):
    return Contains(e, domain, evaluate=False)


_UNARY = {
    Q.positive: lambda e: Gt(e, _zero, evaluate=False),
    Q.negative: lambda e: Lt(e, _zero, evaluate=False),
    Q.nonnegative: lambda e: Ge(e, _zero, evaluate=False),
    Q.nonpositive: lambda e: Le(e, _zero, evaluate=False),
    Q.zero: lambda e: Eq(e, _zero, evaluate=False),
    Q.nonzero: lambda e: Or(Gt(e, _zero, evaluate=False),
                            Lt(e, _zero, evaluate=False)),
    Q.real: lambda e: _element(e, S.Reals),
    Q.complex: lambda e: _element(e, S.Complexes),
    Q.rational: lambda e: _element(e, S.Rationals),
    Q.irrational: lambda e: And(_element(e, S.Reals),
                                Not(_element(e, S.Rationals))),
    Q.integer: lambda e: _element(e, S.Integers),
    Q.even: lambda e: _element(e/2, S.Integers),
    Q.odd: lambda e: And(_element(e, S.Integers),
                         Not(_element(e/2, S.Integers))),
}

_COMPOUND = (And, Or, Not, Implies, Equivalent, Xor, ITE)

_BINARY = {Q.eq: Eq, Q.ne: Ne, Q.gt: Gt, Q.ge: Ge, Q.lt: Lt, Q.le: Le}


def to_statement(formula, keep=False):
    """The statement of sympy-extras equivalent to a Boolean combination of
    predicates, or ``None`` if a predicate has none. With ``keep=True`` such
    a predicate is kept as it is instead.

    Examples
    ========

    >>> from sympy import Q
    >>> from sympy.abc import x, y
    >>> from sympy.assumptions.backends.sympy_extras import to_statement
    >>> to_statement(Q.positive(x) & Q.integer(y))  # doctest: +SKIP
    (x > 0) & Contains(y, Integers)
    >>> print(to_statement(Q.prime(x)))  # doctest: +SKIP
    None
    """
    if isinstance(formula, AppliedPredicate):
        function, args = formula.function, formula.arguments
        if function == Q.is_true:
            return to_statement(args[0], keep)
        if function in _UNARY and len(args) == 1:
            return _UNARY[function](args[0])
        if function in _BINARY and len(args) == 2:
            return _BINARY[function](*args, evaluate=False)
        return formula if keep else None
    if isinstance(formula, _COMPOUND):
        args = [to_statement(arg, keep) for arg in formula.args]
        if any(arg is None for arg in args):
            return None
        return formula.func(*args)
    return formula


def ask(proposition, assumptions):
    statement = to_statement(proposition)
    if statement is None:
        return None
    return _extras_ask(statement, to_statement(assumptions, keep=True))
