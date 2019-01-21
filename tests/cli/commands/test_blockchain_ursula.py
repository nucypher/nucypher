from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MIN_ALLOWED_LOCKED
from nucypher.cli.main import nucypher_cli
from nucypher.utilities.sandbox.constants import MOCK_IP_ADDRESS, TEST_PROVIDER_URI


def test_run_geth_development_ursula(click_runner, deployed_blockchain):
    blockchain, deployer_address = deployed_blockchain

    run_args = ('ursula', 'run',
                '--dev',
                '--debug',
                '--lonely',
                '--poa',
                '--dry-run',
                '--provider-uri', TEST_PROVIDER_URI,
                '--rest-host', MOCK_IP_ADDRESS,
                '--checksum-address', deployer_address)

    result = click_runner.invoke(nucypher_cli, run_args, catch_exceptions=False)
    assert result.exit_code == 0


def test_init_ursula_stake(click_runner, deployed_blockchain):
    blockchain, deployer_address = deployed_blockchain

    stake_args = ('ursula', 'stake',
                  '--value', MIN_ALLOWED_LOCKED,
                  '--duration', MIN_LOCKED_PERIODS,
                  '--dev',
                  '--poa',
                  '--force',
                  '--provider-uri', TEST_PROVIDER_URI,
                  '--rest-host', MOCK_IP_ADDRESS,
                  '--checksum-address', deployer_address)

    result = click_runner.invoke(nucypher_cli, stake_args, catch_exceptions=False)
    assert result.exit_code == 0

    # Examine the stake on the blockchain
    miner = Miner(checksum_address=deployer_address, is_me=True, blockchain=blockchain)
    assert len(miner.stakes) == 1
    stake = miner.stakes[0]
    start, end, value = stake
    assert (abs(end-start)+1) == MIN_LOCKED_PERIODS
    assert value == MIN_ALLOWED_LOCKED


def test_list_ursula_stakes(click_runner, deployed_blockchain):
    blockchain, _deployer_address = deployed_blockchain
    deployer_address, staking_participant, *everyone_else = blockchain.interface.w3.eth.accounts

    stake_args = ('ursula', 'stake', '--list',
                  '--checksum-address', deployer_address,
                  '--dev',
                  '--poa',
                  '--provider-uri', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli, stake_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(MIN_ALLOWED_LOCKED) in result.output
