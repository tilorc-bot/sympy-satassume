"""The satassume backend: both assumption systems are answered by satassume.

satassume (https://github.com/tilorc-bot/satassume) is a SAT (CDCL) based
engine for ``ask``. Its answer is returned as it is: ``None`` for a query it
cannot decide. A query that it answers ``None`` and that
``satassume.sympy_api.out_of_scope`` gives a category (a relation, a matrix or
custom predicate, in the proposition or the assumptions) is answered by
SymPy's own ``ask``.
"""
from __future__ import annotations

from satassume import sympy_api


def ask(proposition, assumptions):
    answer = sympy_api.ask(proposition, assumptions)
    if answer is None and sympy_api.out_of_scope(proposition,
                                                 assumptions) is not None:
        return NotImplemented
    return answer


def is_(expr, fact):
    return sympy_api.default_engine().is_(expr, fact)
