#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
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

INSTALL_REQUIRES = [

    # NuCypher
    'umbral',
    'constant-sorrow',
    'bytestringSplitter',
    'hendrix>=3.1.0',

    # Third Party (General)
    'cryptography>=2.3',
    'pysha3',
    'requests',
    'sqlalchemy',
    'apistar<0.6.0',
    'tzlocal<2.0.0',
    'maya',

    # Third Party (Ethereum)
    'eth-utils==1.2.2',
    'eth-keys',
    'eth-tester>=0.1.0b33',
    'py-evm>=0.2.0a33',
    'py-solc',
    'web3',

    # Third Party (Configuration + CLI)
    'appdirs',
    'click>=7.0',
    'colorama',
    'sentry-sdk==0.5.2',
    'boto3',

]

TESTS_REQUIRE = [
    'pytest',
    'pytest-xdist'
    'pytest-mypy',
    'pytest-twisted',
    'pytest-cov',
    'mypy',
    'codecov',
    'coverage',
    'moto'
]

DEPLOY_REQUIRES = [
    'bumpversion',
    'ansible',
]

DOCS_REQUIRE = [
    'sphinx',
    'sphinx-autobuild'
]

BENCHMARKS_REQUIRE = [
    'pytest-benchmark'
]

EXTRAS_REQUIRE = {'testing': TESTS_REQUIRE,
                  'deployment': DEPLOY_REQUIRES,
                  'docs': DOCS_REQUIRE,
                  'benchmark': BENCHMARKS_REQUIRE}

setup(name=ABOUT['__title__'],
      url=ABOUT['__url__'],
      version=ABOUT['__version__'],
      author=ABOUT['__author__'],
      author_email=ABOUT['__email__'],
      description=ABOUT['__summary__'],
      license=ABOUT['__license__'],
      long_description=long_description,

      install_requires=INSTALL_REQUIRES,
      extras_require=EXTRAS_REQUIRE,

      packages=find_packages(exclude=["tests"]),
      package_data={PACKAGE_NAME: [
          'network/templates/basic_status.j2',
          'network/nicknames/web_colors.json',
          'blockchain/eth/sol/source/contracts/*',
          'blockchain/eth/sol/source/contracts/lib/*',
          'blockchain/eth/sol/source/contracts/proxy/*',
          'blockchain/eth/sol/source/zepellin/math/*',
          'blockchain/eth/sol/source/zepellin/ownership/*',
          'blockchain/eth/sol/source/zepellin/token/*']},
      include_package_data=True,

      entry_points={'console_scripts': ['{0}={0}.cli:cli'.format(PACKAGE_NAME)]},
      cmdclass={'verify': VerifyVersionCommand},

      classifiers=[
          "Development Status :: 2 - Pre-Alpha",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
          "Natural Language :: English",
          "Operating System :: OS Independent",
          "Programming Language :: Python",
          "Programming Language :: Python :: 3 :: Only",
          "Programming Language :: Python :: 3.5",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: 3.7",
          "Programming Language :: Python :: 3.8",
          "Topic:: Security"],
      python_requires='>=3'
      )
