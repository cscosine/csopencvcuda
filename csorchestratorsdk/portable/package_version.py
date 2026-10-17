import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PackageVersion:
    name: str
    version: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "PackageVersion":
        return cls(**data)


@dataclass(frozen=True)
class CMakeConfigPackageVersionGrep:
    name: str
    version_file: Path


@dataclass
class VersionSearchOutput:
    versions: list[PackageVersion] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# return a tuple bc we do not want dependencies from Expected in github wf
def grep_package_version(filename: Path) -> tuple[str | None, str | None]:
    path = filename

    if not path.is_file():
        return (None, f"ERROR: file not found: {path}")

    content = path.read_text(encoding="utf-8")

    matches = []

    for m in re.finditer(
        r'set\s*\(\s*PACKAGE_VERSION\s+("([^"]*)"|([^\s\)]+))\s*\)',
        content,
    ):
        value = m.group(2) or m.group(3)

        # Ignore computed values like "${PACKAGE_VERSION} (...)"
        if "${" in value:
            continue

        matches.append(value)

    if len(matches) != 1:
        return (None, f"ERROR: {path}: expected exactly one PACKAGE_VERSION definition, found {len(matches)}")

    version = matches[0]
    return (version, None)


# return a tuple bc we do not want dependencies from Expected in github wf
def find_cmake_config_version(search_path: Path, name: str) -> tuple[Path | None, str | None]:
    candidates = {
        f"{name}-config-version.cmake".lower(),
        f"{name}ConfigVersion.cmake".lower(),
    }

    matches = [p for p in search_path.rglob("*") if p.is_file() and p.name.lower() in candidates]

    if not matches:
        return (None, f"No config version file found for '{name}' under '{search_path}'")

    if len(matches) > 1:
        return (None, "Multiple config version files found:" + ", ".join(str(p) for p in matches))

    return (matches[0], None)


def get_package_versions_helper(
    repos_config_file_list: list[CMakeConfigPackageVersionGrep],  # pairs of repo and files reporting versions
    repos_auto_search_list: list[str],  # repo name only
    repos_version: list[PackageVersion],  # pairs of repo and versions
    base_install_dir: Path,
    install_subdir: Path,
) -> VersionSearchOutput:
    result = VersionSearchOutput()

    # fixed versions
    for repo_v in repos_version:
        result.versions.append(PackageVersion(name=repo_v.name, version=repo_v.version))

    # repo with version with file hint
    for repo in repos_config_file_list:
        target_full_path = base_install_dir / install_subdir / repo.version_file

        version_or_err = grep_package_version(target_full_path)

        if version_or_err[1] is not None:
            result.errors.append(version_or_err[1])

        else:
            assert version_or_err[0] is not None
            version = version_or_err[0]
            result.versions.append(PackageVersion(name=repo.name, version=version))

    # repo with version autosearch
    for name in repos_auto_search_list:
        search_path = base_install_dir / install_subdir / name
        path_or_err = find_cmake_config_version(search_path=search_path, name=name)
        if path_or_err[1] is not None:
            result.errors.append(path_or_err[1])

        else:
            assert path_or_err[0] is not None
            path = path_or_err[0]

            version_or_err = grep_package_version(path)

            if version_or_err[1] is not None:
                result.errors.append(version_or_err[1])

            else:
                assert version_or_err[0] is not None
                version = version_or_err[0]
                result.versions.append(PackageVersion(name=name, version=version))

    return result
