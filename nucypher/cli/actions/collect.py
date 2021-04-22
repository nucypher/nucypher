"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

from collections import namedtuple

import click
import maya
from constant_sorrow.constants import FEDERATED
from datetime import timedelta
from typing import Tuple
from web3.main import Web3

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.characters.lawful import Bob, Alice
from nucypher.cli.painting.help import enforce_probationary_period, paint_probationary_period_disclaimer
from nucypher.cli.painting.policies import paint_single_card
from nucypher.cli.types import GWEI
from nucypher.policy.identity import Card

PublicKeys = namedtuple('PublicKeys', 'encrypting_key verifying_key')
PolicyParameters = namedtuple('PolicyParameters', 'label m n expiration value rate')


def collect_keys_from_card(emitter: StdoutEmitter, card_identifier: str, force: bool):
    emitter.message(f"Searching contacts for {card_identifier}\n", color='yellow')
    card = Card.load(identifier=card_identifier)

    if card.character is not Bob:
        emitter.error('Grantee card is not a Bob.')
        raise click.Abort
    paint_single_card(emitter=emitter, card=card)

    if not force:
        click.confirm('Is this the correct grantee (Bob)?', abort=True)

    bob_encrypting_key = card.encrypting_key.hex()
    bob_verifying_key = card.verifying_key.hex()
    public_keys = PublicKeys(encrypting_key=bob_encrypting_key, verifying_key=bob_verifying_key)
    return public_keys


def collect_bob_public_keys(
        emitter: StdoutEmitter,
        force: bool,
        card_identifier: str,
        bob_encrypting_key: str,
        bob_verifying_key: str
        ) -> PublicKeys:
    """helper function for collecting Bob's public keys interactively in the Alice CLI."""

    if card_identifier:
        public_keys = collect_keys_from_card(
            emitter=emitter,
            card_identifier=card_identifier,
            force=force)
        return public_keys

    if not bob_encrypting_key:
        bob_encrypting_key = click.prompt("Enter Bob's encrypting key")
    if not bob_verifying_key:
        bob_verifying_key = click.prompt("Enter Bob's verifying key")

    public_keys = PublicKeys(encrypting_key=bob_encrypting_key, verifying_key=bob_verifying_key)
    return public_keys


def collect_label(label: str, bob_identifier: str):
    if not label:
        label = click.prompt(f'Enter label to grant Bob {bob_identifier}', type=click.STRING)
    return label


def collect_expiration(alice: Alice, expiration: maya.MayaDT, force: bool) -> maya.MayaDT:
    # TODO: Support interactive expiration periods?
    if not force and not expiration:
        default_expiration = None
        expiration_prompt = 'Enter policy expiration (Y-M-D H:M:S)'
        if alice.payment_periods:
            default_expiration = maya.now() + timedelta(hours=alice.payment_periods * alice.economics.hours_per_period)
        expiration = click.prompt(expiration_prompt, type=click.DateTime(), default=default_expiration)
    return expiration


def collect_m_and_n(alice: Alice, m: int, n: int, force: bool) -> Tuple[int, int]:
    # Policy Threshold and Shares
    if not n:
        n = alice.n
        if not force and not click.confirm(f'Use default value for N ({n})?', default=True):
            n = click.prompt('Enter total number of shares (N)', type=click.INT)
    if not m:
        m = alice.m
        if not force and not click.confirm(f'Use default value for M ({m})?', default=True):
            m = click.prompt('Enter threshold (M)', type=click.IntRange(1, n))
    return m, n


def collect_policy_rate_and_value(alice: Alice, rate: int, value: int, n: int, force: bool) -> Tuple[int, int]:

    policy_value_provided = bool(value) or bool(rate)
    if not policy_value_provided:

        # TODO #1709 - Fine tuning and selection of default rates
        rate = alice.default_rate  # wei

        if not force:
            default_gwei = Web3.fromWei(rate, 'gwei')  # wei -> gwei
            prompt = "Confirm rate of {node_rate} gwei * {n} nodes ({period_rate} gwei per period)?"

            if not click.confirm(prompt.format(node_rate=default_gwei, period_rate=default_gwei * n, n=n), default=True):
                interactive_rate = click.prompt('Enter rate per period in gwei', type=GWEI)
                # TODO: Interactive rate sampling & validation (#1709)
                interactive_prompt = prompt.format(node_rate=interactive_rate, period_rate=interactive_rate * n, n=n)
                click.confirm(interactive_prompt, default=True, abort=True)
                rate = Web3.toWei(interactive_rate, 'gwei')  # gwei -> wei

    return rate, value


def collect_policy_parameters(
        emitter: StdoutEmitter,
        alice: Alice,
        force: bool,
        bob_identifier: str,
        label: str,
        m: int,
        n: int,
        value: int,
        rate: int,
        expiration: maya.MayaDT
        ) -> PolicyParameters:

    # Interactive collection follows:
    # - Disclaimer
    # - Label
    # - Expiration Date & Time
    # - M of N
    # - Policy Value (ETH)

    label = collect_label(label=label, bob_identifier=bob_identifier)

    # TODO: Remove this line when the time is right.
    paint_probationary_period_disclaimer(emitter)
    expiration = collect_expiration(alice=alice, expiration=expiration, force=force)
    enforce_probationary_period(emitter=emitter, expiration=expiration)

    m, n = collect_m_and_n(alice=alice, m=m, n=n, force=force)
    if alice.federated_only:
        rate, value = FEDERATED, FEDERATED
    else:
        rate, value = collect_policy_rate_and_value(
            alice=alice,
            rate=rate,
            value=value,
            n=n,
            force=force)

    policy_parameters = PolicyParameters(
        label=label,
        m=m,
        n=n,
        expiration=expiration,
        rate=rate,
        value=value
    )

    return policy_parameters
