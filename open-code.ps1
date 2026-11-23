# Owned by the project template (cs-project-template): change it there.
# Opens VS Code on this repository attached to one of its existing builds (made by csorchestrator, or by hand with a
# preset), in either csCMake layout:
#   standalone: <repository>\_csw\build\<variant>\<repository>[\<config>]        (a project with its own sources)
#   sibling:    <workspace>\build\<variant>\<repository>[\<config>]              (a library checked out by its project)
# Writes <build>\<repository>.code-workspace with the settings of that build (build folder, generator, configurations,
# IntelliSense engine, debugger), opens it with the README at "Working in VS Code", and prints the first-time steps.
# The settings shared by every build and OS are in .vscode\settings.json. Same logic on Linux / macOS: open-code.sh.
# A repository with a venv (.venv: a project, a tool) gets it too: active in the shell that starts VS Code, and the
# Python interpreter of the window. C++ sources are a csCMake project (CMakeLists.txt and
# csCMakeProjectSetup.json); without them it opens the folder with the venv, before their first build a Python-only
# workspace file.
# Windows PowerShell 5.1 and PowerShell 7 (ASCII only: 5.1 reads a script without BOM as ANSI).
#
# Usage: .\open-code.ps1 [filter]
#   filter: a part of the build folder name or of the compiler path (msvc, clang-cl, ...); needed when there are several
param([string]$Filter = "")
$ErrorActionPreference = "Stop"

function Normalize([string]$Path) { # CMake writes C:/a/b; compared without case (Windows paths)
    return ($Path -replace '\\', '/').TrimEnd('/').ToLowerInvariant()
}
# VS Code: its `code` command on the PATH (the Windows installer adds it; macOS: command palette, "Shell Command: Install
# 'code' command in PATH"); without it, how to open the file by hand
function OpenInCode([string]$Path, [string[]]$Arguments = @()) {
    if (Get-Command code -ErrorAction SilentlyContinue) {
        & code $Path @Arguments
    } else {
        Write-Host "VS Code's 'code' command is not on the PATH: open $Path by hand (File > Open Workspace from File)."
    }
}

function CacheValue([string]$Cache, [string]$Variable) { # its value in CMakeCache.txt
    $line = Select-String -Path $Cache -Pattern "^$([regex]::Escape($Variable)):[A-Z]*=" | Select-Object -First 1
    if ($null -eq $line) { return "" }
    return $line.Line.Substring($line.Line.IndexOf('=') + 1)
}

$src = (Resolve-Path $PSScriptRoot).Path
$name = Split-Path $src -Leaf

# the venv of the repository, if any (made by setup.ps1): Python, pytest, pre-commit, csorchestrator
$venvPython = ""
if (Test-Path (Join-Path $src ".venv\Scripts\Activate.ps1")) {
    . (Join-Path $src ".venv\Scripts\Activate.ps1")
    $venvPython = Join-Path $src ".venv\Scripts\python.exe"
}

function OpenFolderPythonOnly([string]$Reason) { # the folder and its venv, no C++ build
    Write-Host "${Reason}: opening $name for Python only."
    OpenInCode $src
    exit 0
}
if (-not ((Test-Path (Join-Path $src "CMakeLists.txt")) -and (Test-Path (Join-Path $src "csCMakeProjectSetup.json")))) {
    OpenFolderPythonOnly "No csCMake sources (CMakeLists.txt, csCMakeProjectSetup.json)"
}

# C++ sources not built yet: a Python-only workspace file (in the workspace root, git-ignored) where CMake Tools does not
# configure on its own (as the folder would, with a preset and without the dependencies of the recipe)
function OpenPythonOnlyWorkspace([string]$Reason) {
    $dir = $workspaceRoot
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $file = Join-Path $dir "$name.code-workspace"
    $content = [ordered]@{
        folders  = @([ordered]@{ path = $src; name = "$name - Python only (no C++ build yet)" })
        settings = [ordered]@{
            "python.defaultInterpreterPath" = $venvPython
            "cmake.useCMakePresets"         = "never"
            "cmake.configureOnOpen"         = $false
            "cmake.enableAutomaticKitScan"  = $false
            "clangd.enable"                 = $false
        }
    }
    [IO.File]::WriteAllText($file, (ConvertTo-Json $content -Depth 10))
    Write-Host "${Reason}: opening $name for Python only (venv $src\.venv): $file"
    Write-Host "For C++: run the recipe first (python ${name}_project.py), then this script again."
    OpenInCode $file
    exit 0
}

# where the builds are: the include of csCMakeProjectSetup.json, <csCMake>/presets/layout/<layout>.json, names csCMake;
# in the sibling and standalone layouts csCMake is <workspace root>/csCMake (${sourceParentDir} / ${sourceDir}
# expanded), in the env layouts (env*.json) the workspace root is CSCMAKE_WORKSPACE_ROOT; csCMake's presets build in
# <workspace root>\build. No folder name here: the project's file says it.
$include = ""
$layout = ""
$setupFile = Join-Path $src "csCMakeProjectSetup.json"
if (Test-Path $setupFile) {
    $m = Select-String -Path $setupFile -Pattern '"([^"]*)/presets/layout/([A-Za-z0-9_-]+)\.json"' | Select-Object -First 1
    if ($null -ne $m) { $include = $m.Matches[0].Groups[1].Value; $layout = $m.Matches[0].Groups[2].Value }
}
$workspaceRoot = ""
if ($layout.StartsWith("env")) {
    if ($env:CSCMAKE_WORKSPACE_ROOT) { $workspaceRoot = $env:CSCMAKE_WORKSPACE_ROOT }
} elseif ($include -match '/csCMake$') {
    $csCMakeDir = ""
    if ($include.StartsWith('${sourceDir}/')) {
        $csCMakeDir = Join-Path $src $include.Substring('${sourceDir}/'.Length)
    } elseif ($include.StartsWith('${sourceParentDir}/')) {
        $csCMakeDir = Join-Path (Split-Path $src -Parent) $include.Substring('${sourceParentDir}/'.Length)
    }
    if ($csCMakeDir) { $workspaceRoot = Split-Path $csCMakeDir -Parent }
}
if (-not $workspaceRoot) {
    Write-Error "No workspace root for ${name} from the include of csCMakeProjectSetup.json ('$include'): <root>/csCMake/presets/layout/<layout>.json under `${sourceDir} or `${sourceParentDir}, or an env layout with CSCMAKE_WORKSPACE_ROOT set."
}
$buildRoot = Join-Path $workspaceRoot "build"

# the compiler family of a build, from the compiler CMake identified in it (CMakeFiles\<version>\CMakeCXXCompiler.cmake):
# gcc, clang, appleclang, msvc, clang-cl; the short build folder names say none of them
function CompilerFamily([string]$Dir) {
    $file = Get-ChildItem -Path "$Dir\CMakeFiles\*\CMakeCXXCompiler.cmake" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $file) { return "" }
    $id = ""; $variant = ""
    $m = Select-String -Path $file.FullName -Pattern '^set\(CMAKE_CXX_COMPILER_ID "(.*)"\)$' | Select-Object -First 1
    if ($null -ne $m) { $id = $m.Matches[0].Groups[1].Value }
    $m = Select-String -Path $file.FullName -Pattern '^set\(CMAKE_CXX_COMPILER_FRONTEND_VARIANT "(.*)"\)$' | Select-Object -First 1
    if ($null -ne $m) { $variant = $m.Matches[0].Groups[1].Value }
    if ($id -eq "GNU") { return "gcc" }
    if ($id -eq "Clang" -and $variant -eq "MSVC") { return "clang-cl" }
    if ($id -eq "Clang") { return "clang" }
    if ($id -eq "AppleClang") { return "appleclang" }
    if ($id -eq "MSVC") { return "msvc" }
    return $id
}

# every build of this checkout: multi-config (<variant>\<name>) and single-config (<variant>\<name>\<config>)
$builds = @()
foreach ($root in @($buildRoot)) {
    if (-not (Test-Path $root)) { continue }
    $caches = @(Get-ChildItem -Path "$root\*\$name\CMakeCache.txt", "$root\*\$name\*\CMakeCache.txt" -ErrorAction SilentlyContinue)
    foreach ($cache in $caches) {
        if ((Normalize (CacheValue $cache.FullName "CMAKE_HOME_DIRECTORY")) -ne (Normalize $src)) { continue }
        $dir = $cache.DirectoryName
        $compiler = Split-Path (CacheValue $cache.FullName "CMAKE_CXX_COMPILER") -Leaf
        $relative = $dir.Substring($root.Length + 1)
        $family = CompilerFamily $dir
        if ($Filter -eq "" -or $relative -like "*$Filter*" -or $compiler -like "*$Filter*" -or ($family -ne "" -and $family -like "*$Filter*")) {
            $builds += $dir
        }
    }
}

if ($builds.Count -eq 0 -and $venvPython -ne "" -and $Filter -eq "") {
    OpenPythonOnlyWorkspace "No build of $name yet"
}
if ($builds.Count -eq 0) {
    $suffix = if ($Filter -ne "") { " matching '$Filter'" } else { "" }
    Write-Error "No build of $name$suffix in ${buildRoot}: build it first (csorchestrator)."
}
if ($builds.Count -gt 1) {
    Write-Host "Several builds of ${name}: choose one with a filter (a part of the folder name or of the compiler)."
    $builds | ForEach-Object { Write-Host "  $_ ($(CompilerFamily $_))" }
    exit 1
}

$build = $builds[0]
$cache = Join-Path $build "CMakeCache.txt"
$parent = Split-Path $build -Parent
$label = Split-Path $parent -Leaf
if ($label -eq $name) { $label = "$(Split-Path (Split-Path $parent -Parent) -Leaf)/$(Split-Path $build -Leaf)" }
$generator = CacheValue $cache "CMAKE_GENERATOR"
$platform = CacheValue $cache "CMAKE_GENERATOR_PLATFORM"
$toolset = CacheValue $cache "CMAKE_GENERATOR_TOOLSET"
$configurations = CacheValue $cache "CMAKE_CONFIGURATION_TYPES"
if ($configurations -eq "") { $configurations = CacheValue $cache "CMAKE_BUILD_TYPE" }
if ($configurations -eq "") { $configurations = "Debug" }

# the build types offered by CMake Tools: the configurations of the build, Debug first when it has one
$configs = @($configurations -split ';')
$default = if ($configs -contains "Debug") { "Debug" } else { $configs[0] }
$choices = [ordered]@{}
foreach ($c in $configs) {
    $choices[$c] = [ordered]@{ short = $c; long = "the $c configuration"; buildType = $c }
}

$settings = [ordered]@{
    "cmake.useCMakePresets"         = "never"
    "cmake.cmakePath"               = CacheValue $cache "CMAKE_COMMAND"
    "cmake.ctestPath"               = CacheValue $cache "CMAKE_CTEST_COMMAND"
    "cmake.sourceDirectory"         = $src
    "cmake.buildDirectory"          = $build
    "cmake.generator"               = $generator
    "cmake.configureOnOpen"         = $true
    "cmake.enableAutomaticKitScan"  = $false
    "cmake.defaultVariants"         = [ordered]@{
        buildType = [ordered]@{ default = $default; description = "The configuration to build and test"; choices = $choices }
    }
    "cmake.ctest.debugLaunchTarget" = "Debug the CTest test"
}
if ($platform -ne "") { $settings["cmake.platform"] = $platform }
if ($toolset -ne "") { $settings["cmake.toolset"] = $toolset }
if ($venvPython -ne "") { $settings["python.defaultInterpreterPath"] = $venvPython }
# IntelliSense: clangd on the compile database (Ninja); Visual Studio and Xcode write none: cpptools fed by CMake Tools
if ($generator -like "Visual Studio*" -or $generator -eq "Xcode") {
    $settings["clangd.enable"] = $false
    $settings["C_Cpp.intelliSenseEngine"] = "default"
    $settings["C_Cpp.default.configurationProvider"] = "ms-vscode.cmake-tools"
} else {
    $settings["clangd.enable"] = $true
    $settings["C_Cpp.intelliSenseEngine"] = "disabled"
    $settings["clangd.arguments"] = @("--compile-commands-dir=$build", "--background-index", "--clang-tidy", "--header-insertion=never")
}

# MSVC and clang-cl: the Visual Studio debugger
$launchConfigurations = @(
    [ordered]@{
        name    = "Debug the CTest test"
        type    = "cppvsdbg"
        request = "launch"
        program = '${cmake.testProgram}'
        args    = @('${cmake.testArgs}')
        cwd     = '${cmake.testWorkingDirectory}'
    },
    [ordered]@{
        name          = "Debug the launch target"
        type          = "cppvsdbg"
        request       = "launch"
        preLaunchTask = "CMake: build"
        program       = '${command:cmake.launchTargetPath}'
        args          = @()
        cwd           = '${workspaceFolder}'
    }
)
$inputs = @()
# a build with Catch2 tests: one more configuration, the launch target with a Catch2 test spec
if ((CacheValue $cache "Catch2_DIR") -ne "") {
    $launchConfigurations += [ordered]@{
        name          = "Debug the launch target (Catch2 test spec)"
        type          = "cppvsdbg"
        request       = "launch"
        preLaunchTask = "CMake: build"
        program       = '${command:cmake.launchTargetPath}'
        args          = @('${input:catch2TestSpec}')
        cwd           = '${workspaceFolder}'
    }
    $inputs += [ordered]@{
        id          = "catch2TestSpec"
        type        = "promptString"
        description = "Catch2 test spec: a test name (wildcards allowed), a [tag], or * for all"
        default     = "*"
    }
}
$launch = [ordered]@{ version = "0.2.0"; configurations = $launchConfigurations; inputs = $inputs }

$workspaceFile = [ordered]@{
    folders  = @([ordered]@{ path = $src; name = "$name - $label" })
    settings = $settings
    launch   = $launch
}
$json = ConvertTo-Json $workspaceFile -Depth 20
$file = Join-Path $build "$name.code-workspace"
# rewritten only when it changes: an open window reloads its workspace file when it is written
$old = if (Test-Path $file) { [IO.File]::ReadAllText($file) } else { "" }
if ($old -ne $json) { [IO.File]::WriteAllText($file, $json) } # UTF-8 without BOM, in 5.1 and 7

Write-Host @"
$name - $label
  workspace: $file
             (VS Code opens this workspace file, not the folder: to come back, run this script again or
             File > Open Recent -> "$name - $label (Workspace)")
  build:     $build ($generator; $configurations)
First time in this window (then remembered):
  1. CMake Tools: "Select a kit" -> [Unspecified] (the build keeps its own compiler); it then configures.
Then: status bar -> configuration (default $default) and Build (F7); Testing view -> run or debug one test.
More: README.md, "Working in VS Code".
"@

# the README at its "Working in VS Code" section, in the same window
$readme = Join-Path $src "README.md"
$hit = if (Test-Path $readme) { Select-String -Path $readme -Pattern '^## Working in VS Code' | Select-Object -First 1 } else { $null }
if ($null -ne $hit) { OpenInCode $file @("--goto", "${readme}:$($hit.LineNumber)") } else { OpenInCode $file }
