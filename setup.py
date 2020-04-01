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
import sys

from setuptools import setup, find_packages
from setuptools.command.install import install


#
# Metadata
#

PACKAGE_NAME = 'nucypher'
BASE_DIR = os.path.dirname(__file__)

ABOUT = dict()
with open(os.path.join(BASE_DIR, PACKAGE_NAME, "__about__.py")) as f:
    exec(f.read(), ABOUT)

with open(os.path.join(BASE_DIR, "README.md")) as f:
    long_description = f.read()


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


#
#  Dependencies
#

with open(os.path.join(BASE_DIR, "requirements.txt")) as f:
    _PIP_FLAGS, *INSTALL_REQUIRES = f.read().split('\n')


TESTS_REQUIRE = [
    'pytest',
    'pytest-xdist',
    'pytest-mypy',
    'pytest-twisted',
    'pytest-cov',
    'mypy',
    'codecov',
    'coverage',
]

DEPLOY_REQUIRES = [
    'bumpversion',
    'ansible',
]

DOCS_REQUIRE = [
    'sphinx',
    'sphinx-autobuild',
    'recommonmark',
    'aafigure',
    'sphinx_rtd_theme'
]

BENCHMARKS_REQUIRE = [
    'pytest-benchmark'
]

EXTRAS_REQUIRE = {'development': TESTS_REQUIRE,
                  'deployment': DEPLOY_REQUIRES,
                  'docs': DOCS_REQUIRE,
                  'benchmark': BENCHMARKS_REQUIRE}

PACKAGE_DATA = ['network/templates/basic_status.j2',
                'network/nicknames/web_colors.json',
                'blockchain/eth/contract_registry/mainnet/*',
                'blockchain/eth/contract_registry/cassandra/*',
                'blockchain/eth/contract_registry/gemini/*',
                'blockchain/eth/contract_registry/frances/*',
                'blockchain/eth/contract_registry/miranda/*',
                'blockchain/eth/sol/source/contracts/*',
                'blockchain/eth/sol/source/contracts/lib/*',
                'blockchain/eth/sol/source/contracts/proxy/*',
                'blockchain/eth/sol/source/zeppelin/math/*',
                'blockchain/eth/sol/source/zeppelin/utils/*',
                'blockchain/eth/sol/source/zeppelin/ownership/*',
                'blockchain/eth/sol/source/zeppelin/token/ERC20/*']

setup(name=ABOUT['__title__'],
      url=ABOUT['__url__'],
      version=ABOUT['__version__'],
      author=ABOUT['__author__'],
      author_email=ABOUT['__email__'],
      description=ABOUT['__summary__'],
      license=ABOUT['__license__'],
      long_description=long_description,
      long_description_content_type="text/markdown",

      # Setup
      python_requires='>=3',
      setup_requires=['pytest-runner'],  # required for `setup.py test`
      tests_require=TESTS_REQUIRE,
      install_requires=INSTALL_REQUIRES,
      extras_require=EXTRAS_REQUIRE,

      # Package Data
      packages=find_packages(exclude=["tests"]),
      package_data={PACKAGE_NAME: PACKAGE_DATA},
      include_package_data=True,

      # Entry Points
      entry_points={'console_scripts': [
          f'{PACKAGE_NAME} = {PACKAGE_NAME}.cli.main:nucypher_cli',
          f'{PACKAGE_NAME}-deploy = {PACKAGE_NAME}.cli.commands.deploy:deploy',
      ]},
      cmdclass={'verify': VerifyVersionCommand},

      # Metadata
      classifiers=[
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
      ])
