"""pytest options of every cscosine repository.

Owned by the project template (cs-project-template): change it there.

- ``--run-all``: run every test, as CI does.
- ``--run=<marker>[,<marker>...]``: also run the tests of these opt-in markers.

Opt-in markers are declared by the project in ``tests/conftest.py`` (only when it has some), with one or both hooks::

    def pytest_optin_markers() -> dict[str, str]:  # skipped by default, run by --run-all
        return {"slow": "long tests"}

    def pytest_manual_markers() -> dict[str, str]:  # skipped by default, not run by --run-all
        return {"smoke": "builds on every runner image, run by their own workflow"}

Each one is registered as a marker; a test carrying it is skipped unless ``--run=<name>`` is given (or ``--run-all``,
for the first hook). Other options and markers of the project also go in ``tests/conftest.py``; ``--run-all`` is
``config.getoption("--run-all")`` there.
"""

from __future__ import annotations

import pytest

# the markers skipped in this run (set in pytest_configure)
_SKIPPED = pytest.StashKey[set[str]]()


class _OptInHooks:
    @pytest.hookspec
    def pytest_optin_markers(self) -> dict[str, str]:  # type: ignore[empty-body]
        """Opt-in markers run by --run-all: name -> description."""

    @pytest.hookspec
    def pytest_manual_markers(self) -> dict[str, str]:  # type: ignore[empty-body]
        """Opt-in markers not run by --run-all: name -> description."""


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    pluginmanager.add_hookspecs(_OptInHooks)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-all",
        action="store_true",
        default=False,
        help="run every test (as CI does)",
    )
    parser.addoption(
        "--run",
        action="append",
        default=[],
        metavar="MARKER[,MARKER...]",
        help="also run the tests of these opt-in markers (declared in tests/conftest.py)",
    )


def _merge(results: list[dict[str, str]]) -> dict[str, str]:
    return {name: description for result in results for name, description in result.items()}


def pytest_configure(config: pytest.Config) -> None:
    optin = _merge(config.hook.pytest_optin_markers())
    manual = _merge(config.hook.pytest_manual_markers())
    for name, description in optin.items():
        config.addinivalue_line("markers", f"{name}: {description} (opt-in: --run={name} or --run-all)")
    for name, description in manual.items():
        config.addinivalue_line("markers", f"{name}: {description} (opt-in: --run={name}, not --run-all)")
    requested = {name.strip() for value in config.getoption("--run") for name in value.split(",") if name.strip()}
    unknown = requested - optin.keys() - manual.keys()
    if unknown:
        raise pytest.UsageError(f"--run: unknown opt-in markers {sorted(unknown)}; known: {sorted({*optin, *manual})}")
    run_all = bool(config.getoption("--run-all"))
    config.stash[_SKIPPED] = {name for name in optin if not run_all and name not in requested} | {
        name for name in manual if name not in requested
    }


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skipped = config.stash[_SKIPPED]
    for item in items:
        for name in skipped:
            if item.get_closest_marker(name):
                item.add_marker(pytest.mark.skip(reason=f"opt-in test ({name}): use --run={name}"))
                break
