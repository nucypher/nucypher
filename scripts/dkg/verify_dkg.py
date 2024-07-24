import random
from typing import List

from nucypher_core.ferveo import Transcript, Validator

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.crypto.ferveo.dkg import aggregate_transcripts

ritual_id = 20
domain = domains.MAINNET
endpoint = ""


registry = ContractRegistry.from_latest_publication(domain=domain)
coordinator_agent = ContractAgency.get_agent(
    agent_class=CoordinatorAgent,
    registry=registry,
    blockchain_endpoint=endpoint,
)


def resolve_validators() -> List[Validator]:
    result = list()
    for staking_provider_address in ritual.providers:
        public_key = coordinator_agent.get_provider_public_key(
            provider=staking_provider_address, ritual_id=ritual.id
        )
        external_validator = Validator(
            address=staking_provider_address, public_key=public_key
        )
        result.append(external_validator)
    result = sorted(result, key=lambda x: x.address)
    return result


ritual = coordinator_agent.get_ritual(
    ritual_id=ritual_id,
    transcripts=True,
)

validators = resolve_validators()
transcripts = [Transcript.from_bytes(bytes(t)) for t in ritual.transcripts]
messages = list(zip(validators, transcripts))

aggregate_transcripts(
    transcripts=messages,
    shares=ritual.shares,
    threshold=ritual.threshold,
    me=random.choice(validators),  # this is hacky
    ritual_id=ritual.id,
)
