import re
import sys

from pipenv.utils.dependencies import get_lockfile_section_using_pipfile_category
from pipenv.utils.requirements import (
    requirements_from_lockfile,
    requirements_from_pipfile,
)


def generate_requirements(
    project,
    dev=False,
    dev_only=False,
    include_hashes=False,
    include_markers=True,
    categories="",
    from_pipfile=False,
    no_lock=False,
    include_index=True,
):
    # If --no-lock, generate from Pipfile directly without using lockfile versions
    pass


def _generate_requirements_from_pipfile(
    project,
    dev=False,
    dev_only=False,
    include_markers=True,
    categories="",
    include_index=True,
):
    """Generate requirements directly from Pipfile using flexible version specifiers.

    This is useful for libraries that need looser version constraints than
    the strictly pinned versions in Pipfile.lock.
    """
    pass
