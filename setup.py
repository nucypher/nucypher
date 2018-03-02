from setuptools import setup, find_packages

version = '0.1'


setup(
    name="nkms_eth",
    version=version,
    package_data={'nkms_eth': [
        'project/*', 'project/contracts/*',
        'project/contracts/lib/*',
        'project/contracts/zepellin/math/*',
        'project/contracts/zepellin/ownership/*',
        'project/contracts/zepellin/token/*']},
    include_package_data=True,
    zip_safe=False,
)
