import json
import shutil
import tarfile
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# WAR: do not use assert_never from typing because this can be used in 3.10 too (e.g. on ubuntu 22.04)
from typing import Any, ClassVar, NoReturn, TypeAlias

from .package_version import (
    CMakeConfigPackageVersionGrep,
    PackageVersion,
    get_package_versions_helper,
)


def assert_never(value: NoReturn) -> NoReturn:
    raise AssertionError(f"Unhandled value: {value!r}")


class PublishPackageMode(Enum):
    ON_VARIANT = "ON_VARIANT"
    HEADERS_ONLY = "HEADERS_ONLY"

    # required to represent this in package generation
    def __repr__(self) -> str:
        return f"{type(self).__qualname__}.{self.name}"


ReposPublishConfigDict: TypeAlias = dict[str, PublishPackageMode]


@dataclass
class ManifestVersionsEntry:
    variant: str
    entries: list[PackageVersion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManifestVersionsEntry":
        return cls(
            variant=data["variant"],
            entries=[PackageVersion.from_dict(entry) for entry in data["entries"]],
        )

    @classmethod
    def compose_name_version_to_string(cls, name: str, version: str) -> str:
        return f"{name}-{version}"


@dataclass
class ReleaseManifest:
    project_name: str
    project_version: str

    additional_files: list[str]

    packages: set[str]
    headers_only_packages: set[str]

    dependencies: dict[str, set[str]]
    dependencies_dev: dict[str, set[str]]

    output_bundle_file_name: str | None

    variants: list[ManifestVersionsEntry] = field(default_factory=list)

    MANIFEST_VERSION: ClassVar[str] = "1.0"

    manifest_version: str = MANIFEST_VERSION

    CSORCHESTRATOR_MANIFEST_EXTENSION: ClassVar[str] = ".csOrchestratorManifest"
    CSORCHESTRATOR_MANIFEST_ROOT: ClassVar[str] = "csorchestrator_manifest"

    def __post_init__(self) -> None:
        # ensure dependencies and dependencies_dev are fille in with all packages
        all_packages = deepcopy(self.packages)
        all_packages = all_packages.union(self.headers_only_packages)

        for p in all_packages:
            if p not in self.dependencies:
                self.dependencies[p] = set()
            if p not in self.dependencies_dev:
                self.dependencies_dev[p] = set()

    @classmethod
    def create_manifest_filename_from_project_name_and_version_string(cls, project_name_version: str) -> str:
        return project_name_version + ReleaseManifest.CSORCHESTRATOR_MANIFEST_EXTENSION

    def create_manifest_filename(self) -> str:
        return ReleaseManifest.create_manifest_filename_from_project_name_and_version_string(
            ManifestVersionsEntry.compose_name_version_to_string(self.project_name, self.project_version)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            ReleaseManifest.CSORCHESTRATOR_MANIFEST_ROOT: {
                "manifest_version": self.manifest_version,
                "project_name": self.project_name,
                "project_version": self.project_version,
                "additional_files": list(self.additional_files),
                "packages": list(self.packages),
                "headers_only_packages": list(self.headers_only_packages),
                "dependencies": {name: sorted(deps) for name, deps in self.dependencies.items()},
                "dependencies_dev": {name: sorted(deps) for name, deps in self.dependencies_dev.items()},
                "output_bundle_file_name": self.output_bundle_file_name,
                "variants": [variant.to_dict() for variant in self.variants],
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReleaseManifest":
        in_data = data[ReleaseManifest.CSORCHESTRATOR_MANIFEST_ROOT]
        return cls(
            manifest_version=in_data["manifest_version"],
            project_name=in_data["project_name"],
            project_version=in_data["project_version"],
            additional_files=in_data["additional_files"],
            packages=set(in_data["packages"]),
            headers_only_packages=set(in_data["headers_only_packages"]),
            dependencies={name: set(deps) for name, deps in in_data["dependencies"].items()},
            dependencies_dev={name: set(deps) for name, deps in in_data["dependencies_dev"].items()},
            output_bundle_file_name=in_data["output_bundle_file_name"],
            variants=[ManifestVersionsEntry.from_dict(variant) for variant in in_data["variants"]],
        )

    def write_release_manifest(
        self,
        filename: Path,
    ) -> None:
        """Write a release manifest to a JSON file."""
        path = Path(filename)
        # TODO robustify and return possible errors
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
            f.write("\n")

    @classmethod
    def load_release_manifest(
        cls,
        filename: Path,
    ) -> "ReleaseManifest":
        """Load a release manifest from a JSON file."""
        path = Path(filename)
        # TODO robustify and return possible errors
        with path.open("r", encoding="utf-8") as f:
            return ReleaseManifest.from_dict(json.load(f))


def get_package_versions_and_write_single_variant_manifest(
    repos_config_file_list: list[CMakeConfigPackageVersionGrep],  # pairs of repo and files reporting versions
    repos_auto_search_list: list[str],  # repo name only
    repos_version: list[PackageVersion],  # pairs of repo and versions
    base_install_dir: Path,
    install_subdir: Path,
    variant_string: str,
    project_name: str,
    project_version: str,
    output_file: Path,
) -> list[str]:  # return errors

    result = get_package_versions_helper(
        repos_config_file_list,
        repos_auto_search_list,
        repos_version,
        base_install_dir,
        install_subdir,
    )

    if result.errors:
        return result.errors

    entry = ManifestVersionsEntry(variant=variant_string, entries=result.versions)
    manifest = ReleaseManifest(
        project_name=project_name,
        project_version=project_version,
        packages={package.name for package in entry.entries},
        headers_only_packages=set(),
        dependencies_dev={},
        dependencies={},
        variants=[entry],
        additional_files=[],
        output_bundle_file_name=None,
    )

    manifest.write_release_manifest(output_file)

    return []


def load_release_manifest_single_variant(
    input_full_path: Path,
    expected_context_os_architecture_compiler_generator_string: str,
) -> list[PackageVersion] | str:  # str in case of error
    packages = ReleaseManifest.load_release_manifest(input_full_path)
    if len(packages.variants) == 0 or len(packages.variants) > 1:
        return f"release manifest {str(input_full_path)} has {len(packages.variants)} variants, expected 1"

    if expected_context_os_architecture_compiler_generator_string != packages.variants[0].variant:
        return f"release manifest {str(input_full_path)} has variant name {packages.variants[0].variant}, expected {expected_context_os_architecture_compiler_generator_string}"  # noqa: E501

    return packages.variants[0].entries


def create_artifact_name(
    project_name_and_version: str,
    context_os_architecture_compiler_generator_string: str,
) -> str:
    return f"{project_name_and_version}-{context_os_architecture_compiler_generator_string}"


def create_archive_filename(
    project_name_and_version: str,
    context_os_architecture_compiler_generator_string: str,
    lib_name: str,
    lib_version: str,
) -> str:
    return (
        project_name_and_version
        + "-"
        + lib_name
        + "-"
        + lib_version
        + "-"
        + context_os_architecture_compiler_generator_string
        + ".tar.gz"
    )


def load_release_manifest_single_variant_and_prepare_archive(
    input_full_path: Path,
    project_name_and_version: str,
    context_os_architecture_compiler_generator_string: str,
    input_base_dir: Path,
) -> list[str]:  # return errors
    # load which packages to create archives for from the version file (eg. eigen3: 3.4.0, boost: 1.82.0, etc)
    packages_or_error = load_release_manifest_single_variant(
        input_full_path, context_os_architecture_compiler_generator_string
    )

    if isinstance(packages_or_error, str):
        return [packages_or_error]
    packages = packages_or_error

    for item in packages:
        input_path = Path(
            input_base_dir / context_os_architecture_compiler_generator_string / Path(item.name)
        ).resolve()
        output_path = Path(
            input_base_dir
            / Path(
                create_archive_filename(
                    project_name_and_version,
                    context_os_architecture_compiler_generator_string,
                    item.name,
                    item.version,
                )
            )
        ).resolve()

        with tarfile.open(output_path, "w:gz") as tar:
            for path in input_path.rglob("*"):
                resolved_path = path.resolve()
                # make the archive self-contained: entries start directly with the
                # lib folder (e.g. "libassert/include/..."), not with the variant
                # folder, so that extracting into workspace/libs/<variant> makes the
                # package findable via CMAKE_PREFIX_PATH=<workspace>/libs/<variant>
                arcname = path.resolve().relative_to(input_path.parent)
                tar.add(resolved_path, arcname=arcname)

    return []


# TODO: manage errors
def copy_additional_files(
    base_path_additional_files: Path,
    list_additional_files: list[Path],
    output_folder_additional_files: Path,
) -> None:
    for file_path in list_additional_files:
        # Make the path absolute relative to the base path
        file_path = base_path_additional_files / file_path

        # Get the path relative to the base directory
        relative_path = file_path.relative_to(base_path_additional_files)

        # Preserve the subfolder structure in the output directory
        destination = output_folder_additional_files / relative_path

        # Create parent directories if needed
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Copy the file
        shutil.copy2(file_path, destination)


def create_archive_additional_files(source_folder: Path, source_list: list[Path], output_archive: Path) -> None:
    # TODO manage errors
    with tarfile.open(output_archive, "w:gz") as tar:
        for path in source_list:
            resolved_path = (source_folder / path).resolve()
            arcname = (source_folder / path).resolve().relative_to(source_folder.resolve())
            tar.add(resolved_path, arcname=arcname)


def collect_release_manifest_single_variant_and_prepare_manifest(
    input_folder_base: Path,
    input_manifest_path_variant: list[tuple[Path, str]],
    output_manifest_filename: Path,
    project_name: str,
    project_version: str,
    base_path_additional_files: Path,
    list_additional_files: list[Path],
    output_folder_additional_files: Path,
    output_bundle_file_name: Path,
    repo_publish_config_dict: ReposPublishConfigDict,
    header_only_variants_sources: dict[
        str, str
    ],  # csv1-windows --> csv1-windows-11- .... csv1-linux --> csv1-linux-ubuntu ....
    dependencies: dict[str, set[str]],
    dependencies_dev: dict[str, set[str]],
    archive_files_are_in_context_based_folder: bool,
) -> list[str]:  # return errors

    # collect single variants manifest and cumulate
    # and collect all packages names as single set
    packages_names_set: set[str] = set()
    collected_version_entries: list[ManifestVersionsEntry] = []
    for (
        input_full_path,
        context_os_architecture_compiler_generator_string,
    ) in input_manifest_path_variant:
        packages_or_error = load_release_manifest_single_variant(
            input_full_path, context_os_architecture_compiler_generator_string
        )

        if isinstance(packages_or_error, str):
            return [packages_or_error]
        packages = packages_or_error

        packages_names_set |= {package.name for package in packages}

        collected_version_entries.append(
            ManifestVersionsEntry(
                variant=context_os_architecture_compiler_generator_string,
                entries=packages,
            )
        )

    # add defaults AS_VARIANT to repo_publish_config_dict
    repo_publish_config_dict.update(
        (name, PublishPackageMode.ON_VARIANT) for name in packages_names_set if name not in repo_publish_config_dict
    )

    on_variant_packages: set[str] = {
        package for package, config in repo_publish_config_dict.items() if config == PublishPackageMode.ON_VARIANT
    }
    headers_only_packages: set[str] = {
        package for package, config in repo_publish_config_dict.items() if config == PublishPackageMode.HEADERS_ONLY
    }

    project_name_and_version = ManifestVersionsEntry.compose_name_version_to_string(project_name, project_version)

    final_collected_version_entries: list[ManifestVersionsEntry] = []
    # collect non-headers only entries only and files to remove
    files_to_remove: list[str] = []
    for collected_version_entry in collected_version_entries:
        variant_entries: list[PackageVersion] = []
        for package in collected_version_entry.entries:
            publish_mode = repo_publish_config_dict[package.name]
            if package.name in repo_publish_config_dict:
                match publish_mode:
                    case PublishPackageMode.ON_VARIANT:
                        variant_entries.append(package)
                    case PublishPackageMode.HEADERS_ONLY:
                        package_file_name = create_archive_filename(
                            project_name_and_version=project_name_and_version,
                            context_os_architecture_compiler_generator_string=collected_version_entry.variant,
                            lib_name=package.name,
                            lib_version=package.version,
                        )

                        if archive_files_are_in_context_based_folder:
                            package_file_name = (
                                create_artifact_name(
                                    project_name_and_version=project_name_and_version,
                                    context_os_architecture_compiler_generator_string=collected_version_entry.variant,
                                )
                                + "/"
                                + package_file_name
                            )

                        files_to_remove.append(package_file_name)

                    case _:
                        assert_never(publish_mode)

        final_collected_version_entries.append(
            ManifestVersionsEntry(variant=collected_version_entry.variant, entries=variant_entries)
        )

    # collect headers only to representative headers only versions
    files_to_move: list[tuple[str, str]] = []
    subfolders_to_create: set[str] = set()
    for (
        header_only_variant,
        header_only_variant_src,
    ) in header_only_variants_sources.items():
        entries: list[PackageVersion] = []
        version_entry: ManifestVersionsEntry | None = None
        for variant in collected_version_entries:
            if variant.variant == header_only_variant_src:
                version_entry = variant
        if version_entry is None:
            continue

        for package in version_entry.entries:
            publish_mode = repo_publish_config_dict[package.name]
            if package.name in repo_publish_config_dict:
                match publish_mode:
                    case PublishPackageMode.ON_VARIANT:
                        pass
                    case PublishPackageMode.HEADERS_ONLY:
                        entries.append(package)
                        src = create_archive_filename(
                            project_name_and_version=project_name_and_version,
                            context_os_architecture_compiler_generator_string=header_only_variant_src,
                            lib_name=package.name,
                            lib_version=package.version,
                        )

                        dst = create_archive_filename(
                            project_name_and_version=project_name_and_version,
                            context_os_architecture_compiler_generator_string=header_only_variant,
                            lib_name=package.name,
                            lib_version=package.version,
                        )

                        if archive_files_are_in_context_based_folder:
                            dst_subdir = create_artifact_name(
                                project_name_and_version=project_name_and_version,
                                context_os_architecture_compiler_generator_string=header_only_variant,
                            )
                            subfolders_to_create.add(dst_subdir)

                            src = (
                                create_artifact_name(
                                    project_name_and_version=project_name_and_version,
                                    context_os_architecture_compiler_generator_string=header_only_variant_src,
                                )
                                + "/"
                                + src
                            )
                            dst = dst_subdir + "/" + dst
                        files_to_move.append((src, dst))
                    case _:
                        assert_never(publish_mode)

        final_collected_version_entries.append(ManifestVersionsEntry(variant=header_only_variant, entries=entries))

    # TODO

    # create headers only folders
    for sf in subfolders_to_create:
        Path(input_folder_base / Path(sf)).mkdir(exist_ok=True)

    # rename headers only files to headers only variant
    for fsrc, fdst in files_to_move:
        Path(input_folder_base / fsrc).rename(input_folder_base / fdst)

    # remove per build variants to not upload as release
    for f in files_to_remove:
        Path(input_folder_base / f).unlink(missing_ok=True)

    # Create output directories if needed
    output_folder_additional_files.mkdir(parents=True, exist_ok=True)

    release_manifest = ReleaseManifest(
        project_name=project_name,
        project_version=project_version,
        packages=on_variant_packages,
        headers_only_packages=headers_only_packages,
        variants=final_collected_version_entries,
        additional_files=[file.as_posix() for file in list_additional_files],
        output_bundle_file_name=output_bundle_file_name.as_posix(),
        dependencies=dependencies,
        dependencies_dev=dependencies_dev,
    )
    release_manifest.write_release_manifest(
        output_folder_additional_files / output_manifest_filename,
    )

    if len(list_additional_files) > 0:
        copy_additional_files(
            base_path_additional_files=base_path_additional_files,
            list_additional_files=list_additional_files,
            output_folder_additional_files=output_folder_additional_files,
        )

        create_archive_additional_files(
            source_folder=output_folder_additional_files,
            source_list=list_additional_files,
            output_archive=output_folder_additional_files / output_bundle_file_name,
        )

    return []
