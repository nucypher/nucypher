from typing import Tuple

from hexbytes import HexBytes
from nucypher_core import AAVersion, PackedUserOperation

from nucypher.crypto.powers import TransactingPower


def sign_packed_user_operation(
    packed_user_op: PackedUserOperation,
    transacting_power: TransactingPower,
    aa_version: str,
    chain_id: int,
) -> Tuple[HexBytes, HexBytes]:
    """Sign a PackedUserOperation using the provided transacting power."""
    if aa_version == AAVersion.V07:
        raw_hash = packed_user_op.to_v07_hash(chain_id=chain_id)
        message_hash, signature = transacting_power.sign_message_eip191(
            raw_hash, standardize=False
        )
    else:
        eip_712_message = packed_user_op.to_eip712_struct(aa_version, chain_id)
        message_hash, signature = transacting_power.sign_message_eip712(
            eip_712_message, standardize=False
        )
    return message_hash, signature
