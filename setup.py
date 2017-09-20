from setuptools import setup, find_packages

INSTALL_REQUIRES = [
        'kademlia>=1.0',
        'rpcudp>=3.0',
        'lmdb',
        'pynacl',
        'npre',
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
        'https://github.com/nucypher/nucypher-pre-python/archive/0.3.tar.gz#egg=npre-0.3']

setup(name='nkms',
      version='0.1',
      description='NuCypher decentralized KMS',
      install_requires=INSTALL_REQUIRES,
      dependency_links=LINKS,
      extras_require={'testing': TESTS_REQUIRE},
      packages=find_packages())
