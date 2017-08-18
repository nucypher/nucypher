from distutils.core import setup

INSTALL_REQUIRES = [
        'kademlia>=1.0',
        'rpcudp>=3.0']

setup(name='nkms',
      version='0.1',
      description='NuCypher decentralized KMS',
      install_requires=INSTALL_REQUIRES,
      packages=['nkms'])
