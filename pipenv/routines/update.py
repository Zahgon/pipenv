import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, Tuple

from pipenv.exceptions import JSONParseError, PipenvCmdError
from pipenv.patched.pip._vendor.packaging.specifiers import SpecifierSet
from pipenv.patched.pip._vendor.packaging.version import InvalidVersion, Version
from pipenv.routines.lock import overwrite_with_default
from pipenv.routines.outdated import do_outdated
from pipenv.routines.sync import do_sync
from pipenv.utils import err
from pipenv.utils.constants import VCS_LIST
from pipenv.utils.dependencies import (
    expansive_install_req_from_line,
    get_lockfile_section_using_pipfile_category,
    get_pipfile_category_using_lockfile_section,
)
from pipenv.utils.processes import run_command
from pipenv.utils.project import ensure_project
from pipenv.utils.requirements import add_index_to_pipfile
from pipenv.utils.resolver import venv_resolve_deps
from pipenv.vendor import pipdeptree


def do_update(
    project,
    python=None,
    pre=False,
    system=False,
    packages=None,
    editable_packages=None,
    site_packages=False,
    pypi_mirror=None,
    dev=False,
    categories=None,
    index_url=None,
    extra_pip_args=None,
    quiet=False,
    bare=False,
    dry_run=None,
    outdated=False,
    clear=False,
    lock_only=False,
):
    """Update the virtualenv."""
    pass


def get_reverse_dependencies(project) -> Dict[str, Set[Tuple[str, str]]]:
    """Get reverse dependencies using pipdeptree."""
    pass


def check_version_conflicts(
    package_name: str,
    new_version: str,
    reverse_deps: Dict[str, Set[Tuple[str, str]]],
    lockfile: dict,
) -> Set[str]:
    """
    Check if updating a package would create version conflicts with its dependents.
    Returns set of conflicting packages.
    """
    pass


def _locked_version_satisfies_pipfile_specifier(pipfile_specifier, locked_version):
    """
    Check if the locked version satisfies the Pipfile specifier.

    Args:
        pipfile_specifier: Version specifier from Pipfile (e.g., "*", ">=2.25.1", "==1.0.0")
        locked_version: Version string from lockfile (e.g., "==2.31.0")

    Returns:
        True if the locked version satisfies the Pipfile specifier, False otherwise.
    """
    # Handle wildcard - any version is acceptable
    if pipfile_specifier == "*":
        return True

    # Extract the actual version number from the locked version (remove "==")
    if locked_version.startswith("=="):
        version_str = locked_version[2:]
    else:
        version_str = locked_version

    try:
        # Parse the Pipfile specifier and check if locked version satisfies it
        specifier_set = SpecifierSet(pipfile_specifier)
        version = Version(version_str)
        return version in specifier_set
    except (InvalidVersion, ValueError):
        # If we can't parse, fall back to string comparison
        return pipfile_specifier == locked_version


def get_modified_pipfile_entries(project, pipfile_categories):
    """
    Detect Pipfile entries that have been modified since the last lock.
    Returns a dict mapping categories to sets of InstallRequirement objects.

    A package is considered "modified" if:
    - It's new (not in lockfile)
    - Its version specifier has changed such that the locked version no longer satisfies it
    - Its VCS URL, ref, or extras have changed
    """
    modified = defaultdict(dict)
    lockfile = project.lockfile()

    for pipfile_category in pipfile_categories:
        lockfile_category = get_lockfile_section_using_pipfile_category(pipfile_category)
        pipfile_packages = project.parsed_pipfile.get(pipfile_category, {})
        locked_packages = lockfile.get(lockfile_category, {})

        for package_name, pipfile_entry in pipfile_packages.items():
            if package_name not in locked_packages:
                # New package
                modified[lockfile_category][package_name] = pipfile_entry
                continue

            locked_entry = locked_packages[package_name]
            is_modified = False
            locked_version = locked_entry.get("version", "")

            # For string entries (version specifier only)
            if isinstance(pipfile_entry, str):
                # Check if locked version still satisfies the Pipfile specifier
                if not _locked_version_satisfies_pipfile_specifier(
                    pipfile_entry, locked_version
                ):
                    is_modified = True

            # For dict entries, need to compare relevant fields
            elif isinstance(pipfile_entry, dict):
                if "version" in pipfile_entry:
                    # Check if locked version still satisfies the Pipfile specifier
                    if not _locked_version_satisfies_pipfile_specifier(
                        pipfile_entry["version"], locked_version
                    ):
                        is_modified = True

                # Compare VCS fields
                for key in VCS_LIST:
                    if key in pipfile_entry:
                        if (
                            key not in locked_entry
                            or pipfile_entry[key] != locked_entry[key]
                        ):
                            is_modified = True

                # Compare ref for VCS packages
                if "ref" in pipfile_entry:
                    if (
                        "ref" not in locked_entry
                        or pipfile_entry["ref"] != locked_entry["ref"]
                    ):
                        is_modified = True

                # Compare extras
                if "extras" in pipfile_entry:
                    pipfile_extras = set(pipfile_entry["extras"])
                    locked_extras = set(locked_entry.get("extras", []))
                    if pipfile_extras != locked_extras:
                        is_modified = True

            if is_modified:
                modified[lockfile_category][package_name] = pipfile_entry

    return modified


def _prepare_categories(categories, dev, packages):
    """Prepare and normalize categories for upgrade."""
    pass


def _find_additional_categories(packages, lockfile, current_categories):
    """Find additional categories where packages exist."""
    pass


def _detect_conflicts(package_args, reverse_deps, lockfile):
    """Detect version conflicts in package arguments."""
    pass


def _process_package_args(
    project,
    package_args,
    pipfile_category,
    index_name,
    reverse_deps,
    explicitly_requested,
    category,
    has_package_args,
    requested_packages,
    lock_only=False,
):
    """Process package arguments and update requested_packages."""
    for package in package_args[:]:
        install_req, _ = expansive_install_req_from_line(package, expand_env=True)

        name, normalized_name, pipfile_entry = project.generate_package_pipfile_entry(
            install_req, package, category=pipfile_category, index_name=index_name
        )

        # Only add to Pipfile if this category was explicitly requested for this package
        # and lock_only is not set
        if (
            not lock_only
            and has_package_args
            and (
                normalized_name not in explicitly_requested
                or category in explicitly_requested.get(normalized_name, [])
            )
        ):
            # Guard against cross-category contamination: if the package already
            # exists in a *different* Pipfile section (e.g. [dev-packages]) but
            # NOT in the current section (e.g. [packages]), skip the Pipfile write.
            # Example: `pipenv upgrade mypy==1.5.1` without --dev must not silently
            # add mypy to [packages] when it already lives in [dev-packages].
            package_in_current_category = bool(
                project.get_pipfile_entry(normalized_name, pipfile_category)
            )
            package_in_other_category = any(
                project.get_pipfile_entry(normalized_name, cat)
                for cat in project.get_package_categories()
                if cat != pipfile_category
            )
            if not package_in_current_category and package_in_other_category:
                # The package lives in a different section; only update the
                # lockfile, do not modify the Pipfile entry.
                err.print(
                    f"[bold][yellow]Package {normalized_name!r} found in a different "
                    f"Pipfile section than {pipfile_category!r}; skipping Pipfile update "
                    f"to avoid cross-category contamination. "
                    f"Use --dev or --categories to target the correct section.[/bold][/yellow]"
                )
            else:
                project.add_pipfile_entry_to_pipfile(
                    name, normalized_name, pipfile_entry, category=pipfile_category
                )

        requested_packages[pipfile_category][normalized_name] = pipfile_entry

        # Handle reverse dependencies
        if normalized_name in reverse_deps:
            for dependency, _ in reverse_deps[normalized_name]:
                pipfile_entry = project.get_pipfile_entry(
                    dependency, category=pipfile_category
                )
                if not pipfile_entry:
                    requested_packages[pipfile_category][dependency] = {
                        normalized_name: "*"
                    }
                    continue
                requested_packages[pipfile_category][dependency] = pipfile_entry


def _resolve_and_update_lockfile(
    project,
    requested_packages,
    pipfile_category,
    category,
    package_args,
    pre,
    system,
    pypi_mirror,
    lockfile,
    resolved_default_deps=None,
):
    """Resolve dependencies and update lockfile."""
    pass


def _clean_unused_dependencies(
    project,
    lockfile,
    category,
    full_lock_resolution,
    original_lockfile,
    reverse_deps=None,
):
    """
    Remove dependencies that are no longer needed after an upgrade.

    Args:
        project: The project instance
        lockfile: The current lockfile being built
        category: The category to clean (e.g., 'default', 'develop')
        full_lock_resolution: The complete resolution of dependencies
        original_lockfile: The original lockfile before the upgrade
        reverse_deps: Optional mapping of package -> set of (requiring_package, version_constraint)
            built from the installed environment.  When provided it is used to
            detect transitive dependencies that are still required by packages
            whose pinned version was NOT changed by this upgrade.
    """
    if category not in lockfile or category not in original_lockfile:
        return

    # Guard against an empty resolution which would indicate a resolution failure.
    # Without this guard every package in the original lockfile would be incorrectly
    # treated as unused and deleted.
    if not full_lock_resolution:
        return

    # Get the set of packages in the new resolution
    resolved_packages = set(full_lock_resolution.keys())

    # Get the set of packages in the original lockfile for this category
    original_packages = set(original_lockfile[category].keys())

    # Find packages that were in the original lockfile but not in the new resolution
    unused_packages = original_packages - resolved_packages

    # Remove unused packages from the lockfile
    for package_name in unused_packages:
        if package_name in lockfile[category]:
            # Before removing, check whether this package is still needed as a
            # transitive dependency of a package whose version was NOT changed by
            # this upgrade.  full_lock_resolution resolves every Pipfile entry to
            # its *latest* available version, so its transitive closure only
            # reflects the latest versions – not the versions currently pinned in
            # the lockfile.  If a requiring package stayed at its original pinned
            # version its own dependencies have not changed, so we must keep P.
            if reverse_deps is not None:
                still_needed = False
                for requiring_pkg, _ in reverse_deps.get(package_name, set()):
                    if requiring_pkg not in lockfile[category]:
                        continue
                    current_version = lockfile[category][requiring_pkg].get("version")
                    original_version = (
                        original_lockfile[category].get(requiring_pkg, {}).get("version")
                    )
                    # If the requiring package's version is unchanged, its
                    # transitive dependencies haven't changed either – keep P.
                    if (
                        current_version is not None
                        and current_version == original_version
                    ):
                        still_needed = True
                        break
                if still_needed:
                    if project.s.is_verbose():
                        err.print(
                            f"Keeping {package_name} (still needed by a package at its pinned version)"
                        )
                    continue

            if project.s.is_verbose():
                err.print(f"Removing unused dependency: {package_name}")
            del lockfile[category][package_name]


def upgrade(
    project,
    pre=False,
    system=False,
    packages=None,
    editable_packages=None,
    pypi_mirror=None,
    index_url=None,
    categories=None,
    dev=False,
    lock_only=False,
    extra_pip_args=None,
):
    """Enhanced upgrade command with dependency conflict detection."""
    pass
