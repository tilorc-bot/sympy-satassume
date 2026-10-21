"""The satassume backend: both assumption systems are answered by satassume.

satassume (https://github.com/tilorc-bot/satassume) is a SAT (CDCL) based
engine for ``ask``. Its answer is returned as it is: ``None`` for a query it
cannot decide. A query that it answers ``None`` and that
``satassume.sympy_api.out_of_scope`` gives a category (a relation, a matrix or
custom predicate, in the proposition or the assumptions) is answered by
SymPy's own ``ask``; when only the assumptions are out of scope, only if
SymPy's code does not decide it under their in-scope conjuncts
(sympy-satassume#11).
"""
from __future__ import annotations

from satassume import sympy_api

from sympy.assumptions.ask import ask as sympy_ask
from sympy.core.singleton import S
from sympy.logic.boolalg import And


def ask(proposition, assumptions):
    answer = sympy_api.ask(proposition, assumptions)
    if answer is not None or sympy_api.out_of_scope(proposition,
                                                    assumptions) is None:
        return answer
    if sympy_api.out_of_scope(proposition) is not None:
        return NotImplemented
    # Only the assumptions are out of scope, and satassume does not decide
    # the proposition under the others.  If SymPy's code decides it under
    # the in-scope conjuncts alone (a weakening of the assumptions), its
    # answer does not use those out of scope: it is SymPy's own reasoning on
    # what satassume understands, wrong for nan-valued terms
    # (ask(Q.zero(Mul(0, oo, evaluate=False)), Q.invertible(M)) was True,
    # sympy-satassume#11), and satassume's None stands (None is always
    # sound).  The is_* reads of this query are answered by SymPy's code,
    # those of the full query below by satassume.  (ask here, while the
    # backend runs, is SymPy's code: see _wrap_ask.)
    known = And(*[c for c in And.make_args(assumptions)
                  if sympy_api.out_of_scope(S.true, c) is None])
    if sympy_ask(proposition, known, context=()) is not None:
        return None
    return NotImplemented


def is_(expr, fact):
    return sympy_api.default_engine().is_(expr, fact)
