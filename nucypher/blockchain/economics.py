

from typing import Tuple, Optional

from web3 import Web3
from web3.types import Wei

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    PREApplicationAgent
)
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import TToken


class Economics:

    _default_min_authorization = TToken(40_000, 'T').to_units()
    _default_min_operator_seconds = 60 * 60 * 24  # one day in seconds
    _default_fee_rate = Wei(Web3.to_wei(1, 'gwei'))
    # TODO choose proper default values
    _default_reward_duration = 60 * 60 * 24 * 7   # one week in seconds
    _default_deauthorization_duration = 60 * 60 * 24 * 60  # 60 days in seconds
    # Slashing parameters
    HASH_ALGORITHM_KECCAK256 = 0
    HASH_ALGORITHM_SHA256 = 1
    HASH_ALGORITHM_RIPEMD160 = 2
    _default_hash_algorithm = HASH_ALGORITHM_SHA256
    _default_base_penalty = 2
    _default_penalty_history_coefficient = 0
    _default_percentage_penalty_coefficient = 100000  # 0.001%

    def __init__(self,
                 min_operator_seconds: int = _default_min_operator_seconds,
                 min_authorization: int = _default_min_authorization,
                 fee_rate: Wei = _default_fee_rate,
                 reward_duration: int = _default_reward_duration,
                 deauthorization_duration: int = _default_deauthorization_duration,
                 # Adjudicator
                 hash_algorithm: int = _default_hash_algorithm,
                 base_penalty: int = _default_base_penalty,
                 penalty_history_coefficient: int = _default_penalty_history_coefficient,
                 percentage_penalty_coefficient: int = _default_percentage_penalty_coefficient,
                 ):

        """
        :param min_operator_seconds: Min amount of seconds while an operator can't be changed
        :param min_authorization: Amount of minimum allowable authorization
        :param reward_duration: Duration of one reward cycle
        :param deauthorization_duration: Duration of decreasing authorization

        :param hash_algorithm: Hashing algorithm
        :param base_penalty: Base for the penalty calculation
        :param penalty_history_coefficient: Coefficient for calculating the penalty depending on the history
        :param percentage_penalty_coefficient: Coefficient for calculating the percentage penalty
        """

        self.hash_algorithm = hash_algorithm
        self.base_penalty = base_penalty
        self.penalty_history_coefficient = penalty_history_coefficient
        self.percentage_penalty_coefficient = percentage_penalty_coefficient

        self.min_operator_seconds = min_operator_seconds
        self.min_authorization = min_authorization
        self.fee_rate = fee_rate
        self.reward_duration = reward_duration
        self.deauthorization_duration = deauthorization_duration
    @property
    def pre_application_deployment_parameters(self) -> Tuple[int, ...]:
        """Cast coefficient attributes to uint256 compatible type for solidity+EVM"""
        deploy_parameters = (  # note: order-sensitive
            self.hash_algorithm,
            self.base_penalty,
            self.penalty_history_coefficient,
            self.percentage_penalty_coefficient,
            self.min_authorization,
            self.min_operator_seconds,
            self.reward_duration,
            self.deauthorization_duration,
        )
        return tuple(map(int, deploy_parameters))


class EconomicsFactory:
    # TODO: Enforce singleton

    __economics = dict()

    @classmethod
    def get_economics(cls, registry: BaseContractRegistry, eth_provider_uri: Optional[str] = None) -> Economics:
        registry_id = registry.id
        try:
            return cls.__economics[registry_id]
        except KeyError:
            economics = EconomicsFactory.retrieve_from_blockchain(registry=registry, eth_provider_uri=eth_provider_uri)
            cls.__economics[registry_id] = economics
            return economics

    @staticmethod
    def retrieve_from_blockchain(registry: BaseContractRegistry, eth_provider_uri: Optional[str] = None) -> Economics:

        # Agents
        application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=registry, eth_provider_uri=eth_provider_uri)

        # PRE Application
        min_authorization = application_agent.get_min_authorization()
        min_operator_seconds = application_agent.get_min_operator_seconds()

        # Adjudicator
        # TODO: Reintroduce Adjudicator
        # adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=registry, provider_uri=provider_uri)
        # slashing_parameters = adjudicator_agent.slashing_parameters()

        # Aggregate
        economics_parameters = dict(min_authorization=min_authorization,
                                    min_operator_seconds=min_operator_seconds)

        economics = Economics(**economics_parameters)

        return economics
