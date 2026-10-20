"""The satassume backend: both assumption systems are answered by satassume.

satassume (https://github.com/tilorc-bot/satassume) is a SAT (CDCL) based
engine for ``ask``. Its answer is returned as it is: ``None`` for a query it
cannot decide. A query outside its scope (matrix predicates, for instance,
see ``satassume.sympy_api.out_of_scope``) that it answers ``None`` is
answered by SymPy's own ``ask``.
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
