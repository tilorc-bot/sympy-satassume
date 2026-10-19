"""The satassume backend: both assumption systems are answered by satassume.

satassume (https://github.com/tilorc-bot/satassume) is a SAT (CDCL) based
engine for ``ask``. Its answer is returned as it is: ``None`` for a query it
cannot decide or that is outside its scope (matrix predicates, for instance).
"""

from satassume import sympy_api


def ask(proposition, assumptions):
    return sympy_api.ask(proposition, assumptions)


def is_(expr, fact):
    return sympy_api.default_engine().is_(expr, fact)
