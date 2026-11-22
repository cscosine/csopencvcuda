# csopencvcuda

Automated cross-platform build system and CI pipeline recipe for **OpenCV with CUDA support** (targeting **v5.1.0**), powered by [**csorchestrator**](https://github.com/cscosine/csorchestrator).

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

<!-- cs-template:begin (this block is owned by cs-project-template: do not edit; the rest of the file is the project's) -->
## Getting started

Requires Python 3.11 or newer and Git.

```bash
./setup.sh                    # Windows: .\setup.ps1
source .venv/bin/activate     # Windows: .\.venv\Scripts\Activate.ps1
```

`setup.sh` creates `.venv`, installs the project with its development tools and csorchestrator, and installs the
pre-commit hooks.

csorchestrator: `setup.sh` installs the pinned version (v0.1.0). Another one:
`./setup.sh --csorchestrator=<tag or branch>`; a local clone, editable: `./setup.sh --csorchestrator=../csorchestrator`
(Windows: `.\setup.ps1 -CsOrchestrator <...>`).

Run the recipe locally, regenerate the GitHub workflow after changing it:

```bash
python csopencvcuda_project.py
python csopencvcuda_project.py generate-github-workflow
```

Generated files, never edited by hand:

| Path | Made by | |
|---|---|---|
| `.github/workflows/csopencvcuda.yml` | `csopencvcuda_project.py generate-github-workflow` | Edit the recipe, then regenerate |
| `csorchestratorsdk/` | csorchestrator, at the same command | The release-manifest helpers the CI runs, without installing csorchestrator |
| `dependencies/` | csorchestrator, at the same command | The manifests and recipes of the releases this project builds on |
| `workspace/` *(git-ignored)* | a local run of `csopencvcuda_project.py` | Sources, builds, installs, deploy archives; delete it to start clean |

Checks and tests:

```bash
pre-commit run --all-files
pytest                        # --run-all: every test, as CI; --run=<marker>: an opt-in group (tests/conftest.py)
```

The shared files (setup, checks, CI, agent rules) come from
[cs-project-template](https://github.com/cscosine/cs-project-template); to bring them to its latest version, on a
branch: `copier update --defaults`.
<!-- cs-template:end -->

## Overview

Building OpenCV from source with CUDA support across multiple platforms is complex and error-prone (CUDA/cuDNN toolkits, image codec dev packages, GPU architectures). **csopencvcuda** defines a declarative build and packaging recipe in Python using the `csorchestrator` framework:

- The build pipeline, dependencies, and installation steps are defined in Python code.
- Cross-platform CI workflows (e.g. [`.github/workflows/csopencvcuda.yml`](.github/workflows/csopencvcuda.yml)) are automatically generated.
- Build artifacts, manifests, and release archives (`.tar.gz` bundles) are assembled consistently across environments.

---

## Architecture & Build Pipeline

The core build recipe is defined in [`csopencvcuda_project.py`](csopencvcuda_project.py) and executed across the matrix defined in [`utils/build_matrix.py`](utils/build_matrix.py).

### Version Alignment

The project version (`5.1.0`, tracking the OpenCV release being built) is defined in [`csopencvcuda_project.py`](csopencvcuda_project.py) (`OPENCV_VERSION`) and mirrored in [`pyproject.toml`](pyproject.toml) — keep the two aligned when bumping the version.

### Execution Phases

1. **Repos Update**:
   - Downloads the csCMake release package pinned in [`csopencvcuda_project.py`](csopencvcuda_project.py) (`cscmake_version`, e.g. `1.0.0`) and unpacks it into `workspace/csCMake`, where the presets of the OpenCV fork find it (sibling layout).
   - Shallow clones (`depth=1`) of `cscosine/opencv` and `cscosine/opencv_contrib` at the tags configured in [`csopencvcuda_project.py`](csopencvcuda_project.py) (`v5.1.0-cuda.1`: the `cuda` variant of both forks, see their `cscosine/README.md`; releases are tagged after the fork tag they ship, `v5.1.0-cuda.1-rc1`, `v5.1.0-cuda.1`).
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

---

## Local Execution Policy (Build Guard)

**Do NOT run full local builds** of OpenCV+CUDA (executing all phases of `./csopencvcuda_project.py`): compiling OpenCV with CUDA requires large downloads, significant disk space and long build times. Only run unit tests (`pytest`) or workflow re-generation when checking local configuration logic.

---

## License

This project is licensed under the [MIT License](LICENSE).
