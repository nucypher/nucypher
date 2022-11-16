


from typing import Type, Union

import click
from constant_sorrow.constants import UNKNOWN_DEVELOPMENT_CHAIN_ID

from nucypher.blockchain.eth.deployers import BaseContractDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, VersionedContract, BlockchainInterface
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.cli.literature import (
    ABORT_DEPLOYMENT,
    CHARACTER_DESTRUCTION
)
from nucypher.cli.literature import CONFIRM_VERSIONED_UPGRADE
from nucypher.config.base import CharacterConfiguration
from nucypher.utilities.emitters import StdoutEmitter


def confirm_deployment(emitter: StdoutEmitter, deployer_interface: BlockchainDeployerInterface) -> bool:
    """
    Interactively confirm deployment by asking the user to type the ALL CAPS name of
    the network they are deploying to or 'DEPLOY' if the network if not a known public chain.

    Aborts if the confirmation word is incorrect.
    """
    if deployer_interface.client.chain_name == UNKNOWN_DEVELOPMENT_CHAIN_ID or deployer_interface.client.is_local:
        expected_chain_name = 'DEPLOY'
    else:
        expected_chain_name = deployer_interface.client.chain_name
    if click.prompt(f"Type '{expected_chain_name.upper()}' to continue") != expected_chain_name.upper():
        emitter.echo(ABORT_DEPLOYMENT, color='red', bold=True)
        raise click.Abort(ABORT_DEPLOYMENT)
    return True


def confirm_destroy_configuration(config: CharacterConfiguration) -> bool:
    """Interactively confirm destruction of nucypher configuration files"""
    # TODO: This is a workaround for ursula - needs follow up
    confirmation = CHARACTER_DESTRUCTION.format(name=config.NAME,
                                                root=config.config_root,
                                                keystore=config.keystore_dir,
                                                nodestore=config.node_storage.source,
                                                config=config.filepath)
    click.confirm(confirmation, abort=True)
    return True


def verify_upgrade_details(blockchain: Union[BlockchainDeployerInterface, BlockchainInterface],
                           registry: LocalContractRegistry,
                           deployer: Type[BaseContractDeployer],
                           ) -> None:
    """
    Compares the versions of two 'implementation' contracts using a local and source registry.
    """

    old_contract: VersionedContract = blockchain.get_contract_by_name(
        registry=registry,
        contract_name=deployer.contract_name,
        proxy_name=deployer.agency._proxy_name,
        use_proxy_address=False
    )

    new_contract = blockchain.find_raw_contract_data(contract_name=deployer.contract_name)
    new_version = new_contract[0]  # Handle index error?

    click.confirm(CONFIRM_VERSIONED_UPGRADE.format(contract_name=deployer.contract_name,
                                                   old_version=old_contract.version,
                                                   new_version=new_version), abort=True)
