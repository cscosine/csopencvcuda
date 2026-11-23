#!/usr/bin/env bash
# Owned by the project template (cs-project-template): change it there.
# Opens VS Code on this repository attached to one of its existing builds (made by csorchestrator, or by hand with a
# preset), in either csCMake layout:
#   standalone: <repository>/_csw/build/<variant>/<repository>[/<config>]        (a project with its own sources)
#   sibling:    <workspace>/build/<variant>/<repository>[/<config>]              (a library checked out by its project)
# Writes <build>/<repository>.code-workspace with the settings of that build (build folder, generator, configurations,
# IntelliSense engine, debugger), opens it with the README at "Working in VS Code", and prints the first-time steps.
# The settings shared by every build and OS are in .vscode/settings.json. Same logic on Windows: open-code.ps1.
# A repository with a venv (.venv: a project, a tool) gets it too: active in the shell that starts VS Code, and the
# Python interpreter of the window. C++ sources are a csCMake project (CMakeLists.txt and
# csCMakeProjectSetup.json); without them it opens the folder with the venv, before their first build a Python-only
# workspace file.
#
# Usage: ./open-code.sh [filter]
#   filter: a part of the build folder name or of the compiler path (gcc, clang, ...); needed when there are several
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
name="$(basename "$src")"
filter="${1:-}"

# VS Code: its `code` command on the PATH (the Linux packages and the Windows installer add it; macOS: command palette,
# "Shell Command: Install 'code' command in PATH"); without it, how to open the file by hand
open_in_code() { # <workspace file or folder> [code arguments...]
  if command -v code >/dev/null; then
    code "$@"
  else
    echo "VS Code's 'code' command is not on the PATH: open $1 by hand (File > Open Workspace from File)." >&2
  fi
}

# the venv of the repository, if any (made by setup.sh): Python, pytest, pre-commit, csorchestrator
venv_python=""
if [[ -f "$src/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$src/.venv/bin/activate"
  venv_python="$src/.venv/bin/python"
fi

open_folder_python_only() { # <reason>: the folder and its venv, no C++ build
  echo "$1: opening $name for Python only${venv_python:+ (venv $src/.venv)}." >&2
  open_in_code "$src"
  exit 0
}
[[ -f "$src/CMakeLists.txt" && -f "$src/csCMakeProjectSetup.json" ]] ||
  open_folder_python_only "No csCMake sources (CMakeLists.txt, csCMakeProjectSetup.json)"

# C++ sources not built yet: a Python-only workspace file (in the workspace root, git-ignored) where CMake Tools does not
# configure on its own (as the folder would, with a preset and without the dependencies of the recipe)
open_python_only_workspace() { # <reason>
  local file="$workspace_root/$name.code-workspace"
  mkdir -p "$workspace_root"
  cat >"$file" <<END_OF_WORKSPACE
{
  "folders": [{ "path": "$src", "name": "$name - Python only (no C++ build yet)" }],
  "settings": {
    "python.defaultInterpreterPath": "$venv_python",
    "cmake.useCMakePresets": "never",
    "cmake.configureOnOpen": false,
    "cmake.enableAutomaticKitScan": false,
    "clangd.enable": false
  }
}
END_OF_WORKSPACE
  echo "$1: opening $name for Python only (venv $src/.venv): $file" >&2
  echo "For C++: run the recipe first (python ${name}_project.py), then this script again." >&2
  open_in_code "$file"
  exit 0
}

cache_value() { # <cache> <variable>: its value in CMakeCache.txt
  sed -n "s/^$2:[A-Z]*=//p" "$1" | head -n 1
}

# where the builds are: the include of csCMakeProjectSetup.json, <csCMake>/presets/layout/<layout>.json, names csCMake;
# in the sibling and standalone layouts csCMake is <workspace root>/csCMake (${sourceParentDir} / ${sourceDir}
# expanded), in the env layouts (env*.json) the workspace root is CSCMAKE_WORKSPACE_ROOT; csCMake's presets build in
# <workspace root>/build. No folder name here: the project's file says it.
include="$(grep -o '"[^"]*/presets/layout/[A-Za-z0-9_-]*\.json"' "$src/csCMakeProjectSetup.json" 2>/dev/null | head -n 1 || true)"
include="${include//\"/}"
cscmake_dir="${include%/presets/layout/*}"
layout="${include##*/}"
workspace_root=""
case "$layout:$cscmake_dir" in
  env*) workspace_root="${CSCMAKE_WORKSPACE_ROOT:-}" ;;
  *:'${sourceDir}/'*/csCMake) workspace_root="$src/${cscmake_dir#'${sourceDir}/'}" ;;
  *:'${sourceParentDir}/'*/csCMake | *:'${sourceParentDir}/csCMake')
    workspace_root="$(dirname "$src")/${cscmake_dir#'${sourceParentDir}/'}"
    ;;
esac
workspace_root="${workspace_root%/csCMake}"
if [[ -z "$workspace_root" ]]; then
  echo "No workspace root for $name from the include of csCMakeProjectSetup.json ('${include:-none}'):" >&2
  echo "<root>/csCMake/presets/layout/<layout>.json under \${sourceDir} or \${sourceParentDir}, or an env layout with" >&2
  echo "CSCMAKE_WORKSPACE_ROOT set." >&2
  exit 1
fi
build_root="$workspace_root/build"

# the compiler family of a build, from the compiler CMake identified in it (CMakeFiles/<version>/CMakeCXXCompiler.cmake):
# gcc, clang, appleclang, msvc, clang-cl; the short build folder names say none of them
compiler_family() { # <build dir>
  local file id variant
  for file in "$1"/CMakeFiles/*/CMakeCXXCompiler.cmake; do
    [[ -f "$file" ]] || continue
    id="$(sed -n 's/^set(CMAKE_CXX_COMPILER_ID "\(.*\)")$/\1/p' "$file" | head -n 1)"
    variant="$(sed -n 's/^set(CMAKE_CXX_COMPILER_FRONTEND_VARIANT "\(.*\)")$/\1/p' "$file" | head -n 1)"
    case "$id:$variant" in
      GNU:*) echo gcc ;;
      Clang:MSVC) echo clang-cl ;;
      Clang:*) echo clang ;;
      AppleClang:*) echo appleclang ;;
      MSVC:*) echo msvc ;;
      *) echo "$id" ;;
    esac
    return 0
  done
}

# every build of this checkout: multi-config (<variant>/<name>) and single-config (<variant>/<name>/<config>)
builds=()
for root in "$build_root"; do
  for cache in "$root"/*/"$name"/CMakeCache.txt "$root"/*/"$name"/*/CMakeCache.txt; do
    [[ -f "$cache" ]] || continue
    [[ "$(cache_value "$cache" CMAKE_HOME_DIRECTORY)" == "$src" ]] || continue
    dir="$(dirname "$cache")"
    compiler="$(basename "$(cache_value "$cache" CMAKE_CXX_COMPILER)")"
    family="$(compiler_family "$dir")"
    if [[ -z "$filter" || "${dir#"$root"/}" == *"$filter"* || "$compiler" == *"$filter"* ||
      (-n "$family" && "$family" == *"$filter"*) ]]; then
      builds+=("$dir")
    fi
  done
done

if [[ ${#builds[@]} -eq 0 && -n "$venv_python" && -z "$filter" ]]; then
  open_python_only_workspace "No build of $name yet"
fi
if [[ ${#builds[@]} -eq 0 ]]; then
  echo "No build of $name${filter:+ matching '$filter'} in $build_root:" >&2
  echo "build it first (csorchestrator)." >&2
  exit 1
fi
if [[ ${#builds[@]} -gt 1 ]]; then
  echo "Several builds of $name: choose one with a filter (a part of the folder name or of the compiler)." >&2
  for dir in "${builds[@]}"; do echo "  $dir ($(compiler_family "$dir"))" >&2; done
  exit 1
fi

build="${builds[0]}"
cache="$build/CMakeCache.txt"
label="$(basename "$(dirname "$build")")"
[[ "$(basename "$(dirname "$build")")" == "$name" ]] && label="$(basename "$(dirname "$(dirname "$build")")")/$(basename "$build")"
generator="$(cache_value "$cache" CMAKE_GENERATOR)"
platform="$(cache_value "$cache" CMAKE_GENERATOR_PLATFORM)"
toolset="$(cache_value "$cache" CMAKE_GENERATOR_TOOLSET)"
# the cmake and ctest that made the build (VS Code may not have them on its PATH); a snap by its current revision
snap_current() { sed 's#^/snap/\([^/]*\)/[0-9][0-9]*/#/snap/\1/current/#'; }
cmake_path="$(cache_value "$cache" CMAKE_COMMAND | snap_current)"
ctest_path="$(cache_value "$cache" CMAKE_CTEST_COMMAND | snap_current)"
configurations="$(cache_value "$cache" CMAKE_CONFIGURATION_TYPES)"
[[ -n "$configurations" ]] || configurations="$(cache_value "$cache" CMAKE_BUILD_TYPE)"
[[ -n "$configurations" ]] || configurations="Debug"

# the build types offered by CMake Tools: the configurations of the build, Debug first when it has one
IFS=';' read -r -a configs <<<"$configurations"
default="${configs[0]}"
for c in "${configs[@]}"; do [[ "$c" == "Debug" ]] && default="Debug"; done
choices=""
for c in "${configs[@]}"; do
  choices+="${choices:+,}
          \"$c\": { \"short\": \"$c\", \"long\": \"the $c configuration\", \"buildType\": \"$c\" }"
done

# IntelliSense: clangd on the compile database (Ninja, Makefiles); Visual Studio and Xcode write none: cpptools fed by
# CMake Tools
if [[ "$generator" == Xcode || "$generator" == "Visual Studio"* ]]; then
  intellisense='"clangd.enable": false,
    "C_Cpp.intelliSenseEngine": "default",
    "C_Cpp.default.configurationProvider": "ms-vscode.cmake-tools",'
else
  intellisense="\"clangd.enable\": true,
    \"C_Cpp.intelliSenseEngine\": \"disabled\",
    \"clangd.arguments\": [\"--compile-commands-dir=$build\", \"--background-index\", \"--clang-tidy\", \"--header-insertion=never\"],"
fi
generator_extra=""
[[ -n "$venv_python" ]] && generator_extra+="
    \"python.defaultInterpreterPath\": \"$venv_python\","
[[ -n "$platform" ]] && generator_extra+="
    \"cmake.platform\": \"$platform\","
[[ -n "$toolset" ]] && generator_extra+="
    \"cmake.toolset\": \"$toolset\","

# a build with Catch2 tests: one more configuration, the launch target with a Catch2 test spec
catch2_launch=""
catch2_input=""
if [[ -n "$(cache_value "$cache" Catch2_DIR)" ]]; then
  catch2_launch=',
      {
        "name": "Debug the launch target (Catch2 test spec)",
        "type": "cppdbg",
        "request": "launch",
        "preLaunchTask": "CMake: build",
        "program": "${command:cmake.launchTargetPath}",
        "args": ["${input:catch2TestSpec}"],
        "cwd": "${workspaceFolder}",
        "MIMode": "gdb",
        "osx": { "MIMode": "lldb" },
        "setupCommands": [{ "text": "-enable-pretty-printing", "ignoreFailures": true }]
      }'
  catch2_input='
      {
        "id": "catch2TestSpec",
        "type": "promptString",
        "description": "Catch2 test spec: a test name (wildcards allowed), a [tag], or * for all",
        "default": "*"
      }'
fi

file="$build/$name.code-workspace"
new="$(mktemp)"
trap 'rm -f "$new"' EXIT
cat >"$new" <<EOF
{
  "folders": [{ "path": "$src", "name": "$name - $label" }],
  "settings": {
    "cmake.useCMakePresets": "never",
    "cmake.cmakePath": "$cmake_path",
    "cmake.ctestPath": "$ctest_path",
    "cmake.sourceDirectory": "$src",
    "cmake.buildDirectory": "$build",
    "cmake.generator": "$generator",$generator_extra
    "cmake.configureOnOpen": true,
    "cmake.defaultVariants": {
      "buildType": {
        "default": "$default",
        "description": "The configuration to build and test",
        "choices": {$choices
        }
      }
    },
    "cmake.ctest.debugLaunchTarget": "Debug the CTest test",
    $intellisense
    "cmake.enableAutomaticKitScan": false
  },
  "launch": {
    "version": "0.2.0",
    "configurations": [
      {
        "name": "Debug the CTest test",
        "type": "cppdbg",
        "request": "launch",
        "program": "\${cmake.testProgram}",
        "args": ["\${cmake.testArgs}"],
        "cwd": "\${cmake.testWorkingDirectory}",
        "MIMode": "gdb",
        "osx": { "MIMode": "lldb" },
        "setupCommands": [{ "text": "-enable-pretty-printing", "ignoreFailures": true }]
      },
      {
        "name": "Debug the launch target",
        "type": "cppdbg",
        "request": "launch",
        "preLaunchTask": "CMake: build",
        "program": "\${command:cmake.launchTargetPath}",
        "args": [],
        "cwd": "\${workspaceFolder}",
        "MIMode": "gdb",
        "osx": { "MIMode": "lldb" },
        "setupCommands": [{ "text": "-enable-pretty-printing", "ignoreFailures": true }]
      }$catch2_launch
    ],
    "inputs": [$catch2_input
    ]
  }
}
EOF
# rewritten only when it changes: an open window reloads its workspace file when it is written
if ! cmp -s "$new" "$file"; then
  cp "$new" "$file"
fi

cat <<EOF
$name - $label
  workspace: $file
             (VS Code opens this workspace file, not the folder: to come back, run this script again or
             File > Open Recent -> "$name - $label (Workspace)")
  build:     $build ($generator; $configurations)
First time in this window (then remembered):
  1. CMake Tools: "Select a kit" -> [Unspecified] (the build keeps its own compiler); it then configures.
  2. clangd, if it asks: install it / disable the other IntelliSense -> yes.
Then: status bar -> configuration (default $default) and Build (F7); Testing view -> run or debug one test.
More: README.md, "Working in VS Code".
EOF

# the README at its "Working in VS Code" section, in the same window
line="$(grep -n '^## Working in VS Code' "$src/README.md" 2>/dev/null | head -n 1 | cut -d: -f1 || true)"
if [[ -n "$line" ]]; then
  open_in_code "$file" --goto "$src/README.md:$line"
else
  open_in_code "$file"
fi
