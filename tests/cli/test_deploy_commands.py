import os

from nucypher.blockchain.eth.agents import (
    PolicyManagerAgent,
    StakingEscrowAgent,
    AdjudicatorAgent,
    ContractAgency
)
from nucypher.blockchain.eth.constants import (
    NUCYPHER_TOKEN_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME,
    POLICY_MANAGER_CONTRACT_NAME,
    ADJUDICATOR_CONTRACT_NAME,
    DISPATCHER_CONTRACT_NAME
)
from nucypher.blockchain.eth.deployers import StakingEscrowDeployer
from nucypher.blockchain.eth.registry import LocalContractRegistry, InMemoryContractRegistry
from nucypher.cli.commands.deploy import deploy
from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
    INSECURE_DEVELOPMENT_PASSWORD,
)

ALTERNATE_REGISTRY_FILEPATH = '/tmp/nucypher-test-registry-alternate.json'
ALTERNATE_REGISTRY_FILEPATH_2 = '/tmp/nucypher-test-registry-alternate-2.json'


def test_nucypher_deploy_inspect_no_deployments(click_runner, testerchain, new_local_registry):

    status_command = ('inspect',
                      '--provider', TEST_PROVIDER_URI,
                      '--registry-infile', new_local_registry.filepath)

    result = click_runner.invoke(deploy, status_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert 'not enrolled' in result.output


def test_set_range(click_runner, testerchain, agency_local_registry):

    minimum, default, maximum = 10, 20, 30
    status_command = ('set-range',
                      '--provider', TEST_PROVIDER_URI,
                      '--registry-infile', agency_local_registry.filepath,
                      '--minimum', minimum,
                      '--default', default,
                      '--maximum', maximum)

    account_index = '0\n'
    yes = 'Y\n'
    user_input = account_index + yes + yes
    result = click_runner.invoke(deploy,
                                 status_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert f"range [{minimum}, {maximum}]" in result.output
    assert f"default value {default}" in result.output


def test_nucypher_deploy_inspect_fully_deployed(click_runner, agency_local_registry):

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=agency_local_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=agency_local_registry)

    status_command = ('inspect',
                      '--registry-infile', agency_local_registry.filepath,
                      '--provider', TEST_PROVIDER_URI)

    result = click_runner.invoke(deploy,
                                 status_command,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staking_agent.owner in result.output
    assert policy_agent.owner in result.output
    assert adjudicator_agent.owner in result.output

    minimum, default, maximum = 10, 20, 30
    assert 'Range' in result.output
    assert f"{minimum} wei" in result.output
    assert f"{default} wei" in result.output
    assert f"{maximum} wei" in result.output


def test_transfer_ownership(click_runner, testerchain, agency_local_registry):

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=agency_local_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=agency_local_registry)

    assert staking_agent.owner == testerchain.etherbase_account
    assert policy_agent.owner == testerchain.etherbase_account
    assert adjudicator_agent.owner == testerchain.etherbase_account

    maclane = testerchain.unassigned_accounts[0]

    ownership_command = ('transfer-ownership',
                         '--registry-infile', agency_local_registry.filepath,
                         '--provider', TEST_PROVIDER_URI,
                         '--target-address', maclane)

    account_index = '0\n'
    yes = 'Y\n'
    user_input = account_index + yes + yes

    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    assert staking_agent.owner == maclane
    assert policy_agent.owner == maclane
    assert adjudicator_agent.owner == maclane

    michwill = testerchain.unassigned_accounts[1]

    ownership_command = ('transfer-ownership',
                         '--deployer-address', maclane,
                         '--contract-name', STAKING_ESCROW_CONTRACT_NAME,
                         '--registry-infile', agency_local_registry.filepath,
                         '--provider', TEST_PROVIDER_URI,
                         '--target-address', michwill)

    user_input = yes
    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staking_agent.owner != maclane
    assert staking_agent.owner == michwill


def test_bare_contract_deployment_to_alternate_registry(click_runner, agency_local_registry):

    if os.path.exists(ALTERNATE_REGISTRY_FILEPATH):
        os.remove(ALTERNATE_REGISTRY_FILEPATH)
    assert not os.path.exists(ALTERNATE_REGISTRY_FILEPATH)

    command = ('contracts',
               '--contract-name', StakingEscrowDeployer.contract_name,
               '--mode', 'bare',
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', agency_local_registry.filepath,
               '--registry-outfile', ALTERNATE_REGISTRY_FILEPATH,
               '--ignore-deployed')

    user_input = '0\n' + 'Y\n' + 'DEPLOY'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Verify alternate registry output
    assert os.path.exists(agency_local_registry.filepath)
    assert os.path.exists(ALTERNATE_REGISTRY_FILEPATH)
    new_registry = LocalContractRegistry(filepath=ALTERNATE_REGISTRY_FILEPATH)
    assert agency_local_registry != new_registry

    old_enrolled_names = list(agency_local_registry.enrolled_names).count(StakingEscrowDeployer.contract_name)
    new_enrolled_names = list(new_registry.enrolled_names).count(StakingEscrowDeployer.contract_name)
    assert new_enrolled_names == old_enrolled_names + 1


# TODO: test to validate retargetting via multisig, specifically, building the transaction


def test_manual_proxy_retargeting(testerchain, click_runner, token_economics):

    # A local, alternate filepath registry exists
    assert os.path.exists(ALTERNATE_REGISTRY_FILEPATH)
    local_registry = LocalContractRegistry(filepath=ALTERNATE_REGISTRY_FILEPATH)
    deployer = StakingEscrowDeployer(deployer_address=testerchain.etherbase_account,
                                     registry=local_registry,
                                     economics=token_economics)
    proxy_deployer = deployer.get_proxy_deployer()

    # Un-targeted enrollment is indeed un targeted by the proxy
    untargeted_deployment = deployer.get_latest_enrollment()
    assert proxy_deployer.target_contract.address != untargeted_deployment.address

    # MichWill still owns this proxy.
    michwill = testerchain.unassigned_accounts[1]
    assert proxy_deployer.target_contract.functions.owner().call() == michwill

    command = ('upgrade',
               '--retarget',
               '--deployer-address', michwill,
               '--contract-name', StakingEscrowDeployer.contract_name,
               '--target-address', untargeted_deployment.address,
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', ALTERNATE_REGISTRY_FILEPATH)

    # Upgrade
    user_input = '0\n' + 'Y\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # The proxy target has been updated.
    proxy_deployer = deployer.get_proxy_deployer()
    assert proxy_deployer.target_contract.address == untargeted_deployment.address


def test_manual_deployment_of_idle_network(click_runner):

    if os.path.exists(ALTERNATE_REGISTRY_FILEPATH_2):
        os.remove(ALTERNATE_REGISTRY_FILEPATH_2)
    assert not os.path.exists(ALTERNATE_REGISTRY_FILEPATH_2)
    registry = LocalContractRegistry(filepath=ALTERNATE_REGISTRY_FILEPATH_2)
    registry.write(InMemoryContractRegistry().read())  # FIXME: Manual deployments from scratch require an existing but empty registry (i.e., a json file just with "[]")

    # 1. Deploy NuCypherToken
    command = ('contracts',
               '--contract-name', NUCYPHER_TOKEN_CONTRACT_NAME,
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', ALTERNATE_REGISTRY_FILEPATH_2)

    user_input = '0\n' + 'Y\n' + INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    assert os.path.exists(ALTERNATE_REGISTRY_FILEPATH_2)
    new_registry = LocalContractRegistry(filepath=ALTERNATE_REGISTRY_FILEPATH_2)

    deployed_contracts = [NUCYPHER_TOKEN_CONTRACT_NAME]
    assert list(new_registry.enrolled_names) == deployed_contracts

    # 2. Deploy StakingEscrow in IDLE mode
    command = ('contracts',
               '--contract-name', STAKING_ESCROW_CONTRACT_NAME,
               '--mode', 'idle',
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', ALTERNATE_REGISTRY_FILEPATH_2)

    user_input = '0\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    deployed_contracts.extend([STAKING_ESCROW_CONTRACT_NAME, DISPATCHER_CONTRACT_NAME])
    assert list(new_registry.enrolled_names) == deployed_contracts

    # 3. Deploy PolicyManager
    command = ('contracts',
               '--contract-name', POLICY_MANAGER_CONTRACT_NAME,
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', ALTERNATE_REGISTRY_FILEPATH_2)

    user_input = '0\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    deployed_contracts.extend([POLICY_MANAGER_CONTRACT_NAME, DISPATCHER_CONTRACT_NAME])
    assert list(new_registry.enrolled_names) == deployed_contracts

    # 4. Deploy Adjudicator
    command = ('contracts',
               '--contract-name', ADJUDICATOR_CONTRACT_NAME,
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', ALTERNATE_REGISTRY_FILEPATH_2)

    user_input = '0\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    deployed_contracts.extend([ADJUDICATOR_CONTRACT_NAME, DISPATCHER_CONTRACT_NAME])
    assert list(new_registry.enrolled_names) == deployed_contracts

    # 5. Activate StakingEscrow
    command = ('contracts',
               '--contract-name', STAKING_ESCROW_CONTRACT_NAME,
               '--activate',
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', ALTERNATE_REGISTRY_FILEPATH_2)

    user_input = '0\n' + 'Y\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert list(new_registry.enrolled_names) == deployed_contracts

