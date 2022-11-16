#!/usr/bin/env python3

"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

# Towncrier silently ignores files that do not match the expected ending.
# We use this script to ensure we catch these as errors in CI.

import pathlib


class InvalidNewsFragment(RuntimeError):
    pass


ALLOWED_EXTENSIONS = {
    ".feature.rst",
    ".bugfix.rst",
    ".doc.rst",
    ".removal.rst",
    ".misc.rst",
    ".dev.rst",
}

ALLOWED_FILES = {
    'validate_files.py',
    'README.md',
    '.gitignore'
}

THIS_DIR = pathlib.Path(__file__).parent

for fragment_file in THIS_DIR.iterdir():

    if fragment_file.name in ALLOWED_FILES:
        continue

    full_extension = "".join(fragment_file.suffixes)
    if full_extension not in ALLOWED_EXTENSIONS:
        raise InvalidNewsFragment(f"Unexpected newsfragment file: {fragment_file}")
