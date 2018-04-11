from setuptools import setup, find_packages

VERSION = '0.1'

INSTALL_REQUIRES = [
        'kademlia>=1.0',
        'rpcudp>=3.0',
        'lmdb',
        'pynacl',
        'pysha3==1.0.2',
        'bidict',
]

TESTS_REQUIRE = [
    'pytest',
    'coverage',
    'pytest-cov',
    'pdbpp',
    'ipython',
    'appdirs'
]

# should add --process-dependency-links to pip
LINKS = [
        'https://github.com/nucypher/kademlia/archive/kms-dependency.tar.gz#egg=kademlia-1.0',
        'https://github.com/bmuller/rpcudp/archive/python3.5.tar.gz#egg=rpcudp-3.0.0',
]

setup(name='nkms',
      version=VERSION,
      description='NuCypher decentralized KMS',
      install_requires=INSTALL_REQUIRES,
      dependency_links=LINKS,
      extras_require={'testing': TESTS_REQUIRE},
      packages=find_packages(),
      package_data={'nkms': [
          'blockchain/eth/*', 'project/contracts/*',
          'blockchain/eth/sol_source/contracts/lib/*',
          'blockchain/eth/sol_source/contracts/zepellin/math/*',
          'blockchain/eth/sol_source/contracts/zepellin/ownership/*',
          'blockchain/eth/sol_source/contracts/zepellin/token/*']},
      include_package_data=True,
)
