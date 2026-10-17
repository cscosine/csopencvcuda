"""Canonical csopencvcuda configuration.

This file is shipped inside the csopencvcuda release bundle (it is listed in
`additional_files_list`) and imported by consuming projects as
`<dependencies_folder>.csopencvcuda_config`.

IMPORTANT: this file is intentionally SELF-CONTAINED: it may only import
csorchestrator modules and the Python standard library, never project-local
modules such as `utils.*`. The release bundle preserves relative paths, but the
consumer imports this module from its own `dependencies/` folder, so any
project-local import would not resolve there (see csqt6_config.py /
third_party_base_libs_config.py for the same pattern).

Contents:
- toolchain versions (CUDA/cuDNN) used by the build environment;
- `install_csopencvcuda_build_dependencies()`: adds the pipeline steps that
replicate the csopencvcuda build environment (apt packages, CUDA and cuDNN,
numpy) and downloads the precompiled build dependencies (eigen3) via the
standard provider mechanism. It is called by `csopencvcuda_project.py`
(producer) and by `auto_install_csorchestrator_managed_libraries()`
(consumers pulling the precompiled OpenCV archives);
- `opencv_mapping()`: maps a consumer execution context to the context the
OpenCV archives are built with.
"""

from copy import deepcopy
from pathlib import Path

from csorchestrator.application.recipes.manifest_github import (
    ManifestGithub,
    create_steps_to_get_libs_from_manifest,
    resolve_libs_deps_and_install_dependencies,
)
from csorchestrator.domain.context.context_compiler_generator import (
    Compiler,
    ContextCompilerGenerator,
    GeneratorWithType,
)
from csorchestrator.domain.context.context_os_architecture import (
    OS,
    UBUNTU_STRING_PREFIX,
    Architecture,
    UbuntuVersions,
)
from csorchestrator.domain.context.context_os_architecture_compiler_generator import (
    ContextOsArchitectureCompilerGenerator,
)
from csorchestrator.domain.orchestrator.orchestrator import Orchestrator
from csorchestrator.foundation.core.report import Report
from csorchestrator.frontend.local_execution.step_utils import (
    StepExecuteOnlyOn,
    StepExecuteOnlyOncePerMatrix,
)
from csorchestrator.frontend.step.step_custom_command import (
    StepBashScriptCommand,
    StepInstallAptPackages,
    StepWinPSCommand,
)
from csorchestrator.frontend.step.step_get_precompiled_lib_github import (
    MappingFunction,
    StepGetPrecompiledLibGithub,
)
from csorchestrator.portable.release_manifest import ReleaseManifest

# ============================================================================
# Toolchain versions used by the build environment.
# The install scripts below are parameterized on these constants.
# ============================================================================

# CUDA toolkit (local-repo install method, see install scripts below)
CUDA_VERSION = "13.3.1"  # full version, e.g. 13.3.1
CUDA_VERSION_DIR = "13.3"  # install dir suffix: /usr/local/cuda-13.3, CUDA\v13.3
CUDA_PACKAGE_VERSION = "13-3"  # apt package suffix: cuda-toolkit-13-3
CUDA_LOCAL_DEB_SUFFIX = "610.43.02-1"  # NVIDIA local-repo .deb build suffix

# cuDNN (local-repo install method on Linux, installer exe on Windows)
CUDNN_CUDA_MAJOR = "13"  # apt packages: libcudnn9-cuda-13 / libcudnn9-dev-cuda-13
CUDNN_LINUX_VERSION = "9.24.0"  # Linux local-repo version
CUDNN_WINDOWS_VERSION = "9.23.2"  # Windows installer version
CUDNN_WINDOWS_ROOT_VERSION = "v9.23"  # Windows install root: CUDNN\v9.23
CUDNN_WINDOWS_CUDA_SUBDIR = "12.9"  # per-CUDA-version layout inside the win root

# ============================================================================
# External provider of precompiled build dependencies.
#
# eigen3 is a build dependency of the OpenCV configuration (and of consumers
# replicating the build environment): it is downloaded precompiled from the
# third_party_base_libs GitHub releases, through the standard provider
# mechanism (ManifestGithub description + resolve_libs_deps_and_install_dependencies).
# ============================================================================

THIRD_PARTY_BASE_LIBS_PROVIDER = ManifestGithub(
    base_url=StepGetPrecompiledLibGithub.GITHUB_BASE_URL_HTTPS,
    org="cscosine",
    git_repo="third_party_base_libs",
    project_name="third_party_base_libs",
    project_version="0.1.0",
    release_tag="v0.1.0-rc3",
)


# First-party library list (mirrors csfoundation_config.py pattern).
# csopencvcuda builds OpenCV; eigen3 is a precompiled build dependency of
# OpenCV and is downloaded via the standard provider mechanism.
LIBRARY_LIST = ["opencv"]

# project internal dependencies
LIBRARY_DEPENDENCIES: dict[str, list[str]] = {
    "opencv": [],
}

# project additional dependencies for `dev`
LIBRARY_DEPENDENCIES_DEV: dict[str, list[str]] = {}


def third_party_base_libs_mapping(
    context: ContextOsArchitectureCompilerGenerator,
) -> ContextOsArchitectureCompilerGenerator | None:
    """Remap the context when downloading precompiled third-party base libs.

    OpenCV is built with the Ninja single-config generator, while the
    precompiled eigen archives published by third_party_base_libs are built
    with the ninja-multiconfig Linux x64 context: remap on Linux so that the
    published archive is found. Windows contexts are already the published
    (MSVC multi-config) ones and are left unchanged.
    """
    if context.context_os_architecture.os == OS.LINUX:
        new_context = deepcopy(context)
        new_context.context_compiler_generator = ContextCompilerGenerator(
            compiler_family=Compiler.GCC,
            compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
            build_generator=GeneratorWithType.NINJA_MULTI,
        )
        return new_context
    return deepcopy(context)


# ============================================================================
# Ubuntu apt packages required to build OpenCV.
#
# NOTE: entries must be EXPLICIT package names (no shell wildcards): the
# install step (StepInstallAptPackages) checks presence with `dpkg -s` and a
# wildcard would be always reported as missing, forcing an apt install (and an
# `apt update`) at every run.
# ============================================================================

APT_PACKAGES = """
libavcodec-dev
libavformat-dev
libdc1394-dev
libgstreamer-plugins-base1.0-dev
libgstreamer1.0-dev
libgtk-3-dev
libjpeg-dev
libopenexr-dev
libpng-dev
libswscale-dev
libtbb-dev
libtbb12
libtiff-dev
libwebp-dev
pkg-config
python3-dev
python3-numpy
python3-pip
"""

# ROLLBACK: previous package list, kept verbatim for an easy restore if
# something breaks. Differences with respect to APT_PACKAGES:
# - "gstreamer1.0*" wildcard removed: `dpkg -s` cannot check it, so it was
#   re-installed at every run; runtime gstreamer plugins are resolved by apt
#   from the -dev packages when they are really needed.
# - "ubuntu-restricted-extras" removed: a meta-package pulling large unrelated
#   payloads (mscorefonts etc.) with interactive EULA handling; not required to
#   build OpenCV.
# APT_PACKAGES_OLD = """
# gstreamer1.0*
# libavcodec-dev
# libavformat-dev
# libdc1394-dev
# libgstreamer-plugins-base1.0-dev
# libgstreamer1.0-dev
# libgtk-3-dev
# libjpeg-dev
# libopenexr-dev
# libpng-dev
# libswscale-dev
# libtbb-dev
# libtbb12
# libtiff-dev
# libwebp-dev
# pkg-config
# python3-dev
# python3-numpy
# python3-pip
# ubuntu-restricted-extras
# """


def get_apt_packages_list() -> list[str]:
    return APT_PACKAGES.split()


# ============================================================================
# Linux install scripts (bash).
#
# Every script is IDEMPOTENT: it checks whether the component is already
# installed and skips the (potentially multi-GB) download/install when present.
# __TOKEN__ placeholders are replaced by the builder functions below, so that
# version knowledge stays in the constants at the top of this file.
# ============================================================================

_PREACCEPT_MS_FONTS_SCRIPT_LINUX = r"""
set -euo pipefail

# Pre-accept the Microsoft Core Fonts EULA so installation can run
# non-interactively. No-op when the package is already installed.
if dpkg -s ttf-mscorefonts-installer >/dev/null 2>&1; then
  echo "ttf-mscorefonts-installer already installed, skipping."
  exit 0
fi

sudo apt-get update
echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | sudo debconf-set-selections
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ttf-mscorefonts-installer
"""

_REMOVE_LIBUNWIND_SCRIPT_LINUX = r"""
set -euo pipefail

# Remove libunwind causing errors on ubuntu 22.04. No-op when not installed.
packages=$(dpkg -l 'libunwind*' 2>/dev/null | awk '$1 == "ii" {print $2}' || true)
if [ -z "${packages}" ]; then
  echo "libunwind not installed, nothing to remove."
  exit 0
fi

echo "Removing: ${packages}"
# shellcheck disable=SC2086
sudo apt-get remove -y ${packages}
"""

_INSTALL_CUDA_SCRIPT_LINUX = r"""
set -euo pipefail

# Idempotent CUDA toolkit install: skip everything when nvcc is already present.
if [ -x /usr/local/cuda-__CUDA_VERSION_DIR__/bin/nvcc ]; then
  echo "CUDA __CUDA_VERSION__ already installed (/usr/local/cuda-__CUDA_VERSION_DIR__/bin/nvcc present), skipping."
  exit 0
fi

# apt pin, install only when not already configured
if [ ! -f /etc/apt/preferences.d/cuda-repository-pin-600 ]; then
  wget -q __CUDA_PIN_URL__
  sudo mv cuda-__CUDA_REPO_ID__.pin /etc/apt/preferences.d/cuda-repository-pin-600
fi

# local repository package (contains the multi-GB payload): install only when missing
if ! dpkg -s cuda-repo-__CUDA_REPO_PACKAGE__ >/dev/null 2>&1; then
  wget -q __CUDA_LOCAL_DEB_URL__
  sudo dpkg -i __CUDA_LOCAL_DEB__
  sudo cp /var/cuda-repo-__CUDA_REPO_PACKAGE__/cuda-*-keyring.gpg /usr/share/keyrings/
  rm -f __CUDA_LOCAL_DEB__
fi

sudo apt-get update
sudo apt-get -y install cuda-toolkit-__CUDA_PACKAGE_VERSION__
"""

_INSTALL_CUDNN_SCRIPT_LINUX = r"""
set -euo pipefail

# Idempotent cuDNN install: skip everything when the dev package is present.
if dpkg -s libcudnn9-dev-cuda-__CUDNN_CUDA_MAJOR__ >/dev/null 2>&1; then
  echo "cuDNN for CUDA __CUDNN_CUDA_MAJOR__ already installed, skipping."
  exit 0
fi

# local repository package: install only when missing
if ! dpkg -s cudnn-local-repo-__CUDNN_REPO_PACKAGE__ >/dev/null 2>&1; then
  wget -q __CUDNN_LOCAL_DEB_URL__
  sudo dpkg -i __CUDNN_LOCAL_DEB__
  sudo cp /var/cudnn-local-repo-__CUDNN_REPO_PACKAGE__/cudnn-*-keyring.gpg /usr/share/keyrings/
  rm -f __CUDNN_LOCAL_DEB__
fi

sudo apt-get update
sudo apt-get -y install libcudnn9-cuda-__CUDNN_CUDA_MAJOR__ libcudnn9-dev-cuda-__CUDNN_CUDA_MAJOR__
"""

_VERIFY_CUDA_SCRIPT_LINUX = r"""
set -euo pipefail

# Cheap post-conditions of the CUDA install steps.
ls /usr/local/cuda/lib64/stubs/libcuda.so
/usr/local/cuda/bin/nvcc --version
"""


def _fill_tokens(template: str, tokens: dict[str, str]) -> str:
    result = template
    for key, value in tokens.items():
        result = result.replace(f"__{key}__", value)
    return result


def install_cuda_script_linux(ubuntu_number: str) -> str:
    """CUDA toolkit install script for Ubuntu.

    ubuntu_number: ubuntu version as used in the NVIDIA repo ids, e.g. "2204".
    """
    repo_id = f"ubuntu{ubuntu_number}"
    repo_package = f"{repo_id}-{CUDA_PACKAGE_VERSION}-local"
    deb_name = f"cuda-repo-{repo_package}_{CUDA_VERSION}-{CUDA_LOCAL_DEB_SUFFIX}_amd64.deb"
    return _fill_tokens(
        _INSTALL_CUDA_SCRIPT_LINUX,
        {
            "CUDA_VERSION": CUDA_VERSION,
            "CUDA_VERSION_DIR": CUDA_VERSION_DIR,
            "CUDA_PACKAGE_VERSION": CUDA_PACKAGE_VERSION,
            "CUDA_REPO_ID": repo_id,
            "CUDA_REPO_PACKAGE": repo_package,
            "CUDA_PIN_URL": (
                f"https://developer.download.nvidia.com/compute/cuda/repos/{repo_id}/x86_64/cuda-{repo_id}.pin"
            ),
            "CUDA_LOCAL_DEB": deb_name,
            "CUDA_LOCAL_DEB_URL": (
                f"https://developer.download.nvidia.com/compute/cuda/{CUDA_VERSION}/local_installers/{deb_name}"
            ),
        },
    )


def install_cudnn_script_linux(ubuntu_number: str) -> str:
    """cuDNN install script for Ubuntu.

    ubuntu_number: ubuntu version as used in the NVIDIA repo ids, e.g. "2204".
    """
    repo_package = f"ubuntu{ubuntu_number}-{CUDNN_LINUX_VERSION}"
    deb_name = f"cudnn-local-repo-{repo_package}_1.0-1_amd64.deb"
    return _fill_tokens(
        _INSTALL_CUDNN_SCRIPT_LINUX,
        {
            "CUDNN_CUDA_MAJOR": CUDNN_CUDA_MAJOR,
            "CUDNN_REPO_PACKAGE": repo_package,
            "CUDNN_LOCAL_DEB": deb_name,
            "CUDNN_LOCAL_DEB_URL": (
                f"https://developer.download.nvidia.com/compute/cudnn/{CUDNN_LINUX_VERSION}/local_installers/{deb_name}"
            ),
        },
    )


# ============================================================================
# Windows install scripts (PowerShell).
#
# Same idempotency policy as the Linux scripts: check for presence first and
# skip the download/install when the component is already in place.
# ============================================================================

_INSTALL_NUMPY_SCRIPT_WINDOWS = r"""
$ErrorActionPreference = "Stop"

# Idempotent numpy install: skip when numpy is importable.
python -c "import numpy" 2>$null
if ($LASTEXITCODE -eq 0) {
  Write-Host "numpy already installed, skipping."
  exit 0
}

python -m pip install --upgrade pip
python -m pip install numpy
"""

_INSTALL_CUDA_SCRIPT_WINDOWS = r"""
$ErrorActionPreference = "Stop"

# Idempotent CUDA toolkit install: skip everything when nvcc is already present.
$nvcc = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/__CUDA_VERSION_DIR__/bin/nvcc.exe"
if (Test-Path $nvcc) {
  Write-Host "CUDA __CUDA_VERSION__ already installed ($nvcc present), skipping."
  exit 0
}

$installer = "$env:TEMP/__CUDA_INSTALLER__"

Write-Host "Download CUDA installer..."
$download = [System.Diagnostics.Stopwatch]::StartNew()
curl.exe -L --fail --progress-bar -o $installer "__CUDA_URL__"
if ($LASTEXITCODE -ne 0) {
  throw "CUDA download failed with exit code $LASTEXITCODE"
}
$download.Stop()
Write-Host ("Download took {0:mm\:ss}" -f $download.Elapsed)

$install = [System.Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $installer -ArgumentList "-s" -Wait -PassThru
$install.Stop()
Write-Host ("Installation took {0:mm\:ss}" -f $install.Elapsed)

if ($p.ExitCode -ne 0) {
  throw "Installer failed with exit code $($p.ExitCode)"
}

Remove-Item -Path $installer -ErrorAction SilentlyContinue
"""

_VERIFY_CUDA_SCRIPT_WINDOWS = r"""
$nvcc = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/__CUDA_VERSION_DIR__/bin/nvcc.exe"

if (!(Test-Path $nvcc)) {
  throw "nvcc not found: $nvcc"
}

& $nvcc --version
"""

_INSTALL_CUDNN_SCRIPT_WINDOWS = r"""
$ErrorActionPreference = "Stop"

# Idempotent cuDNN install: skip everything when the install root is present.
$root = "C:/Program Files/NVIDIA/CUDNN/__CUDNN_WINDOWS_ROOT_VERSION__"
if (Test-Path $root) {
  Write-Host "cuDNN already installed ($root present), skipping."
  exit 0
}

$installer = "$env:TEMP/__CUDNN_INSTALLER__"

Write-Host "Downloading cuDNN installer..."
$download = [System.Diagnostics.Stopwatch]::StartNew()
curl.exe -L --fail --progress-bar -o $installer "__CUDNN_URL__"
if ($LASTEXITCODE -ne 0) {
  throw "cuDNN download failed with exit code $LASTEXITCODE"
}
$download.Stop()
Write-Host ("Download took {0:mm\:ss}" -f $download.Elapsed)

$install = [System.Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $installer -ArgumentList "-s" -Wait -PassThru
$install.Stop()
Write-Host ("Installation took {0:mm\:ss}" -f $install.Elapsed)

if ($p.ExitCode -ne 0) {
  throw "Installer failed with exit code $($p.ExitCode)"
}

Remove-Item -Path $installer -ErrorAction SilentlyContinue
"""

_VERIFY_CUDNN_SCRIPT_WINDOWS = r"""
$root = "C:/Program Files/NVIDIA/CUDNN/__CUDNN_WINDOWS_ROOT_VERSION__"

# Print directory tree first (directories only view via tree)
Write-Host "cuDNN directory tree ($root):"
cmd /c "tree `"$root`" /a"
Write-Host ""

$dllPath = Join-Path $root "bin/__CUDNN_WINDOWS_CUDA_SUBDIR__/x64"
$includePath = Join-Path $root "include/__CUDNN_WINDOWS_CUDA_SUBDIR__"
$libFile = Join-Path $root "lib/__CUDNN_WINDOWS_CUDA_SUBDIR__/x64/cudnn.lib"

# Strict existence checks
if (-not (Test-Path $dllPath)) {
  throw "cuDNN DLL directory not found: $dllPath"
}

if (-not (Test-Path $includePath)) {
  throw "cuDNN include directory not found: $includePath"
}

if (-not (Test-Path $libFile)) {
  throw "cuDNN library file not found: $libFile"
}

# List DLLs strictly from target folder
$dlls = Get-ChildItem -Path $dllPath -Filter "cudnn*.dll" -ErrorAction Stop

if (-not $dlls) {
  throw "No cuDNN DLLs found in $dllPath"
}

Write-Host ""
Write-Host "Found cuDNN DLLs in ${dllPath}:"
$dlls | Select-Object -ExpandProperty FullName

Write-Host ""
Write-Host "Include path verified: ${includePath}"
Write-Host "Library verified: ${libFile}"
"""


def install_cuda_script_windows() -> str:
    installer = f"cuda_{CUDA_VERSION}_windows.exe"
    return _fill_tokens(
        _INSTALL_CUDA_SCRIPT_WINDOWS,
        {
            "CUDA_VERSION": CUDA_VERSION,
            "CUDA_VERSION_DIR": CUDA_VERSION_DIR,
            "CUDA_INSTALLER": installer,
            "CUDA_URL": (
                f"https://developer.download.nvidia.com/compute/cuda/{CUDA_VERSION}/local_installers/{installer}"
            ),
        },
    )


def verify_cuda_script_windows() -> str:
    return _fill_tokens(_VERIFY_CUDA_SCRIPT_WINDOWS, {"CUDA_VERSION_DIR": CUDA_VERSION_DIR})


def install_cudnn_script_windows() -> str:
    installer = f"cudnn_{CUDNN_WINDOWS_VERSION}_windows_x86_64.exe"
    return _fill_tokens(
        _INSTALL_CUDNN_SCRIPT_WINDOWS,
        {
            "CUDNN_WINDOWS_ROOT_VERSION": CUDNN_WINDOWS_ROOT_VERSION,
            "CUDNN_INSTALLER": installer,
            "CUDNN_URL": (
                "https://developer.download.nvidia.com/compute/cudnn/"
                f"{CUDNN_WINDOWS_VERSION}/local_installers/{installer}"
            ),
        },
    )


def verify_cudnn_script_windows() -> str:
    return _fill_tokens(
        _VERIFY_CUDNN_SCRIPT_WINDOWS,
        {
            "CUDNN_WINDOWS_ROOT_VERSION": CUDNN_WINDOWS_ROOT_VERSION,
            "CUDNN_WINDOWS_CUDA_SUBDIR": CUDNN_WINDOWS_CUDA_SUBDIR,
        },
    )


# ============================================================================
# Build environment installation
# ============================================================================

# ubuntu_version -> ubuntu number as used in the NVIDIA repository ids
_UBUNTU_NUMBER_BY_VERSION: dict[str, str] = {
    UbuntuVersions.UBUNTU_22_04.value: "2204",
    UbuntuVersions.UBUNTU_24_04.value: "2404",
}


def install_csopencvcuda_build_dependencies(
    orchestrator: Orchestrator,
    base_libs_dir: Path,
    dependencies_config_path: Path,
    dev: bool,
    download_dependencies_manifest_and_bundle: bool,
    mapping_function: MappingFunction,
    phase_name_suffix: str,
    required_libs: list[str] | None = None,
) -> Report:
    """Add the steps that replicate the csopencvcuda build environment.

    Called by:
    - `csopencvcuda_project.py` when building OpenCV (producer);
    - `auto_install_csorchestrator_managed_libraries()` when the precompiled
      OpenCV archives are consumed and the environment must be replicated.

    Includes the download of precompiled build dependencies (eigen3 from the
    third_party_base_libs provider) via the standard provider mechanism, which
    downloads the manifest and bundle into ``dependencies_config_path``.

    All steps are idempotent: already-installed components are detected and
    skipped (no multi-GB downloads when CUDA/cuDNN are already present).
    """
    report = Report()

    p = orchestrator.create_phase("Install Build Dependencies (csopencvcuda)")

    # ------------------------------ LINUX ------------------------------
    p.add_step(
        StepBashScriptCommand(
            name="Pre-accept MS fonts EULA (Linux)",
            description="pre-accept the Microsoft Core Fonts EULA for non-interactive installs",
            cmd=_PREACCEPT_MS_FONTS_SCRIPT_LINUX.strip().splitlines(),
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.LINUX, version_starts_with=UBUNTU_STRING_PREFIX))
    )

    p.add_step(
        StepBashScriptCommand(
            name="Remove libunwind (Ubuntu 22.04)",
            description="remove libunwind causing errors on ubuntu 22.04",
            cmd=_REMOVE_LIBUNWIND_SCRIPT_LINUX.strip().splitlines(),
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(
            StepExecuteOnlyOn(
                os=OS.LINUX,
                version_starts_with=UbuntuVersions.UBUNTU_22_04.value,
            )
        )
    )

    p.add_step(
        StepInstallAptPackages(
            name="Install apt packages (Linux)",
            description="install apt packages if not already installed in the system",
            packages=get_apt_packages_list(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.LINUX, version_starts_with=UBUNTU_STRING_PREFIX))
    )

    for ubuntu_version, ubuntu_number in _UBUNTU_NUMBER_BY_VERSION.items():
        p.add_step(
            StepBashScriptCommand(
                name=f"Install CUDA (Linux {ubuntu_version})",
                description="install the CUDA toolkit if not already installed",
                cmd=install_cuda_script_linux(ubuntu_number).strip().splitlines(),
            )
            .add_extra(StepExecuteOnlyOncePerMatrix())
            .add_extra(
                StepExecuteOnlyOn(
                    os=OS.LINUX,
                    version_starts_with=ubuntu_version,
                    arch=Architecture.X64,
                )
            )
        )

        p.add_step(
            StepBashScriptCommand(
                name=f"Install cuDNN (Linux {ubuntu_version})",
                description="install cuDNN if not already installed",
                cmd=install_cudnn_script_linux(ubuntu_number).strip().splitlines(),
            )
            .add_extra(StepExecuteOnlyOncePerMatrix())
            .add_extra(
                StepExecuteOnlyOn(
                    os=OS.LINUX,
                    version_starts_with=ubuntu_version,
                    arch=Architecture.X64,
                )
            )
        )

    p.add_step(
        StepBashScriptCommand(
            name="Verify CUDA (Linux)",
            description="verify the CUDA stub library and nvcc exist",
            cmd=_VERIFY_CUDA_SCRIPT_LINUX.strip().splitlines(),
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.LINUX, version_starts_with=UBUNTU_STRING_PREFIX))
    )

    # ------------------------------ WINDOWS -----------------------------
    p.add_step(
        StepWinPSCommand(
            name="Install numpy (Windows)",
            description="install numpy if not already installed",
            cmd=_INSTALL_NUMPY_SCRIPT_WINDOWS.strip().splitlines(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.WINDOWS))
    )

    p.add_step(
        StepWinPSCommand(
            name="Install CUDA (Windows)",
            description="install the CUDA toolkit if not already installed",
            cmd=install_cuda_script_windows().strip().splitlines(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.WINDOWS))
    )

    p.add_step(
        StepWinPSCommand(
            name="Verify CUDA (Windows)",
            description="verify cuda installation",
            cmd=verify_cuda_script_windows().strip().splitlines(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.WINDOWS))
    )

    p.add_step(
        StepWinPSCommand(
            name="Install cuDNN (Windows)",
            description="install cuDNN if not already installed",
            cmd=install_cudnn_script_windows().strip().splitlines(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.WINDOWS))
    )

    p.add_step(
        StepWinPSCommand(
            name="Verify cuDNN (Windows)",
            description="verify cuDNN installation",
            cmd=verify_cudnn_script_windows().strip().splitlines(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.WINDOWS))
    )

    # ------------------- PRECOMPILED THIRD-PARTY BASE LIBS -------------------
    # eigen3: precompiled build dependency, downloaded via the standard
    # provider mechanism (resolve_libs_deps_and_install_dependencies) which
    # downloads the manifest+bundle into dependencies_config_path and triggers
    # the provider's auto_install step.
    report.append_report(
        resolve_libs_deps_and_install_dependencies(
            orchestrator=orchestrator,
            base_libs_dir=base_libs_dir,
            dependencies_config_path=dependencies_config_path,
            dev=dev,
            download_dependencies_manifest_and_bundle=download_dependencies_manifest_and_bundle,
            mapping_function=mapping_function,
            required_libs=required_libs,
            full_library_list=LIBRARY_LIST,
            library_dependencies=LIBRARY_DEPENDENCIES,
            library_dependencies_dev=LIBRARY_DEPENDENCIES_DEV,
            external_library_dependencies={
                THIRD_PARTY_BASE_LIBS_PROVIDER.project_name: {
                    "opencv": ["eigen3"],
                },
            },
            external_library_dependencies_dev={
                THIRD_PARTY_BASE_LIBS_PROVIDER.project_name: {},
            },
            external_provides_description=[THIRD_PARTY_BASE_LIBS_PROVIDER],
            provider_mapping_function={},
            phase_name_suffix=phase_name_suffix,
        )
    )

    return report


# ============================================================================
# Context mapping for consumers of the precompiled OpenCV archives
# ============================================================================


def opencv_mapping(
    context: ContextOsArchitectureCompilerGenerator,
) -> ContextOsArchitectureCompilerGenerator | None:
    """Map a consumer execution context to the csopencvcuda archive context.

    Archives are published for (see utils/build_matrix.py):
    - Linux x64 (ubuntu22.04 / ubuntu24.04): GCC, Ninja single-config;
    - Windows x64: MSVC, Visual Studio 2026 multi-config (archives for the
      2022 generator are also published, but the 2026 variant is the one
      resolved for consumers).

    Contexts that are not built (e.g. Linux arm64) return None.
    """
    os_arch = context.context_os_architecture

    if os_arch.os == OS.LINUX and os_arch.architecture == Architecture.X64:
        new_context = deepcopy(context)
        new_context.context_compiler_generator = ContextCompilerGenerator(
            compiler_family=Compiler.GCC,
            compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
            build_generator=GeneratorWithType.NINJA,
        )
        return new_context

    if os_arch.os == OS.WINDOWS and os_arch.architecture == Architecture.X64:
        new_context = deepcopy(context)
        new_context.context_compiler_generator = ContextCompilerGenerator(
            compiler_family=Compiler.MSVC,
            compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
            build_generator=GeneratorWithType.MSVC_18_2026,
        )
        return new_context

    return None


def auto_install_csorchestrator_managed_libraries(
    orchestrator: Orchestrator,
    base_libs_dir: Path,
    manifest_description: ManifestGithub,
    manifest_loaded: ReleaseManifest,
    dependencies_config_path: Path,
    mapping_function: MappingFunction,
    download_dependencies_manifest_and_bundle: bool,
    phase_name_suffix: str,
    required_libs: list[str] | None = None,
) -> Report:
    report = Report()

    # replicate the csopencvcuda build environment (CUDA/cuDNN/apt packages)
    # and precompiled build dependencies (eigen3) in the consumer pipeline:
    # customers need the same toolchain to use the precompiled OpenCV archives
    report.append_report(
        install_csopencvcuda_build_dependencies(
            orchestrator=orchestrator,
            base_libs_dir=base_libs_dir,
            dependencies_config_path=dependencies_config_path,
            dev=False,
            download_dependencies_manifest_and_bundle=download_dependencies_manifest_and_bundle,
            mapping_function=mapping_function,
            phase_name_suffix=phase_name_suffix,
            required_libs=required_libs,
        )
    )

    report.append_report(
        create_steps_to_get_libs_from_manifest(
            orchestrator=orchestrator,
            manifest_description=manifest_description,
            manifest_loaded=manifest_loaded,
            base_libs_dir=base_libs_dir,
            lib_name_list=required_libs,
            mapping_function=mapping_function,
            phase_name=phase_name_suffix,
            dev=False,
        )
    )

    return report
