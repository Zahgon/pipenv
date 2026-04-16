import sys
from optparse import Values

from pipenv.patched.pip._internal.cli import cmdoptions
from pipenv.patched.pip._internal.cli.base_command import Command
from pipenv.patched.pip._internal.cli.status_codes import SUCCESS
from pipenv.patched.pip._internal.operations.freeze import freeze
from pipenv.patched.pip._internal.utils.compat import stdlib_pkgs


def _should_suppress_build_backends() -> bool:
    return sys.version_info < (3, 12)


def _dev_pkgs() -> set[str]:
    pkgs = {"pip"}

    if _should_suppress_build_backends():
        pkgs |= {"setuptools", "distribute", "wheel"}

    return pkgs


class FreezeCommand(Command):
    """
    Output installed packages in requirements format.

    packages are listed in a case-insensitive sorted order.
    """

    ignore_require_venv = True
    usage = """
      %prog [options]"""

    def add_options(self) -> None:
        pass

    def run(self, options: Values, args: list[str]) -> int:
        skip = set(stdlib_pkgs)
        if not options.freeze_all:
            skip.update(_dev_pkgs())

        if options.excludes:
            skip.update(options.excludes)

        cmdoptions.check_list_path_option(options)

        for line in freeze(
            requirement=options.requirements,
            local_only=options.local,
            user_only=options.user,
            paths=options.path,
            isolated=options.isolated_mode,
            skip=skip,
            exclude_editable=options.exclude_editable,
        ):
            sys.stdout.write(line + "\n")
        return SUCCESS
