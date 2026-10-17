from pathlib import Path

from csorchestrator.application.recipes.manifest_github import (
    ManifestGithub,
    create_steps_to_get_libs_from_manifest,
)
from csorchestrator.domain.orchestrator.orchestrator import Orchestrator
from csorchestrator.foundation.core.report import Report
from csorchestrator.frontend.step.step_get_precompiled_lib_github import (
    MappingFunction,
)
from csorchestrator.portable.release_manifest import ReleaseManifest


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

    _ = dependencies_config_path
    _ = download_dependencies_manifest_and_bundle

    return create_steps_to_get_libs_from_manifest(
        orchestrator=orchestrator,
        manifest_description=manifest_description,
        manifest_loaded=manifest_loaded,
        base_libs_dir=base_libs_dir,
        lib_name_list=required_libs,
        mapping_function=mapping_function,
        phase_name=phase_name_suffix,
        dev=False,
    )
