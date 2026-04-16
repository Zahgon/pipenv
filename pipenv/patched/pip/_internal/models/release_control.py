from __future__ import annotations

from dataclasses import dataclass, field

from pipenv.patched.pip._vendor.packaging.utils import NormalizedName, canonicalize_name

from pipenv.patched.pip._internal.exceptions import CommandError


# TODO: add slots=True when Python 3.9 is dropped
@dataclass
class ReleaseControl:
    """Helper for managing which release types can be installed."""

    all_releases: set[str] = field(default_factory=set)
    only_final: set[str] = field(default_factory=set)
    _order: list[tuple[str, str]] = field(
        init=False, default_factory=list, compare=False, repr=False
    )

    def handle_mutual_excludes(
        self, value: str, target: set[str], other: set[str], attr_name: str
    ) -> None:
        """Parse and apply release control option value.

        Processes comma-separated package names or special values `:all:` and `:none:`.

        When adding packages to target, they're removed from other to maintain mutual
        exclusivity between all_releases and only_final. All operations are tracked in
        order so that the original command-line argument sequence can be reconstructed
        when passing options to build subprocesses.
        """
        pass

    def get_ordered_args(self) -> list[tuple[str, str]]:
        """
        Get ordered list of (flag_name, value) tuples for reconstructing CLI args.

        Returns:
            List of tuples where each tuple is (attribute_name, value).
            The attribute_name is either 'all_releases' or 'only_final'.

        Example:
            [("all_releases", ":all:"), ("only_final", "simple")]
            would be reconstructed as:
            ["--all-releases", ":all:", "--only-final", "simple"]
        """
        return self._order[:]

    def allows_prereleases(self, canonical_name: NormalizedName) -> bool | None:
        """
        Determine if pre-releases are allowed for a package.

        Returns:
            True: Pre-releases are allowed (package in all_releases)
            False: Only final releases allowed (package in only_final)
            None: No specific setting, use default behavior
        """
        if canonical_name in self.all_releases:
            return True
        elif canonical_name in self.only_final:
            return False
        elif ":all:" in self.all_releases:
            return True
        elif ":all:" in self.only_final:
            return False
        return None
