from setuptools import setup, find_packages

version = '0.1'

INSTALL_REQUIRES = [
        'appdirs',
        'populus'
]

TESTS_REQUIRE = [
    'pytest',
    'pdbpp',
]

setup(
    name="nkms_eth",
    version=version,
    packages=find_packages(),
    package_data={'nkms_eth': [
        'project/*', 'project/contracts/*',
        'project/contracts/lib/*',
        'project/contracts/zepellin/math/*',
        'project/contracts/zepellin/ownership/*',
        'project/contracts/zepellin/token/*']},
    include_package_data=True,
    zip_safe=False,
    install_requires=INSTALL_REQUIRES,
    extras_require={'testing': TESTS_REQUIRE},
)
