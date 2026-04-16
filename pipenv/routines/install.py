import os
import queue
import sys
import warnings
from collections import defaultdict
from tempfile import NamedTemporaryFile

from pipenv import environments, exceptions
from pipenv.patched.pip._internal.exceptions import PipError
from pipenv.routines.lock import do_lock
from pipenv.utils import console, err, fileutils
from pipenv.utils.dependencies import (
    expansive_install_req_from_line,
    get_lockfile_section_using_pipfile_category,
    install_req_from_pipfile,
    normalize_editable_path_for_pip,
)
from pipenv.utils.indexes import get_source_list
from pipenv.utils.internet import download_file, is_valid_url
from pipenv.utils.pip import (
    get_trusted_hosts,
    pip_install_deps,
)
from pipenv.utils.pipfile import ensure_pipfile
from pipenv.utils.project import ensure_project
from pipenv.utils.requirements import add_index_to_pipfile, import_requirements
from pipenv.utils.shell import temp_environ


def _should_use_no_binary(pkg_name, extra_pip_args):
    """Return True if --no-binary should be recorded in the Pipfile for pkg_name.

    Checks both ``extra_pip_args`` (e.g. ``["--no-binary", "cartopy"]``) and the
    ``PIP_NO_BINARY`` environment variable (e.g. ``PIP_NO_BINARY=cartopy``).
    """
    pass


def handle_new_packages(
    project,
    packages,
    editable_packages,
    dev,
    pre,
    system,
    pypi_mirror,
    extra_pip_args,
    pipfile_categories,
    perform_upgrades=True,
    index=None,
):
    pass


def handle_lockfile(
    project,
    packages,
    ignore_pipfile,
    skip_lock,
    system,
    allow_global,
    deploy,
    pre,
    pypi_mirror,
    categories,
):
    """Handle the lockfile, updating if necessary.  Returns True if package updates were applied."""
    if (
        (project.lockfile_exists and not ignore_pipfile)
        and not skip_lock
        and not packages
    ):
        old_hash = project.get_lockfile_hash()
        new_hash = project.calculate_pipfile_hash()
        if new_hash != old_hash:
            if deploy:
                console.print(
                    f"Your Pipfile.lock ({old_hash}) is out of date. Expected: ({new_hash}).",
                    style="red",
                )
                raise exceptions.DeployException
            elif not system:
                handle_outdated_lockfile(
                    project,
                    packages,
                    old_hash=old_hash,
                    new_hash=new_hash,
                    system=system,
                    allow_global=allow_global,
                    skip_lock=skip_lock,
                    pre=pre,
                    pypi_mirror=pypi_mirror,
                    categories=categories,
                )
    elif not project.lockfile_exists and not skip_lock:
        handle_missing_lockfile(project, system, allow_global, pre, pypi_mirror)


def handle_outdated_lockfile(
    project,
    packages,
    old_hash,
    new_hash,
    system,
    allow_global,
    skip_lock,
    pre,
    pypi_mirror,
    categories,
):
    """Handle an outdated lockfile returning True if package updates were applied."""
    if (system or allow_global) and not (project.s.PIPENV_VIRTUALENV):
        err.print(
            f"Pipfile.lock ({old_hash}) out of date, but installation uses --system so"
            f" re-building lockfile must happen in isolation."
            f" Please rebuild lockfile in a virtualenv. Continuing anyway...",
            style="yellow",
        )
    else:
        if old_hash:
            msg = (
                "Pipfile.lock ({0}) out of date: run `pipenv lock` to update to ({1})..."
            )
        else:
            msg = "Pipfile.lock is corrupt, replaced with ({1})..."
        err.print(
            msg.format(old_hash, new_hash),
            style="bold yellow",
        )
        if not skip_lock:
            do_lock(
                project,
                system=system,
                pre=pre,
                write=True,
                pypi_mirror=pypi_mirror,
                categories=None,
            )


def handle_missing_lockfile(project, system, allow_global, pre, pypi_mirror):
    if (system or allow_global) and not project.s.PIPENV_VIRTUALENV:
        raise exceptions.PipenvOptionsError(
            "--system",
            "--system is intended to be used for Pipfile installation, "
            "not installation of specific packages. Aborting.\n"
            "See also: --deploy flag.",
        )
    else:
        if not project.s.is_quiet():
            err.print(
                "Pipfile.lock not found, creating...",
                style="bold",
            )
        do_lock(
            project,
            system=system,
            pre=pre,
            write=True,
            pypi_mirror=pypi_mirror,
        )


def do_install(
    project,
    packages=False,
    editable_packages=False,
    index=False,
    dev=False,
    python=False,
    pypi_mirror=None,
    system=False,
    ignore_pipfile=False,
    requirementstxt=False,
    pre=False,
    deploy=False,
    site_packages=None,
    extra_pip_args=None,
    pipfile_categories=None,
    skip_lock=False,
):
    pass


def do_install_validations(
    project,
    package_args,
    requirements_directory,
    dev=False,
    system=False,
    ignore_pipfile=False,
    requirementstxt=False,
    pre=False,
    deploy=False,
    categories=None,
    skip_lock=False,
):
    # Don't attempt to install develop and default packages if Pipfile is missing
    pass


def install_build_system_packages(
    project,
    allow_global=False,
    pypi_mirror=None,
    requirements_dir=None,
):
    """Install packages specified in [build-system].requires from the Pipfile.

    These packages are installed before any other packages are resolved or installed,
    so they are available when building packages that import non-standard tools in
    their setup.py (e.g. custom setuptools wrappers).

    Example Pipfile::

        [build-system]
        requires = ["stwrapper", "setuptools>=40.8.0", "wheel"]

    :param project: The pipenv project instance.
    :param allow_global: Whether to use the global Python environment.
    :param pypi_mirror: Optional PyPI mirror URL.
    :param requirements_dir: Optional temporary directory for requirements files.
    """
    build_requires = project.pipfile_build_requires
    if not build_requires:
        return

    if not requirements_dir:
        requirements_dir = fileutils.create_tracked_tempdir(
            suffix="-requirements", prefix="pipenv-"
        )

    if not project.s.is_quiet():
        err.print(
            "Installing [build-system] dependencies...",
            style="bold",
        )

    sources = get_source_list(
        project,
        index=None,
        extra_indexes=None,
        trusted_hosts=get_trusted_hosts(),
        pypi_mirror=pypi_mirror,
    )

    procs = queue.Queue(maxsize=1)
    cmds = pip_install_deps(
        project,
        deps=build_requires,
        sources=sources,
        allow_global=allow_global,
        ignore_hashes=True,  # Build deps are not hashed
        no_deps=False,
        requirements_dir=requirements_dir,
        use_pep517=True,
        extra_pip_args=None,
    )

    for c in cmds:
        procs.put(c)
        _cleanup_procs(project, procs)


def do_install_dependencies(
    project,
    dev=False,
    bare=False,
    allow_global=False,
    ignore_hashes=False,
    requirements_dir=None,
    pypi_mirror=None,
    extra_pip_args=None,
    categories=None,
    skip_lock=False,
):
    """
    Executes the installation functionality.

    """
    # Install any build-system packages first so they are available when
    # building packages that use non-standard setup.py tooling.
    install_build_system_packages(
        project,
        allow_global=allow_global,
        pypi_mirror=pypi_mirror,
        requirements_dir=requirements_dir,
    )
    procs = queue.Queue(maxsize=1)
    if not categories:
        if dev:
            categories = ["packages", "dev-packages"]
        else:
            categories = ["packages"]

    for pipfile_category in categories:
        lockfile = None
        pipfile = None
        if skip_lock:
            ignore_hashes = True
            if not bare and not project.s.is_quiet():
                console.print("Installing dependencies from Pipfile...", style="bold")
            pipfile = project.get_pipfile_section(pipfile_category)
        else:
            lockfile = project.get_or_create_lockfile(categories=categories)
            if not bare and not project.s.is_quiet():
                lockfile_category = get_lockfile_section_using_pipfile_category(
                    pipfile_category
                )
                lockfile_type = (
                    "pylock.toml"
                    if project.pylock_exists
                    and (project.use_pylock or not project.lockfile_exists)
                    else "Pipfile.lock"
                )
                lockfile_hash = lockfile["_meta"].get("hash", {}).get("sha256", "") or ""
                hash_suffix = f"({lockfile_hash[-6:]})" if lockfile_hash else ""
                console.print(
                    f"Installing dependencies from {lockfile_type} "
                    f"[{lockfile_category}]{hash_suffix}...",
                    style="bold",
                )
        if skip_lock:
            deps_list = []
            for req_name, pipfile_entry in pipfile.items():
                install_req, markers, req_line = install_req_from_pipfile(
                    req_name, pipfile_entry
                )
                deps_list.append(
                    (
                        install_req,
                        req_line,
                    )
                )
        else:
            lockfile_category = get_lockfile_section_using_pipfile_category(
                pipfile_category
            )
            deps_list = list(
                lockfile.get_requirements(
                    dev=dev, only=False, categories=[lockfile_category]
                )
            )
        editable_or_vcs_deps = [
            (dep, pip_line) for dep, pip_line in deps_list if (dep.link and dep.editable)
        ]
        normal_deps = [
            (dep, pip_line)
            for dep, pip_line in deps_list
            if not (dep.link and dep.editable)
        ]

        install_kwargs = {
            "no_deps": not skip_lock,
            "ignore_hashes": ignore_hashes,
            "allow_global": allow_global,
            "pypi_mirror": pypi_mirror,
            "sequential_deps": editable_or_vcs_deps,
            "extra_pip_args": extra_pip_args,
        }
        if skip_lock:
            lockfile_section = pipfile
        else:
            lockfile_category = get_lockfile_section_using_pipfile_category(
                pipfile_category
            )
            lockfile_section = lockfile[lockfile_category]
        batch_install(
            project,
            normal_deps,
            lockfile_section,
            procs,
            requirements_dir,
            **install_kwargs,
        )

        if not procs.empty():
            _cleanup_procs(project, procs)


def batch_install_iteration(
    project,
    deps_to_install,
    sources,
    procs,
    requirements_dir,
    no_deps=True,
    ignore_hashes=False,
    allow_global=False,
    extra_pip_args=None,
):
    with temp_environ():
        if not allow_global:
            os.environ["PIP_USER"] = "0"
            if "PYTHONHOME" in os.environ:
                del os.environ["PYTHONHOME"]
        if "GIT_CONFIG" in os.environ:
            del os.environ["GIT_CONFIG"]
        cmds = pip_install_deps(
            project,
            deps=deps_to_install,
            sources=sources,
            allow_global=allow_global,
            ignore_hashes=ignore_hashes,
            no_deps=no_deps,
            requirements_dir=requirements_dir,
            use_pep517=True,
            extra_pip_args=extra_pip_args,
        )

        for c in cmds:
            procs.put(c)
            _cleanup_procs(project, procs)


def batch_install(
    project,
    deps_list,
    lockfile_section,
    procs,
    requirements_dir,
    no_deps=True,
    ignore_hashes=False,
    allow_global=False,
    pypi_mirror=None,
    sequential_deps=None,
    extra_pip_args=None,
):
    if sequential_deps is None:
        sequential_deps = []

    # Collect packages that require --no-binary from the lockfile / pipfile section.
    # This ensures that packages installed via "pipenv install" from an existing
    # Pipfile/lockfile honour the no_binary flag that was recorded at install time.
    no_binary_packages = [
        pkg_name
        for pkg_name, entry in lockfile_section.items()
        if isinstance(entry, dict) and entry.get("no_binary")
    ]
    if no_binary_packages:
        extra_pip_args = list(extra_pip_args or [])
        extra_pip_args += ["--no-binary", ",".join(no_binary_packages)]

    deps_to_install = deps_list[:]
    deps_to_install.extend(sequential_deps)
    filtered_deps = []
    for dep, pip_line in deps_to_install:
        # Skip packages whose environment markers don't match the current
        # Python environment (e.g. python_version < '3.11' on Python 3.11).
        # This ensures pipenv install -r and pipenv sync behave consistently.
        # KeyError can occur for pylock.toml markers that use non-PEP-508
        # variables like 'dependency_groups'; those are already filtered at
        # the lockfile level so we simply include the package here.
        try:
            markers_match = not dep.markers or dep.markers.evaluate()
        except KeyError:
            markers_match = True
        if not markers_match:
            err.print(
                f"Ignoring [bold]{dep.name}[/bold]: markers "
                f"[yellow]{dep.markers!r}[/yellow] don't match your environment",
                style="dim",
            )
            continue
        if not project.environment.is_satisfied(dep):
            filtered_deps.append((dep, pip_line))
    deps_to_install = filtered_deps
    search_all_sources = project.settings.get("install_search_all_sources", False)
    sources = get_source_list(
        project,
        index=None,
        extra_indexes=None,
        trusted_hosts=get_trusted_hosts(),
        pypi_mirror=pypi_mirror,
    )
    if search_all_sources:
        dependencies = [pip_line for _, pip_line in deps_to_install]
        batch_install_iteration(
            project,
            dependencies,
            sources,
            procs,
            requirements_dir,
            no_deps=no_deps,
            ignore_hashes=ignore_hashes,
            allow_global=allow_global,
            extra_pip_args=extra_pip_args,
        )
    else:
        # Sort the dependencies out by index -- include editable/vcs in the default group
        deps_by_index = defaultdict(list)
        for dependency, pip_line in deps_to_install:
            index = project.sources_default["name"]
            if dependency.name and dependency.name in lockfile_section:
                entry = lockfile_section[dependency.name]
                if isinstance(entry, dict) and "index" in entry:
                    index = entry["index"]
            deps_by_index[index].append(pip_line)
        # Treat each index as its own pip install phase
        for index_name, dependencies in deps_by_index.items():
            try:
                install_source = next(filter(lambda s: s["name"] == index_name, sources))
                batch_install_iteration(
                    project,
                    dependencies,
                    [install_source],
                    procs,
                    requirements_dir,
                    no_deps=no_deps,
                    ignore_hashes=ignore_hashes,
                    allow_global=allow_global,
                    extra_pip_args=extra_pip_args,
                )
            except StopIteration:  # noqa: PERF203
                console.print(
                    f"Unable to find {index_name} in sources, please check dependencies: {dependencies}",
                    style="bold red",
                )
                sys.exit(1)


def _cleanup_procs(project, procs):
    while not procs.empty():
        c = procs.get()
        try:
            out, err = c.communicate()
        except AttributeError:
            out, err = c.stdout, c.stderr
        failed = c.returncode != 0
        if project.s.is_verbose():
            console.print(out.strip() or err.strip(), style="yellow")
        # The Installation failed...
        if failed:
            # The Installation failed...
            # We echo both c.stdout and c.stderr because pip returns error details on out.
            err = err.strip().splitlines() if err else []
            out = out.strip().splitlines() if out else []
            err_lines = [line for message in [out, err] for line in message]
            deps = getattr(c, "deps", {}).copy()
            # Return the subprocess' return code.
            raise exceptions.InstallError(deps, extra=err_lines)


def do_init(
    project,
    packages=None,
    allow_global=False,
    ignore_pipfile=False,
    system=False,
    deploy=False,
    pre=False,
    pypi_mirror=None,
    skip_lock=False,
    categories=None,
):
    """Initialize the project, ensuring that the Pipfile and Pipfile.lock are in place.
    Returns True if packages were updated + installed.
    """
    if not deploy and not ignore_pipfile:
        ensure_pipfile(project, system=system)

    handle_lockfile(
        project,
        packages,
        ignore_pipfile=ignore_pipfile,
        skip_lock=skip_lock,
        system=system,
        allow_global=allow_global,
        deploy=deploy,
        pre=pre,
        pypi_mirror=pypi_mirror,
        categories=categories,
    )

    if (
        not allow_global
        and not deploy
        and "PIPENV_ACTIVE" not in os.environ
        and not project.s.is_quiet()
    ):
        console.print(
            "To activate this project's virtualenv, run [yellow]pipenv shell[/yellow].\n"
            "Alternatively, run a command inside the virtualenv with [yellow]pipenv run[/yellow]."
        )
