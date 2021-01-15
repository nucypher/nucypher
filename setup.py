#!/usr/bin/env python3
# -*- coding: utf-8 -*-


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


import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from setuptools import find_packages, setup
from setuptools.command.develop import develop
from setuptools.command.install import install
from typing import Dict


#
# Metadata
#

PACKAGE_NAME = 'nucypher'
BASE_DIR = Path(__file__).parent
PYPI_CLASSIFIERS = [
      "Development Status :: 3 - Alpha",
      "Intended Audience :: Developers",
      "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
      "Natural Language :: English",
      "Operating System :: OS Independent",
      "Programming Language :: Python",
      "Programming Language :: Python :: 3 :: Only",
      "Programming Language :: Python :: 3.6",
      "Programming Language :: Python :: 3.7",
      "Programming Language :: Python :: 3.8",
      "Topic :: Security"
]

ABOUT: Dict[str, str] = dict()
SOURCE_METADATA_PATH = BASE_DIR / PACKAGE_NAME / "__about__.py"
with open(str(SOURCE_METADATA_PATH.resolve())) as f:
    exec(f.read(), ABOUT)


#
# Utilities
#

class VerifyVersionCommand(install):
    """Custom command to verify that the git tag matches our version"""
    description = 'verify that the git tag matches our version'

    def run(self):
        tag = os.getenv('CIRCLE_TAG')
        if tag.startswith('v'):
            tag = tag[1:]

        version = ABOUT['__version__']
        if version.startswith('v'):
            version = version[1:]

        if tag != version:
            info = "Git tag: {0} does not match the version of this app: {1}".format(
                os.getenv('CIRCLE_TAG'), ABOUT['__version__']
            )
            sys.exit(info)


class PostDevelopCommand(develop):
    """
    Post-installation for development mode.
    Execute manually with python setup.py develop or automatically included with
    `pip install -e . -r dev-requirements.txt`.
    """
    def run(self):
        """development setup scripts (pre-requirements)"""
        develop.run(self)
        subprocess.call(f"scripts/installation/install_solc.py")


#
#  Requirements
#

def read_requirements(path):
    with open(os.path.join(BASE_DIR, path)) as f:
        _pipenv_flags, *lines = f.read().split('\n')

    # TODO remove when will be no more git dependencies in requirements.txt
    # Transforms VCS requirements to PEP 508
    requirements = []
    for line in lines:
        if line.startswith('-e git:') or line.startswith('-e git+') or \
                line.startswith('git:') or line.startswith('git+'):
            # parse out egg=... fragment from VCS URL
            parsed = urlparse(line)
            egg_name = parsed.fragment.partition("egg=")[-1]
            without_fragment = parsed._replace(fragment="").geturl()
            requirements.append(f"{egg_name} @ {without_fragment}")
        else:
            requirements.append(line)

    return requirements


INSTALL_REQUIRES = read_requirements('requirements.txt')
DEV_REQUIRES = read_requirements('dev-requirements.txt')

BENCHMARK_REQUIRES = [
    'pytest-benchmark'
]

DEPLOY_REQUIRES = [
    'bumpversion',
    'ansible',
    'twine'
]

URSULA_REQUIRES = ['prometheus_client', 'sentry-sdk']  # TODO: Consider renaming to 'monitor', etc.
ALICE_REQUIRES = ['qrcode']
BOB_REQUIRES = ['qrcode']

EXTRAS = {

    # Admin
    'dev': DEV_REQUIRES + URSULA_REQUIRES + ALICE_REQUIRES,
    'benchmark': DEV_REQUIRES + BENCHMARK_REQUIRES,
    'deploy': DEPLOY_REQUIRES,

    # User
    'ursula': URSULA_REQUIRES,
    'alice': ALICE_REQUIRES,
    'bob': BOB_REQUIRES
}


setup(

    # Requirements
    python_requires='>=3',
    setup_requires=['setuptools-markdown'],
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS,

    # Package Data
    packages=find_packages(exclude=["tests", "scripts"]),
    include_package_data=True,
    zip_safe=False,

    # Entry Points
    entry_points={'console_scripts': [
      'nucypher = nucypher.cli.main:nucypher_cli',
      'nucypher-deploy = nucypher.cli.commands.deploy:deploy',
    ]},

    # setup.py commands
    cmdclass={
        'verify': VerifyVersionCommand,
        'develop': PostDevelopCommand
    },

    # Metadata
    name=ABOUT['__title__'],
    url=ABOUT['__url__'],
    version=ABOUT['__version__'],
    author=ABOUT['__author__'],
    author_email=ABOUT['__email__'],
    description=ABOUT['__summary__'],
    license=ABOUT['__license__'],
    long_description_content_type="text/markdown",
    long_description_markdown_filename='README.md',
    keywords="nucypher, proxy re-encryption",
    classifiers=PYPI_CLASSIFIERS
)
