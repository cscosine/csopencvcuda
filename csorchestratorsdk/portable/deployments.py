"""The deployments of a csCMake build (``cs_deployment``): find their folders, archive them, run them.

A csCMake build writes ``cs-deployments.json`` in its top build folder: for each deployment, its project, its
configurations and its folder in each of them (made by the install). This module reads it.

Portable: copied into the projects (``csorchestratorsdk``) and run by the generated GitHub workflow steps; the
standard library only.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# the messages (errors are returned): print by default; csorchestrator passes its report locally
Log = Callable[[str], object]

DEPLOYMENTS_FILE = "cs-deployments.json"
SYSTEM_REQUIREMENTS_FILE = "system-requirements.txt"

# the build configurations of csorchestrator (BuildConfig values, e.g. "debug-release") -> CMake configurations
_CMAKE_CONFIGS = {
    "debug": "Debug",
    "release": "Release",
    "relWithDebInfo": "RelWithDebInfo",
    "paranoid": "Paranoid",
}


@dataclass(frozen=True)
class DeploymentFolder:
    project: str  # the namespace of the csCMake project of the deployment
    name: str  # cs_deployment(<name> ...)
    config: str  # CMake configuration, e.g. Release
    folder: Path


def cmake_configs_of_build_config(build_config: str) -> list[str]:
    """The CMake configurations of a csorchestrator build configuration, e.g. "debug-release" -> Debug, Release."""
    return [_CMAKE_CONFIGS[part] for part in build_config.split("-") if part in _CMAKE_CONFIGS]


def find_deployment_folders(build_dir: Path, configs: list[str]) -> tuple[list[DeploymentFolder], list[str]]:
    """The folders of the deployments of the builds in ``build_dir`` (every ``cs-deployments.json`` below it), for the
    configurations both listed by a deployment and in ``configs`` (the ones built); and the errors: a file not read, a
    folder that does not exist (the install did not make the deployment)."""
    folders: dict[tuple[str, str, str], DeploymentFolder] = {}
    errors: list[str] = []
    for deployments_file in sorted(build_dir.rglob(DEPLOYMENTS_FILE)):
        try:
            data = json.loads(deployments_file.read_text(encoding="utf-8"))
            entries = data["deployments"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            errors.append(f"{deployments_file}: not read ({e})")
            continue
        for entry in entries:
            for config in entry["configs"]:
                if config not in configs:
                    continue
                folder = Path(entry["folders"][config])
                # single-config builds: one file per build folder, the same deployments
                folders[(entry["project"], entry["name"], config)] = DeploymentFolder(
                    entry["project"], entry["name"], config, folder
                )
    for deployment in folders.values():
        if not deployment.folder.is_dir():
            errors.append(
                f"deployment {deployment.name} ({deployment.project}, {deployment.config}): {deployment.folder} not "
                "found (made by the install of the build)"
            )
    return sorted(folders.values(), key=lambda d: (d.project, d.name, d.config)), errors


def deployment_archive_base_name(
    deployment: DeploymentFolder, project_name: str, project_name_and_version: str, variant: str
) -> str:
    """``<project>-<version>-<variant>-<deployment>-<config>``; the project of the deployment after the variant when it
    is not the project of the orchestrator (e.g. a dependency built in the same workspace)."""
    name = deployment.name if deployment.project == project_name else f"{deployment.project}-{deployment.name}"
    return f"{project_name_and_version}-{variant}-{name}-{deployment.config}"


def _archive_folder(folder: Path, output_dir: Path, base_name: str, use_zip: bool) -> Path:
    """Archive the content of ``folder`` in ``output_dir/<base_name>.tar.gz`` (or ``.zip``), under a folder
    ``<base_name>/`` (symlinks kept in a tar)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if use_zip:
        output = output_dir / f"{base_name}.zip"
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{base_name}/{path.relative_to(folder).as_posix()}")
        return output
    output = output_dir / f"{base_name}.tar.gz"
    with tarfile.open(output, "w:gz") as archive:
        archive.add(folder, arcname=base_name)
    return output


def create_deployment_archives(
    build_dir: Path,
    build_config: str,
    project_name: str,
    project_name_and_version: str,
    variant: str,
    output_dir: Path,
    use_zip: bool | None = None,
    log: Log = print,
) -> list[str]:
    """Archive every deployment made by the builds in ``build_dir`` in the configurations of ``build_config``, in
    ``output_dir`` (``.zip`` on Windows, else ``.tar.gz``, unless ``use_zip``); the errors (none: archived)."""
    deployments, errors = find_deployment_folders(build_dir, cmake_configs_of_build_config(build_config))
    if errors:
        return errors
    zip_archives = sys.platform == "win32" if use_zip is None else use_zip
    for deployment in deployments:
        base_name = deployment_archive_base_name(deployment, project_name, project_name_and_version, variant)
        archive = _archive_folder(deployment.folder, output_dir, base_name, zip_archives)
        log(f"deployment {deployment.name} ({deployment.config}): {archive}")
    if not deployments:
        log(f"no deployments in {build_dir}")
    return []


# kept by the clean environment: the display (a GUI application opens its windows there) and the locale, not a
# library search path
_DISPLAY_VARIABLES = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "LANG", "LC_ALL")


def clean_environment() -> dict[str, str]:
    """An environment with nothing to find libraries with: the system folders of the programs only (Linux, macOS:
    no LD_LIBRARY_PATH, DYLD_*; Windows: System32 only on PATH), and the display and locale variables of the caller."""
    if sys.platform == "win32":
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        return {"SystemRoot": system_root, "PATH": str(Path(system_root) / "System32")}
    environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    environment.update({name: os.environ[name] for name in _DISPLAY_VARIABLES if name in os.environ})
    return environment


def system_packages(folder: Path) -> list[str]:
    """The Debian packages of ``system-requirements.txt`` of a deployment (its ``apt install`` line; none without)."""
    requirements = folder / SYSTEM_REQUIREMENTS_FILE
    if not requirements.is_file():
        return []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if line.startswith("apt install "):
            return line.split()[2:]
    return []


def _install_system_packages(packages: list[str], log: Log) -> str | None:
    """``sudo apt-get install`` the packages (CI runners); an error, or None."""
    for command in (["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "-y", *packages]):
        log("$ " + " ".join(command))
        if subprocess.run(command, check=False).returncode != 0:
            return f"{' '.join(command[:4])}: failed"
    return None


@dataclass(frozen=True)
class DeploymentArchives:
    """Where the archives of the deployments are (create_deployment_archives), and how they are named."""

    folder: Path
    project_name: str
    project_name_and_version: str
    variant: str

    def find(self, deployment: DeploymentFolder) -> Path | None:
        """The archive of ``deployment`` (``.tar.gz`` or ``.zip``), or None."""
        base_name = deployment_archive_base_name(
            deployment, self.project_name, self.project_name_and_version, self.variant
        )
        for suffix in (".tar.gz", ".zip"):
            if (self.folder / f"{base_name}{suffix}").is_file():
                return self.folder / f"{base_name}{suffix}"
        return None


def _extract(archive: Path, destination: Path) -> Path:
    """Extract ``archive`` in ``destination``; the folder of the deployment in it (the only one at the top)."""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as content:
            content.extractall(destination)
    else:
        with tarfile.open(archive) as content:
            if hasattr(tarfile, "data_filter"):  # Python 3.11.4+: no path out of destination
                content.extractall(destination, filter="data")
            else:
                content.extractall(destination)  # noqa: S202 (our own archive)
    (folder,) = [path for path in destination.iterdir() if path.is_dir()]
    return folder


@dataclass(frozen=True)
class DeploymentRunOutput:
    """What an assessor gets: the run of a deployment in one configuration."""

    deployment: str
    config: str
    folder: Path  # the deployment, extracted from its archive
    exit_code: int
    output: str  # standard output and error, merged


# checks the output of a run: the errors (none: the run passes)
Assessor = Callable[[DeploymentRunOutput], list[str]]


@dataclass(frozen=True)
class DeploymentRun:
    deployment: str  # cs_deployment(<name> ...)
    command: list[str]  # "{folder}" replaced by the folder of the deployment (extracted from its archive)
    clean_environment: bool = True
    install_system_requirements: bool = False  # Linux: apt-get install the packages of system-requirements.txt first
    expect_exit_code: int | None = 0  # None: any exit code (e.g. the assessor checks it)
    timeout_seconds: float = 120
    environment: dict[str, str] = field(default_factory=dict)  # set on top (e.g. QT_OPENGL=software)
    # "module:function", an Assessor checking the output after the exit code: a module of the project (its root on
    # the import path), that imports the standard library and csorchestratorsdk only (it runs in the CI step)
    assessor: str | None = None


def load_assessor(spec: str, search_path: Path | None = None) -> Assessor | str:
    """The assessor ``module:function`` (``search_path`` first on the import path, e.g. the root of the project);
    an error message if it cannot be loaded."""
    module_name, _, function_name = spec.partition(":")
    if not module_name or not function_name:
        return f"assessor {spec!r}: expected 'module:function'"
    if search_path is not None and str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))
    try:
        function = getattr(importlib.import_module(module_name), function_name)
    except (ImportError, AttributeError) as error:
        return f"assessor {spec!r}: {error}"
    if not callable(function):
        return f"assessor {spec!r}: not a function"
    return function  # type: ignore[no-any-return]


def run_deployment(
    build_dir: Path,
    build_config: str,
    run: DeploymentRun,
    archives: DeploymentArchives,
    log: Log = print,
    assessor_search_path: Path | None = None,
) -> list[str]:
    """Run the command of ``run`` on its deployment extracted from its archive in a temporary folder (outside the
    workspace: the archive is complete, the deployment runs once moved), in every configuration of ``build_config``
    the deployment lists; the errors: the deployment not found, not made or not archived, another exit code, a
    timeout, the errors of the assessor (loaded from ``assessor_search_path``, e.g. the root of the project)."""
    assessor: Assessor | None = None
    if run.assessor is not None:
        loaded = load_assessor(run.assessor, assessor_search_path)
        if isinstance(loaded, str):
            return [f"deployment {run.deployment}: {loaded}"]
        assessor = loaded
    deployments, errors = find_deployment_folders(build_dir, cmake_configs_of_build_config(build_config))
    deployments = [d for d in deployments if d.name == run.deployment]
    if errors:
        return errors
    if not deployments:
        return [f"deployment {run.deployment}: not in the builds of {build_dir} ({build_config})"]
    for deployment in deployments:
        archive = archives.find(deployment)
        if archive is None:
            errors.append(
                f"deployment {deployment.name} ({deployment.config}): no archive in {archives.folder} (run after "
                "the archives of the deployments)"
            )
            continue
        with tempfile.TemporaryDirectory(prefix="cs-deployment-") as temporary:
            errors.extend(
                _run_in(deployment.name, deployment.config, _extract(archive, Path(temporary)), run, assessor, log)
            )
    return errors


def _run_in(name: str, config: str, folder: Path, run: DeploymentRun, assessor: Assessor | None, log: Log) -> list[str]:
    """Run the command of ``run`` on ``folder``, the deployment name in config; the errors."""
    label = f"deployment {name} ({config})"
    if run.install_system_requirements and sys.platform.startswith("linux"):
        packages = system_packages(folder)
        if packages and (error := _install_system_packages(packages, log)) is not None:
            return [f"{label}: {error}"]
    command = [part.replace("{folder}", folder.as_posix()) for part in run.command]
    if shutil.which(command[0]) is None and not Path(command[0]).is_file():
        return [f"{label}: {command[0]} not found"]
    environment = clean_environment() if run.clean_environment else dict(os.environ)
    environment.update(run.environment)
    log(f"{label}: $ {' '.join(command)}")
    _no_error_dialogs()
    try:
        result = subprocess.run(
            command,
            env=environment,
            timeout=run.timeout_seconds,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
    except subprocess.TimeoutExpired as expired:
        _log_output(expired.output, log)
        _log_files(folder, log)
        return [f"{label}: still running after {run.timeout_seconds} s"]
    _log_output(result.stdout, log)
    if run.expect_exit_code is not None and result.returncode != run.expect_exit_code:
        _log_files(folder, log)
        return [f"{label}: exit code {result.returncode}, expected {run.expect_exit_code}"]
    if assessor is not None:
        errors = assessor(DeploymentRunOutput(name, config, folder, result.returncode, result.stdout))
        if errors:
            _log_files(folder, log)
            return [f"{label}: {error}" for error in errors]
        log(f"{label}: exit code {result.returncode}, output assessed ({run.assessor})")
        return []
    log(f"{label}: exit code {result.returncode}, as expected")
    return []


def _log_output(output: str | bytes | None, log: Log) -> None:
    """Log the output of the run (captured, for the assessor)."""
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    if output:
        log(output.rstrip("\n"))


def _no_error_dialogs() -> None:
    """Windows: no error dialog for the processes started from now on (inherited): a crash or a DLL not found ends
    them with an exit code, instead of a dialog waiting for a click (on a machine without a user, until the
    timeout)."""
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415 (Windows only)

        sem_failcriticalerrors, sem_nogpfaulterrorbox, sem_noopenfileerrorbox = 0x0001, 0x0002, 0x8000
        ctypes.windll.kernel32.SetErrorMode(  # type: ignore[attr-defined,unused-ignore]
            sem_failcriticalerrors | sem_nogpfaulterrorbox | sem_noopenfileerrorbox
        )


def _log_files(folder: Path, log: Log) -> None:
    """Log the files of the deployment in folder (a failed run: what it ships)."""
    files = sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file())
    log(f"the files of the deployment ({len(files)}): {', '.join(files)}")
