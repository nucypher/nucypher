from distutils.core import setup

INSTALL_REQUIRES = [
        'kademlia>=1.0',
        'rpcudp>=3.0']

TESTS_REQUIRE = [
    'pytest',
    'coverage',
    'pytest-cov',
    'pdbpp',
]

# should add --process-dependency-links to pip
LINKS = [
        'https://github.com/bmuller/kademlia/archive/python3.5.tar.gz#egg=kademlia-1.0',
        'https://github.com/bmuller/rpcudp/archive/python3.5.tar.gz#egg=rpcudp-3.0.0']

setup(name='nkms',
      version='0.1',
      description='NuCypher decentralized KMS',
      install_requires=INSTALL_REQUIRES,
      dependency_links=LINKS,
      extras_require={'testing': TESTS_REQUIRE},
      packages=['nkms'])
