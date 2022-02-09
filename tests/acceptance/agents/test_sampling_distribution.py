from collections import Counter

import pytest
import random
from itertools import permutations
from unittest.mock import Mock

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import WeightedSampler, ContractAgency, PREApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower, CryptoPower
from tests.constants import PYEVM_DEV_URI


def test_sampling_distribution(testerchain, test_registry, threshold_staking, application_economics):

    # setup
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    stake_provider_accounts = testerchain.stake_providers_accounts
    amount = application_economics.min_authorization
    all_locked_tokens = len(stake_provider_accounts) * amount

    # providers and operators
    for provider_address in stake_provider_accounts:
        operator_address = provider_address

        # initialize threshold stake
        tx = threshold_staking.functions.setRoles(provider_address).transact()
        testerchain.wait_for_receipt(tx)
        tx = threshold_staking.functions.authorizationIncreased(provider_address, 0, amount).transact()
        testerchain.wait_for_receipt(tx)

        power = TransactingPower(account=provider_address, signer=Web3Signer(testerchain.client))

        # We assume that the staking provider knows in advance the account of her operator
        application_agent.bond_operator(staking_provider=provider_address,
                                        operator=operator_address,
                                        transacting_power=power)

        operator = Operator(is_me=True,
                            operator_address=operator_address,
                            domain=TEMPORARY_DOMAIN,
                            registry=test_registry,
                            crypto_power=CryptoPower(),
                            transacting_power=power,
                            eth_provider_uri=PYEVM_DEV_URI,
                            payment_method=Mock())
        operator.confirm_address()

    #
    # Test sampling distribution
    #

    ERROR_TOLERANCE = 0.05  # With this tolerance, all sampling ratios should between 5% and 15% (expected is 10%)
    SAMPLES = 1000
    quantity = 3
    counter = Counter()

    sampled, failed = 0, 0
    while sampled < SAMPLES:
        try:
            reservoir = application_agent.get_staking_provider_reservoir()
            addresses = set(reservoir.draw(quantity))
            addresses.discard(NULL_ADDRESS)
        except application_agent.NotEnoughStakingProviders:
            failed += 1
            continue
        else:
            sampled += 1
            counter.update(addresses)

    total_times = sum(counter.values())

    expected = amount / all_locked_tokens
    for stake_provider in stake_provider_accounts:
        times = counter[stake_provider]
        sampled_ratio = times / total_times
        abs_error = abs(expected - sampled_ratio)
        assert abs_error < ERROR_TOLERANCE

    # TODO: Test something wrt to % of failed


def probability_reference_no_replacement(weights, idxs):
    """
    The probability of drawing elements with (distinct) indices ``idxs`` (in given order),
    given ``weights``. No replacement.
    """
    assert len(set(idxs)) == len(idxs)
    all_weights = sum(weights)
    p = 1
    for idx in idxs:
        p *= weights[idx] / all_weights
        all_weights -= weights[idx]
    return p


@pytest.mark.parametrize('sample_size', [1, 2, 3])
def test_weighted_sampler(sample_size):
    weights = [1, 9, 100, 2, 18, 70]
    elements = list(range(len(weights)))

    # Use a fixed seed to avoid flakyness of the test
    rng = random.Random(123)

    counter = Counter()

    weighted_elements = {element: weight for element, weight in zip(elements, weights)}

    samples = 100000
    for i in range(samples):
        sampler = WeightedSampler(weighted_elements)
        sample_set = sampler.sample_no_replacement(rng, sample_size)
        counter.update({tuple(sample_set): 1})

    for idxs in permutations(elements, sample_size):
        test_prob = counter[idxs] / samples
        ref_prob = probability_reference_no_replacement(weights, idxs)

        # A rough estimate to check probabilities.
        # A little too forgiving for samples with smaller probabilities,
        # but can go up to 0.5 on occasion.
        assert abs(test_prob - ref_prob) * samples**0.5 < 1
