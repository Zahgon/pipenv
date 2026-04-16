"""This is invoked in a subprocess to call the build backend hooks.

It expects:
- Command line args: hook_name, control_dir
- Environment variables:
      _PYPROJECT_HOOKS_BUILD_BACKEND=entry.point:spec
      _PYPROJECT_HOOKS_BACKEND_PATH=paths (separated with os.pathsep)
- control_dir/input.json:
  - {"kwargs": {...}}

Results:
- control_dir/output.json
  - {"return_val": ...}
"""
import json
import os
import os.path
import re
import shutil
import sys
import traceback
from glob import glob
from importlib import import_module
from importlib.machinery import PathFinder
from os.path import join as pjoin

# This file is run as a script, and `import wrappers` is not zip-safe, so we
# include write_json() and read_json() from wrappers.py.


def write_json(obj, path, **kwargs):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, **kwargs)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class BackendUnavailable(Exception):
    """Raised if we cannot import the backend"""

    def __init__(self, message, traceback=None):
        super().__init__(message)
        self.message = message
        self.traceback = traceback


class HookMissing(Exception):
    """Raised if a hook is missing and we are not executing the fallback"""

    def __init__(self, hook_name=None):
        super().__init__(hook_name)
        self.hook_name = hook_name


def _build_backend():
    """Find and load the build backend"""
    backend_path = os.environ.get("_PYPROJECT_HOOKS_BACKEND_PATH")
    ep = os.environ["_PYPROJECT_HOOKS_BUILD_BACKEND"]
    mod_path, _, obj_path = ep.partition(":")

    if backend_path:
        # Ensure in-tree backend directories have the highest priority when importing.
        extra_pathitems = backend_path.split(os.pathsep)
        sys.meta_path.insert(0, _BackendPathFinder(extra_pathitems, mod_path))

    try:
        obj = import_module(mod_path)
    except ImportError:
        msg = f"Cannot import {mod_path!r}"
        raise BackendUnavailable(msg, traceback.format_exc())

    if obj_path:
        for path_part in obj_path.split("."):
            obj = getattr(obj, path_part)
    return obj


class _BackendPathFinder:
    """Implements the MetaPathFinder interface to locate modules in ``backend-path``.

    Since the environment provided by the frontend can contain all sorts of
    MetaPathFinders, the only way to ensure the backend is loaded from the
    right place is to prepend our own.
    """

    def __init__(self, backend_path, backend_module):
        self.backend_path = backend_path
        self.backend_module = backend_module
        self.backend_parent, _, _ = backend_module.partition(".")

    def find_spec(self, fullname, _path, _target=None):
        pass

    if sys.version_info >= (3, 8):

        def find_distributions(self, context=None):
            # Delayed import: Python 3.7 does not contain importlib.metadata
            pass


def _supported_features():
    """Return the list of options features supported by the backend.

    Returns a list of strings.
    The only possible value is 'build_editable'.
    """
    pass


def get_requires_for_build_wheel(config_settings):
    """Invoke the optional get_requires_for_build_wheel hook

    Returns [] if the hook is not defined.
    """
    backend = _build_backend()
    try:
        hook = backend.get_requires_for_build_wheel
    except AttributeError:
        return []
    else:
        return hook(config_settings)


def get_requires_for_build_editable(config_settings):
    """Invoke the optional get_requires_for_build_editable hook

    Returns [] if the hook is not defined.
    """
    backend = _build_backend()
    try:
        hook = backend.get_requires_for_build_editable
    except AttributeError:
        return []
    else:
        return hook(config_settings)


def prepare_metadata_for_build_wheel(
    metadata_directory, config_settings, _allow_fallback
):
    """Invoke optional prepare_metadata_for_build_wheel

    Implements a fallback by building a wheel if the hook isn't defined,
    unless _allow_fallback is False in which case HookMissing is raised.
    """
    pass


def prepare_metadata_for_build_editable(
    metadata_directory, config_settings, _allow_fallback
):
    """Invoke optional prepare_metadata_for_build_editable

    Implements a fallback by building an editable wheel if the hook isn't
    defined, unless _allow_fallback is False in which case HookMissing is
    raised.
    """
    pass


WHEEL_BUILT_MARKER = "PYPROJECT_HOOKS_ALREADY_BUILT_WHEEL"


def _dist_info_files(whl_zip):
    """Identify the .dist-info folder inside a wheel ZipFile."""
    pass


def _get_wheel_metadata_from_wheel(whl_basename, metadata_directory, config_settings):
    """Extract the metadata from a wheel.

    Fallback for when the build backend does not
    define the 'get_wheel_metadata' hook.
    """
    pass


def _find_already_built_wheel(metadata_directory):
    """Check for a wheel already built during the get_wheel_metadata hook."""
    pass


def build_wheel(wheel_directory, config_settings, metadata_directory=None):
    """Invoke the mandatory build_wheel hook.

    If a wheel was already built in the
    prepare_metadata_for_build_wheel fallback, this
    will copy it rather than rebuilding the wheel.
    """
    pass


def build_editable(wheel_directory, config_settings, metadata_directory=None):
    """Invoke the optional build_editable hook.

    If a wheel was already built in the
    prepare_metadata_for_build_editable fallback, this
    will copy it rather than rebuilding the wheel.
    """
    pass


def get_requires_for_build_sdist(config_settings):
    """Invoke the optional get_requires_for_build_wheel hook

    Returns [] if the hook is not defined.
    """
    pass


class _DummyException(Exception):
    """Nothing should ever raise this exception"""


class GotUnsupportedOperation(Exception):
    """For internal use when backend raises UnsupportedOperation"""

    def __init__(self, traceback):
        self.traceback = traceback


def build_sdist(sdist_directory, config_settings):
    """Invoke the mandatory build_sdist hook."""
    pass


HOOK_NAMES = {
    "get_requires_for_build_wheel",
    "prepare_metadata_for_build_wheel",
    "build_wheel",
    "get_requires_for_build_editable",
    "prepare_metadata_for_build_editable",
    "build_editable",
    "get_requires_for_build_sdist",
    "build_sdist",
    "_supported_features",
}


def main():
    if len(sys.argv) < 3:
        sys.exit("Needs args: hook_name, control_dir")
    hook_name = sys.argv[1]
    control_dir = sys.argv[2]
    if hook_name not in HOOK_NAMES:
        sys.exit("Unknown hook: %s" % hook_name)

    # Remove the parent directory from sys.path to avoid polluting the backend
    # import namespace with this directory.
    here = os.path.dirname(__file__)
    if here in sys.path:
        sys.path.remove(here)

    hook = globals()[hook_name]

    hook_input = read_json(pjoin(control_dir, "input.json"))

    json_out = {"unsupported": False, "return_val": None}
    try:
        json_out["return_val"] = hook(**hook_input["kwargs"])
    except BackendUnavailable as e:
        json_out["no_backend"] = True
        json_out["traceback"] = e.traceback
        json_out["backend_error"] = e.message
    except GotUnsupportedOperation as e:
        json_out["unsupported"] = True
        json_out["traceback"] = e.traceback
    except HookMissing as e:
        json_out["hook_missing"] = True
        json_out["missing_hook_name"] = e.hook_name or hook_name

    write_json(json_out, pjoin(control_dir, "output.json"), indent=2)


if __name__ == "__main__":
    main()
