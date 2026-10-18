from copy import deepcopy

from csorchestrator.domain.context.context_compiler_generator import (
    Compiler,
    ContextCompilerGenerator,
    GeneratorWithType,
)
from csorchestrator.domain.context.context_os_architecture import (
    OS,
    Architecture,
)
from csorchestrator.frontend.cscmake_presets.supported_variants import (
    get_supported_context_os_architecture_list,
)

from csopencvcuda_config import opencv_mapping
from utils.build_matrix import populate_build_matrix


def test_opencv_mapping_on_supported_contexts() -> None:
    """opencv_mapping must map (or explicitly reject) every supported context."""

    for config in get_supported_context_os_architecture_list():
        res = opencv_mapping(deepcopy(config))  # deep copy to be sure

        if config.context_os_architecture.os == OS.LINUX:
            if config.context_os_architecture.architecture != Architecture.X64:
                # linux non x64 is not built: mapping must reject it
                assert res is None
                continue

            assert res is not None
            assert res.context_os_architecture == config.context_os_architecture
            assert res.context_compiler_generator == ContextCompilerGenerator(
                compiler_family=Compiler.GCC,
                compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
                build_generator=GeneratorWithType.NINJA,
            )

        elif config.context_os_architecture.os == OS.WINDOWS:
            assert res is not None
            assert res.context_os_architecture == config.context_os_architecture
            assert res.context_compiler_generator == ContextCompilerGenerator(
                compiler_family=Compiler.MSVC,
                compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
                build_generator=GeneratorWithType.MSVC_17_2022,
            )

        else:
            raise AssertionError("non expected config")


def test_opencv_mapping_is_defined_on_build_matrix() -> None:
    """Every context of the csopencvcuda build matrix must be consumable."""

    build_matrix = populate_build_matrix()
    assert len(build_matrix) > 0

    for config in build_matrix:
        res = opencv_mapping(deepcopy(config))
        assert res is not None
        assert res.context_os_architecture == config.context_os_architecture


def test_build_matrix_platforms_and_architectures() -> None:
    """The build matrix is Linux x64 (gcc/clang ninja) + Windows x64 (msvc)."""

    build_matrix = populate_build_matrix()

    for config in build_matrix:
        os_arch = config.context_os_architecture
        assert os_arch.architecture == Architecture.X64

        if os_arch.os == OS.LINUX:
            assert config.context_compiler_generator.compiler_family in (Compiler.GCC, Compiler.CLANG)
            assert config.context_compiler_generator.build_generator == GeneratorWithType.NINJA
        elif os_arch.os == OS.WINDOWS:
            assert config.context_compiler_generator.compiler_family == Compiler.MSVC
            assert config.context_compiler_generator.build_generator in (GeneratorWithType.MSVC_17_2022,)
        else:
            raise AssertionError("non expected os in build matrix")
