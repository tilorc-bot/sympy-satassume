# Expected test failures of the assumptions backends

One file per backend, `<backend>.txt`, lists the tests that fail with that
backend and pass with SymPy's own assumptions (`SYMPY_ASSUMPTIONS_BACKEND=sympy`,
which has no file). The root `conftest.py` reads the file of the active backend
(`sympy.assumptions.backends.xfail_key()`) and

* marks each listed test as a non-strict xfail (some failures depend on the
  order of the tests, so a listed test may pass: XPASS); tests tagged
  `timeout` or `recursion` are not run (`run=False`);
* turns the collection error of a listed module (an entry without `::`) into
  a skip with the reason, since a module that fails to import cannot be
  marked xfail.

`pytest --no-backend-xfails` ignores the file. The pytest header shows the
active backends and the file used.

Format: one entry per line, `TAG NODEID`; `#` starts a comment line. The tags
are explained at the top of each file.

To regenerate a list, see "Regenerating the xfail lists" in the README.md at
the root of the repository.
