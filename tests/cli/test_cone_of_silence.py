from nucypher.cli.cone_of_silence import cone_of_silence


def test_cone_of_silence_start(click_runner):
    args = ('start')

    result = click_runner.invoke(cone_of_silence, args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Starting..." in result.output


def test_cone_of_silence_stop(click_runner):
    args = ('stop')

    result = click_runner.invoke(cone_of_silence, args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Stopping..." in result.output
