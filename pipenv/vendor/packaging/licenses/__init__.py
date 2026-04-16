#######################################################################################
#
# Adapted from:
#  https://github.com/pypa/hatch/blob/5352e44/backend/src/hatchling/licenses/parse.py
#
# MIT License
#
# Copyright (c) 2017-present Ofek Lev <oss@ofek.dev>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be included in all copies
# or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#
# With additional allowance of arbitrary `LicenseRef-` identifiers, not just
# `LicenseRef-Public-Domain` and `LicenseRef-Proprietary`.
#
#######################################################################################
from __future__ import annotations

import re
from typing import NewType, cast

from ._spdx import EXCEPTIONS, LICENSES

__all__ = [
    "InvalidLicenseExpression",
    "NormalizedLicenseExpression",
    "canonicalize_license_expression",
]

license_ref_allowed = re.compile("^[A-Za-z0-9.-]*$")

NormalizedLicenseExpression = NewType("NormalizedLicenseExpression", str)


class InvalidLicenseExpression(ValueError):
    """Raised when a license-expression string is invalid

    >>> canonicalize_license_expression("invalid")
    Traceback (most recent call last):
        ...
    packaging.licenses.InvalidLicenseExpression: Invalid license expression: 'invalid'
    """


def canonicalize_license_expression(
    raw_license_expression: str,
) -> NormalizedLicenseExpression:
    pass
