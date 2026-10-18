# csopencvcuda

Automated cross-platform build system and CI pipeline recipe for **OpenCV with CUDA support** (targeting **v5.0.0**), powered by [**csorchestrator**](https://github.com/cscosine/csorchestrator).

> [!CAUTION]
> ## ⚠️ Known Build Limitations — Read Before Building
>
> ### 1. Visual Studio 2026 (VS 2026) is NOT built — VS 2022 only
> VS 2026 (`Visual Studio 18 2026`, runner `windows-2025-vs2026`) was removed
> from the build matrix in [`utils/build_matrix.py`](utils/build_matrix.py):
> the remote (GitHub Actions) build **fails downloading cuDNN** on that runner.
> Only `Visual Studio 17 2022` on `windows-2022` is built, and `opencv_mapping()`
> in [`csopencvcuda_config.py`](csopencvcuda_config.py) resolves Windows consumers
> to `MSVC_17_2022`.
>
> ### 2. Local Ubuntu 22.04 build needs an explicit CUDA path, CI does not
> The OpenCV CMake preset (csCMake) as committed works on GitHub CI but
> **does NOT configure locally on Ubuntu 22.04** (CUDA not found). Setting
> explicitly:
> ```cmake
> CMAKE_CUDA_COMPILER="/usr/local/cuda-13.3/bin/nvcc"
> CUDA_TOOLKIT_ROOT_DIR="/usr/local/cuda-13.3"
> ```
> fixes the local configure but **breaks the remote (CI) build**, so it is
> intentionally NOT committed. Local root cause (observed): `/usr/bin/nvcc`
> is a stale CUDA 11.5 while the real CUDA 13.3 toolkit installed by the recipe
> lives in `/usr/local/cuda-13.3/bin/nvcc` — CMake's default discovery picks the
> wrong one locally, whereas clean CI runners resolve correctly. Ubuntu 24.04
> local behavior not yet tested.
> See [Local Execution Policy](#local-execution-policy-build-guard): full local
> OpenCV+CUDA builds are discouraged; use `pytest` or workflow re-generation
> for local checks.

---

## Getting Started

### Prerequisites

* Python `>= 3.11`
* Git
* [csorchestrator](https://github.com/cscosine/csorchestrator) cloned as a peer directory (`../csorchestrator`)

### Environment Setup

Bootstrap the local virtual environment, install dev dependencies, link `csorchestrator` in editable mode, and install git hooks:

**Linux / macOS:**
```bash
./setup.sh
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

### Running the Orchestrator Locally

Execute the orchestrator script to run pipeline steps locally:

```bash
./csopencvcuda_project.py
# or
python csopencvcuda_project.py
```

### Re-generating the GitHub Workflow

To re-generate the GitHub Actions CI workflow (`.github/workflows/csopencvcuda.yml`) from the definition in [`csopencvcuda_project.py`](csopencvcuda_project.py):

```bash
./csopencvcuda_project.py generate-github-workflow
# or
python csopencvcuda_project.py generate-github-workflow
```

### Development & Quality Checks

```bash
# Code formatting and linting
ruff check .
ruff format .

# Strict type checking
python -m mypy . --config-file=pyproject.toml

# Unit tests
pytest

# Run all pre-commit hooks
pre-commit run --all-files
```

---

## Overview

Building OpenCV from source with CUDA support across multiple platforms is complex and error-prone (CUDA/cuDNN toolkits, image codec dev packages, GPU architectures). **csopencvcuda** defines a declarative build and packaging recipe in Python using the `csorchestrator` framework:

- The build pipeline, dependencies, and installation steps are defined in Python code.
- Cross-platform CI workflows (e.g. [`.github/workflows/csopencvcuda.yml`](.github/workflows/csopencvcuda.yml)) are automatically generated.
- Build artifacts, manifests, and release archives (`.tar.gz` bundles) are assembled consistently across environments.

---

## Architecture & Build Pipeline

The core build recipe is defined in [`csopencvcuda_project.py`](csopencvcuda_project.py) and executed across the matrix defined in [`utils/build_matrix.py`](utils/build_matrix.py).

### Version Alignment

The project version (`5.0.0`, tracking the OpenCV release being built) is defined in [`csopencvcuda_project.py`](csopencvcuda_project.py) (`OPENCV_VERSION`) and mirrored in [`pyproject.toml`](pyproject.toml) — keep the two aligned when bumping the version.

### Execution Phases

1. **Repos Update**:
   - Shallow clones (`depth=1`) of `cscosine/csCMake`, `cscosine/opencv` and `cscosine/opencv_contrib` (branch `cs-main`).
2. **Install Build Dependencies (csopencvcuda)**:
   - All environment-replication steps: Microsoft fonts EULA pre-accept, libunwind removal (Ubuntu 22.04), apt dev packages, **CUDA and cuDNN toolkits**, numpy (Windows).
   - Precompiled `eigen3` downloaded from the [third_party_base_libs](https://github.com/cscosine/third_party_base_libs) provider (`ManifestGithub` + `StepGetPrecompiledLibGithub`).
   - Defined in [`csopencvcuda_config.py`](csopencvcuda_config.py) (`install_build_dependencies()`), so that consumers of the precompiled archives can replicate the exact same toolchain and dependencies.
   - **All steps are idempotent**: presence is checked first (e.g. `nvcc` on disk, `dpkg -s`), so already-installed CUDA/cuDNN (multi-GB downloads) are skipped.
3. **Configure-Build-Test-Install**:
   - Runs the csCMake CMake workflow presets on `workspace/opencv` for config `DEBUG_RELEASE` (single-config generators run debug+release, multi-config run debug-release).
   - On Windows, runs under PowerShell with a PATH sanitization prefix that removes MinGW/Strawberry entries conflicting with MSVC.
4. **Create and Upload Artifacts**:
   - Extracts package versions from the installed CMake config packages, creates `.tar.gz` archives, and uploads them as CI artifacts (released on tags).

### Build Matrix

Defined in [`utils/build_matrix.py`](utils/build_matrix.py):

| OS      | Arch | Compiler        | Generator                    |
|---------|------|-----------------|------------------------------|
| Linux   | x64  | GCC / CLANG     | Ninja (single-config)        |
| Windows | x64  | MSVC            | VS 2022 (multi)                |

Linux arm64 and non-MSVC Windows compilers are intentionally not built (OpenCV+CUDA).
VS 2026 was removed: remote build fails downloading cuDNN (see top notice).

---

## Consuming csopencvcuda

[`csopencvcuda_config.py`](csopencvcuda_config.py) is the canonical configuration shipped inside every release bundle (`additional_files_list`). Consuming projects import it from their `dependencies/` folder through the csorchestrator manifest mechanism (same pattern as `csqt6_config.py` / `third_party_base_libs_config.py`).

> [!IMPORTANT]
> `csopencvcuda_config.py` is intentionally **self-contained**: it imports only csorchestrator and the standard library, never project-local modules such as `utils.*`. The release bundle preserves relative paths, but consumers import the module from their own tree, so project-local imports would not resolve there.

When consumed, `auto_install_csorchestrator_managed_libraries()`:

1. adds `install_build_dependencies()` steps to the consumer pipeline (CUDA/cuDNN/apt environment replication);
2. adds the steps to download the precompiled OpenCV archives, using `opencv_mapping()` to resolve the archive matching the consumer context.

### Toolchain versions

CUDA/cuDNN versions are single-sourced in `csopencvcuda_config.py` constants (`CUDA_VERSION`, `CUDNN_LINUX_VERSION`, `CUDNN_WINDOWS_VERSION`, ...) and consumed by the parameterized install scripts.

---

## Project Layout

```
csopencvcuda/
├── csopencvcuda_project.py     # Core pipeline definition and phases
├── csopencvcuda_config.py      # Canonical config: deps + env install + mapping (included in release)
├── utils/
│   └── build_matrix.py         # OS, architecture, and generator matrix definitions
├── tests/
│   └── csopencvcuda/           # Unit tests for config mappings and build matrix
├── docs/notes/                 # Reference notes (CUDA install links, local config dumps)
└── .github/workflows/
    └── csopencvcuda.yml         # [Autogenerated] GitHub Actions CI workflow (emitted by csopencvcuda_project.py)
```

### Autogenerated Files Lifecycle

| Path | Origin / Trigger | Maintenance Policy |
|---|---|---|
| [`.github/workflows/csopencvcuda.yml`](.github/workflows/csopencvcuda.yml) | Autogenerated by running `./csopencvcuda_project.py generate-github-workflow`. | **Never edit manually.** Edit `csopencvcuda_project.py` or files in `utils/`, then re-run the generator command. |
| `workspace/` *(gitignored)* | Created at runtime when running `./csopencvcuda_project.py` locally. | Holds cloned sources, temporary build directories, and install outputs. Can be safely deleted to reset local state. |

---

## Local Execution Policy (Build Guard)

**Do NOT run full local builds** of OpenCV+CUDA (executing all phases of `./csopencvcuda_project.py`): compiling OpenCV with CUDA requires large downloads, significant disk space and long build times. Only run unit tests (`pytest`) or workflow re-generation when checking local configuration logic.

---

## License

This project is licensed under the [MIT License](LICENSE).
