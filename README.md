# sympy-satassume: SymPy with pluggable assumption backends

This repository is a copy of [SymPy](https://github.com/sympy/sympy) (at
upstream commit
[`751a370`](https://github.com/sympy/sympy/commit/751a37041610a83fb22559bc0618f84623fcea04),
with its history) in which SymPy's assumption systems are answered by a
pluggable **backend**. The default backend is
[satassume](https://github.com/tilorc-bot/satassume), a SAT (CDCL) based
engine, which replaces **both** assumption systems, with **no fallback** to
SymPy's own code: its answer is returned as it is, `None` included. The one
exception: a query of the new system that satassume answers `None` and that
`satassume.sympy_api.out_of_scope` gives a category (a relation, a matrix or
custom predicate, in the proposition or the assumptions) is answered by
SymPy's own `ask`.

It is an experiment, not a SymPy release, and it is not affiliated with the
SymPy project. The package is still imported as `sympy`.

SymPy has two assumption systems:

- the *old* system: the `expr.is_*` properties (`sympy/core/assumptions.py`
  and the `_eval_is_*` handlers);
- the *new* system: `sympy.assumptions.ask.ask` and what is built on it, such
  as `refine`.

## Backends

| backend | old system (`expr.is_*`) | new system (`ask`, `refine`) |
|---|---|---|
| `satassume` (default) | satassume (`Engine.is_`) | satassume (`satassume.sympy_api.ask`) |
| `sympy` | SymPy | SymPy (identical to upstream) |
| `sympy_extras` | SymPy | [sympy-extras](https://github.com/Upabjojr/sympy-extras) (`sympy_extras.assumptions.ask`) |

Choose the backend when `sympy` is imported, with an environment variable:

```
SYMPY_ASSUMPTIONS_BACKEND=satassume     # the default
SYMPY_ASSUMPTIONS_BACKEND=sympy         # SymPy's own assumptions
SYMPY_ASSUMPTIONS_BACKEND=sympy_extras  # ask/refine through sympy-extras
```

`SYMPY_ASSUMPTIONS_BACKEND_OLD` and `SYMPY_ASSUMPTIONS_BACKEND_NEW` choose the
backend of one system only, for example `SYMPY_ASSUMPTIONS_BACKEND_OLD=sympy`
with the default keeps the `is_*` properties of SymPy and answers only `ask`
with satassume. To see which backends are active:

```python
>>> from sympy.assumptions.backends import active_backends
>>> active_backends()
{'old': 'satassume', 'new': 'satassume'}
```

The pytest header also shows them (`assumptions backends: old=... new=...`).

How it works (`sympy/assumptions/backends/`):

- A backend is a module that may define `ask(proposition, assumptions)` (new
  system), `is_(expr, fact)` (old system) and `setup()`. A system whose
  function is missing stays with SymPy's code.
- The backend module is imported at the end of `import sympy` (both satassume
  and sympy-extras import SymPy, so they cannot be imported earlier).
- New system: `ask()` calls the backend after checking and sympifying its
  arguments and merging the global assumptions. Every caller of `ask`
  (`refine`, the handlers, matrices, ...) goes through it. A backend that
  returns `NotImplemented` leaves the query to SymPy's code: the satassume
  backend does so when satassume answers `None` and
  `satassume.sympy_api.out_of_scope` gives a category (`relation`, `matrix`,
  `custom` or `other`) for the query. That includes every query with a
  relation (even one that satassume's theories interpret) and matrix or
  custom predicates that appear only in the assumptions.
- Old system: the module function `sympy.core.assumptions._ask`, which every
  `is_*` property calls on a miss of the object's cache, is replaced. The
  backend's answer is stored in the cache of the object together with its
  implications, as SymPy's own code stores its answers (SymPy's code, which
  answers the nested queries, skips stored facts and so cannot deduce from
  them). So the facts it implies are then answered by SymPy's rules instead
  of the backend. An answer that SymPy's rules find inconsistent with a
  stored fact is stored without its implications (a None answer then keeps
  the stored value).
- Old system, class-level facts: SymPy turns the facts it derives from a
  class's explicit `is_commutative = False` alone (`Commutator.is_zero =
  False`, `is_integer`, `is_complex`, ...) into class attributes and
  default facts, so they are answered without `_ask`. They describe how
  the object is built, not its value: `Commutator(b - b, a)` is 0, so the
  backend must decide them. While a backend answers the old system, each
  such fact of each class (those defined so far and every class defined
  later) is removed from the class's default facts. It is turned back into
  a property that asks, and `commutative` stays a class attribute.
- Re-entrancy: while a backend runs, every query it makes in turn (satassume
  reads facts of numbers through `is_*`; sympy-extras calls `sympy.ask`) is
  answered by SymPy's own code.
- `sympy_extras` translates each `Q` predicate to a statement of sympy-extras
  (`Q.positive(x)` to `x > 0`, `Q.integer(x)` to
  `Contains(x, Integers)`, `Q.even(x)` to `Contains(x/2, Integers)`, `Q.gt(x, y)`
  to `x > y`, ...). A proposition with a predicate that has no statement
  (`Q.finite`, `Q.prime`, the `extended_*` and matrix predicates, ...) gets
  `None`. Predicates without a statement in the assumptions are passed on
  unchanged, and sympy-extras gives them to SymPy's `ask`.
- `sympy_extras` answers only the new system. Routing `is_*` through it as
  well was tried and measured (`sympy/core/tests/test_arit.py` and
  `sympy/integrals/tests/test_integrals.py`, 303 tests, `-n 4`): with only
  `ask` through sympy-extras, 303 pass in 35 s; with `is_*` as well, 193 fail
  and an xdist worker crashes (144 s) when facts without a statement answer
  `None`, and 181 fail (116 s) even when those facts are left to SymPy.
  `integrate(x*exp(x), x)` raises `ValueError`. Most facts of the old system
  (`commutative`, `finite`, `extended_real`, ...) have no statement in
  sympy-extras.

The change to SymPy itself is small: `sympy/assumptions/backends/` (new),
a hook of a few lines in `sympy/assumptions/ask.py`, 3 lines at the end of
`sympy/__init__.py`, the xfail hook in `conftest.py`, and `setup.py`.
One fix in SymPy's own handlers comes with it: the number handlers of
`sympy/assumptions/handlers/order.py` and `sets.py` take an `evalf` result
that is no Number (no `_prec`, as for `Operator(1)`, whose `is_number` is
True) as unevaluated, and so answer None instead of raising
`AttributeError`. Upstream raises too wherever `Q.real` is not False
(`ask(Q.nonzero(Operator(pi)**2))`); for `Operator(1)` the class-level
facts of non-commutative classes made it False.

## Installation

```
pip install "sympy @ git+https://github.com/tilorc-bot/sympy-satassume"
pip install "sympy[sympy_extras] @ git+https://github.com/tilorc-bot/sympy-satassume"  # with sympy-extras
```

or, from a clone, `pip install -e .` (or `-e '.[sympy_extras]'`).

Pinned dependencies (`setup.py`):

- satassume `6f50449caeafab2b4443bfb5d4a71f881e83fd0e` (a dependency:
  `satassume @ git+https://github.com/tilorc-bot/satassume@6f50449...`);
- sympy-extras `ae8f9f6c959111413c2fbe0675ce76e52e4d7502` (the optional extra
  `sympy_extras`).

sympy-extras requires `sympy>=1.14`. This copy is `sympy 1.15.0.dev0`, which
satisfies it, so installing the extra (or sympy-extras afterwards, without
`--upgrade`) keeps this copy; check with
`python -c "import sympy; print(sympy.__file__)"`. Do not run
`pip install -U sympy-extras`: it may replace this copy with SymPy from PyPI.

## Test-suite results per backend

The full test suite without slow tests and doctests (SymPy's defaults), run
in 150 chunks (`bin/assumption_backends/chunks.txt`) with `pytest -n N
--timeout=60` (N xdist workers, given per run below), Python 3.14.8, x86_64
Linux. The expected failures of each
backend are listed, with a cause tag, in **one file per backend**:

- [`sympy/testing/assumption_backend_xfails/satassume.txt`](sympy/testing/assumption_backend_xfails/satassume.txt)
- [`sympy/testing/assumption_backend_xfails/sympy_extras.txt`](sympy/testing/assumption_backend_xfails/sympy_extras.txt)

The root `conftest.py` marks the listed tests as non-strict `xfail` (tests
tagged `timeout` or `recursion` are not run) and reports the collection error
of a listed module as a skip. `pytest --no-backend-xfails` turns this off.
See [the README of that directory](sympy/testing/assumption_backend_xfails/README.md).

Measured on 2026-10-18 with the lists as committed (464 entries for
satassume, 48 for sympy_extras):

| backend | `-n` | tests | passed | failed | xfailed: listed + upstream | xpassed: listed + upstream | skipped | time (sum of chunks) |
|---|---|---|---|---|---|---|---|---|
| `sympy` | 4 | 14330 | 13265 | 0 | 0 + 329 | 0 + 2 | 734 | 899 s |
| `satassume` | 16 | 14317 | 12789 | **0** | 462 + 324 | 1 + 7 | 734 | 891 s |
| `sympy_extras` | 4 | 14330 | 13217 | **0** | 48 + 326 | 0 + 5 | 734 | 741 s |

- *listed* counts the tests in the backend's xfail file, *upstream* SymPy's
  own `XFAIL` tests. Of the 462 listed xfails of satassume, 28 (tags
  `timeout` and `recursion`) are not run. The listed xpass of satassume is
  `test_arit.py::test_pow_im`, which fails only in some runs.
- satassume has 13 tests fewer: `sympy/solvers/ode/tests/test_single.py`
  fails at collection with satassume and is reported as one skipped module.
- Measured again on 2026-10-20 with satassume `29a5ed7` and 240 entries
  (satassume backend, `-n 8`): 13030 passed, 1 failed
  (`test_integrals.py::test_issue_14241`, listed since), 562 xfailed,
  8 xpassed (`test_pow_im` and 7 upstream), 731 skipped;
  `test_single.py` collects now.
- Measured again on 2026-10-20 with satassume `93a612e` and 194 entries
  (satassume backend, `-n 8`, 1178 s): 13078 passed, 0 failed, 518 xfailed
  (194 listed + 324 upstream), 7 xpassed (upstream), 731 skipped, of 14334.
  `test_pow_im` passed (in this run and in the runs of the listed ids), so
  it is no longer listed.
- Measured again on 2026-10-20 with satassume `b26f174` (#180 final review
  F1, F3) and the F2 wrapper fix (satassume backend, `-n 8`): 13076 passed,
  3 failed before listing (`test_hermitian`, two `test_delta.py`
  deltaproduct tests, answers given up for soundness; listed since, 197
  entries), 518 xfailed (194 listed + 324 upstream), 7 xpassed (upstream),
  731 skipped, of 14335.
- Measured again on 2026-10-21 with satassume `92f4bf4` (#233: level-2
  commutativity only over terms commutative by construction, #235: no
  template fact at an argument holding an explicit nan or infinity;
  satassume backend, `-n 8`, 1225 s): 13076 passed, 0 failed, 521 xfailed
  (197 listed + 324 upstream), 7 xpassed (upstream), 731 skipped, of 14335.
  Every listed id still fails, so the list is unchanged (197 entries).
- Measured again on 2026-10-21 with satassume `6f50449` (#236: the nan
  guard follows every argument that carries a value, #238: level 2 only
  for a matrix or a plain undefined function) and the backend answering
  the class-level implications of `is_commutative = False` (satassume
  backend, `-n 8`, 3281 s on a loaded host): 13075 passed, 0 failed, 521
  xfailed (197 listed + 324 upstream), 7 xpassed (upstream), 731 skipped,
  2 timeouts, of 14336. The timeouts (`test_limits.py::test_issue_17431`,
  `test_recurr.py::test_issue_17990`) come from host load (load average
  15-18 on 12 CPUs): run alone, they take 8 s and 39 s, the same at the
  old pin and without the class-level change. Every listed id still fails,
  so the list is unchanged (197 entries).
- With the `sympy` backend the results are those of upstream SymPy at
  `751a370` (the same run of upstream without this change, in the
  experiment, gave the same outcome for every test; this copy adds the 3
  tests of `sympy/assumptions/tests/test_backends.py`).
- `sympy_extras` without its list (`--no-backend-xfails`, `-n 4`, 1000 s):
  13217 passed, 48 failed, 326 xfailed, 5 xpassed, 734 skipped. The 48
  failures are the list (`assumptions` 24, `matrices` 17, `tensor` 3,
  `core` 2, `codegen` 1, `logic` 1).
- satassume with its first list (443 entries, seeded from the experiment,
  `-n 4`, 999 s): 2 unexpected failures; a second sweep with 461 entries
  (`-n 2`, 1347 s): 2 others. Both were added, together with the tests the
  failures moved to in reruns of the affected chunks (see the header of
  `satassume.txt`).

The runs shared the machine with other jobs (the `-n 2` and `-n 4` runs with
heavy load, the `-n 16` run with light load). Times, and which tests hit the
60 s limit or a `RecursionError`, depend on the load, on `-n`, and on the
order of the tests in each worker: satassume keeps state between queries
and some of its failures are order dependent. Other runs may therefore show
a few unexpected failures or xpasses.

## Regenerating the xfail lists

The scripts are in `bin/assumption_backends/`:

- `run_chunks.sh BACKEND CHUNKFILE OUTDIR [pytest args]` runs the chunks,
  each with `timeout 270` (split a chunk that hits it), with `NPROC` xdist
  workers (default 4). It is resumable: chunks already in `OUTDIR/status.tsv`
  are skipped. It records every test outcome with `outcomes_plugin.py`.
- `xfails.py summary RUNDIR [BASEDIR]` prints the counts, the unexpected
  failures, and with `BASEDIR` the failures that are new against it.
- `xfails.py make BACKEND RUNDIR BASEDIR [PREVIOUS]` writes the list: the
  tests that fail in `RUNDIR` but not in `BASEDIR`, with the tags of
  `PREVIOUS` kept and new tags derived from the failure message.

```
B=bin/assumption_backends
$B/run_chunks.sh sympy $B/chunks.txt /tmp/run-sympy
$B/run_chunks.sh satassume $B/chunks.txt /tmp/run-satassume --no-backend-xfails
python $B/xfails.py make satassume /tmp/run-satassume /tmp/run-sympy \
    sympy/testing/assumption_backend_xfails/satassume.txt > /tmp/satassume.txt
mv /tmp/satassume.txt sympy/testing/assumption_backend_xfails/satassume.txt
$B/run_chunks.sh satassume $B/chunks.txt /tmp/check-satassume   # verify
python $B/xfails.py summary /tmp/check-satassume                 # 0 unexpected
```

Some failures depend on the order of the tests and on the load of the machine
(timeouts), so a verification run may show a few unexpected failures that the
first run did not: add them (rerun `make` with both runs, or add the lines by
hand) and keep the entries that pass (XPASS) unless they pass in several runs.

The tags of `satassume.txt` (`none`, `wrong`, `extra`, `agree`, `unrecorded`,
`engine-exc`, `timeout`, `recursion`) come from a root-cause analysis of the
experiment that preceded this repository: every satassume answer was recorded
during the failing tests and compared with SymPy's answer to the same query
in a separate process. `xfails.py make` only derives the coarser tags
`assert`, `none` (an assertion `assert None is ...`), `exc-<Exception>`,
`timeout` and `recursion` from the failure message.

## License

SymPy's [LICENSE](LICENSE) (New BSD) covers this repository; see
[AUTHORS](AUTHORS) for SymPy's authors. The README of SymPy follows.

---

# SymPy

[![pypi version](https://img.shields.io/pypi/v/sympy.svg)](https://pypi.python.org/pypi/sympy)
[![Join the chat at https://gitter.im/sympy/sympy](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/sympy/sympy?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Zenodo Badge](https://zenodo.org/badge/18918/sympy/sympy.svg)](https://zenodo.org/badge/latestdoi/18918/sympy/sympy)
[![Downloads](https://pepy.tech/badge/sympy/month)](https://pepy.tech/project/sympy)
[![GitHub Issues](https://img.shields.io/badge/issue_tracking-github-blue.svg)](https://github.com/sympy/sympy/issues)
[![Git Tutorial](https://img.shields.io/badge/PR-Welcome-%23FF8300.svg?)](https://git-scm.com/book/en/v2/GitHub-Contributing-to-a-Project)
[![Powered by NumFocus](https://img.shields.io/badge/powered%20by-NumFOCUS-orange.svg?style=flat&colorA=E1523D&colorB=007D8A)](https://numfocus.org)
[![Commits since last release](https://img.shields.io/github/commits-since/sympy/sympy/latest.svg?longCache=true&style=flat-square&logo=git&logoColor=fff)](https://github.com/sympy/sympy/releases)

[![SymPy Banner](https://github.com/sympy/sympy/raw/master/banner.svg)](https://sympy.org/)


See the [AUTHORS](https://github.com/sympy/sympy/blob/master/AUTHORS) file for the list of authors.

And many more people helped on the SymPy mailing list, reported bugs,
helped organize SymPy's participation in the Google Summer of Code, the
Google Highly Open Participation Contest, Google Code-In, wrote and
blogged about SymPy...

License: New BSD License (see the [LICENSE](https://github.com/sympy/sympy/blob/master/LICENSE) file for details) covers all
files in the sympy repository unless stated otherwise.

Our mailing list is at
<https://groups.google.com/forum/?fromgroups#!forum/sympy>.

We have a community chat at [Gitter](https://gitter.im/sympy/sympy). Feel
free to ask us anything there. We have a very welcoming and helpful
community.

## Download

The recommended installation method is through Anaconda,
<https://www.anaconda.com/products/distribution>

You can also get the latest version of SymPy from
<https://pypi.python.org/pypi/sympy/>

To get the git version do

    $ git clone https://github.com/sympy/sympy.git

For other options (tarballs, debs, etc.), see
<https://docs.sympy.org/dev/install.html>.

## Documentation and Usage

For in-depth instructions on installation and building the
documentation, see the [SymPy Documentation Style Guide](https://docs.sympy.org/dev/documentation-style-guide.html).

Everything is at:

<https://docs.sympy.org/>

You can generate everything at the above site in your local copy of
SymPy by:

    $ cd doc
    $ make html

Then the docs will be in <span class="title-ref">\_build/html</span>. If
you don't want to read that, here is a short usage:

From this directory, start Python and:

``` python
>>> from sympy import Symbol, cos
>>> x = Symbol('x')
>>> e = 1/cos(x)
>>> print(e.series(x, 0, 10))
1 + x**2/2 + 5*x**4/24 + 61*x**6/720 + 277*x**8/8064 + O(x**10)
```

SymPy also comes with a console that is a simple wrapper around the
classic python console (or IPython when available) that loads the SymPy
namespace and executes some common commands for you.

To start it, issue:

    $ bin/isympy

from this directory, if SymPy is not installed or simply:

    $ isympy

if SymPy is installed.

## Installation

To install SymPy using PyPI, run the following command:

    $ pip install sympy

To install SymPy using Anaconda, run the following command:

    $ conda install -c anaconda sympy

To install SymPy from GitHub source, first clone SymPy using `git`:

    $ git clone https://github.com/sympy/sympy.git

Then, in the `sympy` repository that you cloned, simply run:

    $ pip install .

See <https://docs.sympy.org/dev/install.html> for more information.

## Contributing

We welcome contributions from anyone, even if you are new to open
source. Please read our [Contributor Guide](https://docs.sympy.org/dev/contributing/index.html)
page and the [SymPy Documentation Style Guide](https://docs.sympy.org/dev/documentation-style-guide.html). If you
are new and looking for some way to contribute, a good place to start is
to look at the issues tagged [Easy to Fix](https://github.com/sympy/sympy/issues?q=is%3Aopen+is%3Aissue+label%3A%22Easy+to+Fix%22).

Please note that all participants in this project are expected to follow
our Code of Conduct. By participating in this project you agree to abide
by its terms. See [CODE\_OF\_CONDUCT.md](CODE_OF_CONDUCT.md).

## Tests

To execute all tests, run:

    $./setup.py test

in the current directory.

For the more fine-grained running of tests or doctests, use `bin/test`
or respectively `bin/doctest`. The master branch is automatically tested
by GitHub Actions.

To test pull requests, use
[sympy-bot](https://github.com/sympy/sympy-bot).

## Regenerate Experimental <span class="title-ref">LaTeX</span> Parser/Lexer

The parser and lexer were generated with the [ANTLR4](http://antlr4.org)
toolchain in `sympy/parsing/latex/_antlr` and checked into the repo.
Presently, most users should not need to regenerate these files, but
if you plan to work on this feature, you will need the `antlr4`
command-line tool (and you must ensure that it is in your `PATH`).
One way to get it is:

    $ conda install -c conda-forge antlr=4.11.1

Alternatively, follow the instructions on the ANTLR website and download
the `antlr-4.11.1-complete.jar`. Then export the `CLASSPATH` as instructed
and instead of creating `antlr4` as an alias, make it an executable file
with the following contents:
``` bash
#!/bin/bash
java -jar /usr/local/lib/antlr-4.11.1-complete.jar "$@"
```

After making changes to `sympy/parsing/latex/LaTeX.g4`, run:

    $ ./setup.py antlr

## Clean

To clean everything (thus getting the same tree as in the repository):

    $ git clean -Xdf

which will clear everything ignored by `.gitignore`, and:

    $ git clean -df

to clear all untracked files. You can revert the most recent changes in
git with:

    $ git reset --hard

WARNING: The above commands will all clear changes you may have made,
and you will lose them forever. Be sure to check things with `git
status`, `git diff`, `git clean -Xn`, and `git clean -n` before doing any
of those.

## Bugs

Our issue tracker is at <https://github.com/sympy/sympy/issues>. Please
report any bugs that you find. Or, even better, fork the repository on
GitHub and create a pull request. We welcome all changes, big or small,
and we will help you make the pull request if you are new to git (just
ask on our mailing list or Gitter Channel). If you further have any queries, you can find answers
on Stack Overflow using the [sympy](https://stackoverflow.com/questions/tagged/sympy) tag.

## Brief History

SymPy was started by Ondřej Čertík in 2005, he wrote some code during
the summer, then he wrote some more code during summer 2006. In February
2007, Fabian Pedregosa joined the project and helped fix many things,
contributed documentation, and made it alive again. 5 students (Mateusz
Paprocki, Brian Jorgensen, Jason Gedge, Robert Schwarz, and Chris Wu)
improved SymPy incredibly during summer 2007 as part of the Google
Summer of Code. Pearu Peterson joined the development during the summer
2007 and he has made SymPy much more competitive by rewriting the core
from scratch, which has made it from 10x to 100x faster. Jurjen N.E. Bos
has contributed pretty-printing and other patches. Fredrik Johansson has
written mpmath and contributed a lot of patches.

SymPy has participated in every Google Summer of Code since 2007. You
can see <https://github.com/sympy/sympy/wiki#google-summer-of-code> for
full details. Each year has improved SymPy by bounds. Most of SymPy's
development has come from Google Summer of Code students.

In 2011, Ondřej Čertík stepped down as lead developer, with Aaron
Meurer, who also started as a Google Summer of Code student, taking his
place. Ondřej Čertík is still active in the community but is too busy
with work and family to play a lead development role.

Since then, a lot more people have joined the development and some
people have also left. You can see the full list in [AUTHORS](https://github.com/sympy/sympy/blob/master/AUTHORS).

The git history goes back to 2007 when development moved from svn to hg.
To see the history before that point, look at
<https://github.com/sympy/sympy-old>.

You can use git to see the biggest developers. The command:

    $ git shortlog -ns

will show each developer, sorted by commits to the project. The command:

    $ git shortlog -ns --since="1 year"

will show the top developers from the last year.

## Citation

To cite SymPy in publications use

> Meurer A, Smith CP, Paprocki M, Čertík O, Kirpichev SB, Rocklin M,
> Kumar A, Ivanov S, Moore JK, Singh S, Rathnayake T, Vig S, Granger BE,
> Muller RP, Bonazzi F, Gupta H, Vats S, Johansson F, Pedregosa F, Curry
> MJ, Terrel AR, Roučka Š, Saboo A, Fernando I, Kulal S, Cimrman R,
> Scopatz A. (2017) SymPy: symbolic computing in Python. *PeerJ Computer
> Science* 3:e103 <https://doi.org/10.7717/peerj-cs.103>

A BibTeX entry for LaTeX users is

``` bibtex
@article{10.7717/peerj-cs.103,
 title = {SymPy: symbolic computing in Python},
 author = {Meurer, Aaron and Smith, Christopher P. and Paprocki, Mateusz and \v{C}ert\'{i}k, Ond\v{r}ej and Kirpichev, Sergey B. and Rocklin, Matthew and Kumar, Amit and Ivanov, Sergiu and Moore, Jason K. and Singh, Sartaj and Rathnayake, Thilina and Vig, Sean and Granger, Brian E. and Muller, Richard P. and Bonazzi, Francesco and Gupta, Harsh and Vats, Shivam and Johansson, Fredrik and Pedregosa, Fabian and Curry, Matthew J. and Terrel, Andy R. and Rou\v{c}ka, \v{S}t\v{e}p\'{a}n and Saboo, Ashutosh and Fernando, Isuru and Kulal, Sumith and Cimrman, Robert and Scopatz, Anthony},
 year = 2017,
 month = Jan,
 keywords = {Python, Computer algebra system, Symbolics},
 abstract = {
            SymPy is an open-source computer algebra system written in pure Python. It is built with a focus on extensibility and ease of use, through both interactive and programmatic applications. These characteristics have led SymPy to become a popular symbolic library for the scientific Python ecosystem. This paper presents the architecture of SymPy, a description of its features, and a discussion of select submodules. The supplementary material provides additional examples and further outlines details of the architecture and features of SymPy.
         },
 volume = 3,
 pages = {e103},
 journal = {PeerJ Computer Science},
 issn = {2376-5992},
 url = {https://doi.org/10.7717/peerj-cs.103},
 doi = {10.7717/peerj-cs.103}
}
```

SymPy is BSD licensed, so you are free to use it whatever you like, be
it academic, commercial, creating forks or derivatives, as long as you
copy the BSD statement if you redistribute it (see the LICENSE file for
details). That said, although not required by the SymPy license, if it
is convenient for you, please cite SymPy when using it in your work and
also consider contributing all your changes back, so that we can
incorporate it and all of us will benefit in the end.
