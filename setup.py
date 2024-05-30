#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from pathlib import Path
from typing import Dict

from setuptools import find_namespace_packages, setup

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
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Security",
]

ABOUT: Dict[str, str] = dict()
SOURCE_METADATA_PATH = BASE_DIR / PACKAGE_NAME / "__about__.py"
with open(str(SOURCE_METADATA_PATH.resolve())) as f:
    exec(f.read(), ABOUT)


def read_requirements(path):
    with open(BASE_DIR / path) as f:
        return f.read().split("\n")


INSTALL_REQUIRES = read_requirements("requirements.txt")
DEV_REQUIRES = read_requirements("dev-requirements.txt")

EXTRAS = {
    "dev": DEV_REQUIRES,
}

# read the contents of your README file
long_description = (Path(__file__).parent / "README.md").read_text()

setup(

    # Requirements
    python_requires='>=3',
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS,

    # Package Data
    packages=find_namespace_packages(
        exclude=["scripts", "nucypher.utilities.templates"]
    ),
    include_package_data=True,
    zip_safe=True,

    # Entry Points
    entry_points={
        'console_scripts': [
            'nucypher = nucypher.cli.main:nucypher_cli',
        ],
        'pytest11': [
            "pytest-nucypher = tests.fixtures"
        ]
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
    long_description=long_description,
    keywords="threshold access control, distributed key generation",
    classifiers=PYPI_CLASSIFIERS,
)
