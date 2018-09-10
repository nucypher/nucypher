import os

from click.testing import CliRunner
from pyfakefs.fake_filesystem_unittest import Patcher

from cli.main import cli


def test_file_system_isolation(fs):
    # "fs" is the reference to the fake file system
    fs.create_file('/var/data/xx1.txt')
    assert os.path.exists('/var/data/xx1.txt'), 'Filesystem is not isolated'

    with Patcher() as patcher:
        # access the fake_filesystem object via patcher.fs
        patcher.fs.create_file('/foo/bar', contents='test')

        # the following code works on the fake filesystem
        with open('/foo/bar') as f:
            contents = f.read()
            assert contents == 'test', 'Filesystem is not isolated'


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'], catch_exceptions=False)

    assert result.exit_code == 0
    assert 'Usage: cli [OPTIONS] COMMAND [ARGS]' in result.output, 'Missing or invalid help text was produced.'
