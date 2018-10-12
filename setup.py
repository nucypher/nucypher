from setuptools import setup, find_packages

VERSION = '0.1'


# NOTE: Use Pipfile & Pipfile.lock to manage dependencies\
INSTALL_REQUIRES = []
TESTS_REQUIRE = []

setup(name='nucypher',
      version=VERSION,
      description='A proxy re-encryption network to empower privacy in decentralized systems.',
      install_requires=INSTALL_REQUIRES,
      extras_require={'testing': TESTS_REQUIRE},
      packages=find_packages(),
      package_data={'nucypher': [
          'blockchain/eth/*', 'project/contracts/*',
          'blockchain/eth/sol_source/contracts/lib/*',
          'blockchain/eth/sol_source/contracts/zepellin/math/*',
          'blockchain/eth/sol_source/contracts/zepellin/ownership/*',
          'blockchain/eth/sol_source/contracts/zepellin/token/*']},
      include_package_data=True,
      entry_points='''
                   [console_scripts]
                   nucypher=cli.main:cli
                   '''
      )
