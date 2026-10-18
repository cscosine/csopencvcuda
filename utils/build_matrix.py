from csorchestrator.domain.context.context_compiler_generator import (
    Compiler,
    ContextCompilerGenerator,
    GeneratorWithType,
)
from csorchestrator.domain.context.context_os_architecture import (
    ARCHITECTURE_VARIANT_GENERIC,
    OS,
    Architecture,
    ContextOsArchitecture,
)
from csorchestrator.domain.context.context_os_architecture_compiler_generator import (
    ContextOsArchitectureCompilerGenerator,
)
from csorchestrator.frontend.cscmake_presets.supported_variants import (
    get_supported_os_version_list,
)


def populate_build_matrix() -> list[ContextOsArchitectureCompilerGenerator]:
    """Contexts supported by the csopencvcuda OpenCV+CUDA build.

    - Linux: x64 only (CUDA requirement), GCC and CLANG with the Ninja
      single-config generator.
    - Windows: x64 only, MSVC with the Visual Studio multi-config generators
      2022; non-MSVC compilers are not supported by this OpenCV build.

    NOTE: this deviates from the csorchestrator default matrix
    (`get_supported_context_os_architecture_list()`), which includes Linux arm64
    and non-MSVC Windows compilers: those combinations are intentionally not
    built here.
    """
    ret_list: list[ContextOsArchitectureCompilerGenerator] = []

    # ------------------------------ LINUX ------------------------------
    for os_version in get_supported_os_version_list(OS.LINUX):
        os_arch = ContextOsArchitecture(
            os=OS.LINUX,
            os_version=os_version,
            architecture=Architecture.X64,
            architecture_variant=ARCHITECTURE_VARIANT_GENERIC,
        )
        for compiler in [Compiler.GCC, Compiler.CLANG]:
            ccg = ContextCompilerGenerator(
                compiler_family=compiler,
                compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
                build_generator=GeneratorWithType.NINJA,
            )
            ret_list.append(
                ContextOsArchitectureCompilerGenerator(
                    context_os_architecture=os_arch,
                    context_compiler_generator=ccg,
                )
            )

    # ------------------------------ WINDOWS -----------------------------
    for os_version in get_supported_os_version_list(OS.WINDOWS):
        os_arch = ContextOsArchitecture(
            os=OS.WINDOWS,
            os_version=os_version,
            architecture=Architecture.X64,
            architecture_variant=ARCHITECTURE_VARIANT_GENERIC,
        )
        for generator in [
            GeneratorWithType.MSVC_17_2022,
        ]:
            ccg = ContextCompilerGenerator(
                compiler_family=Compiler.MSVC,
                compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
                build_generator=generator,
            )
            ret_list.append(
                ContextOsArchitectureCompilerGenerator(
                    context_os_architecture=os_arch,
                    context_compiler_generator=ccg,
                )
            )

    return ret_list
