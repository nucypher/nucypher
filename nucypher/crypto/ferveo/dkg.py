from enum import Enum
from typing import List, Tuple, Union

from eth_utils import keccak
from ferveo_py.ferveo_py import *

from nucypher.utilities.logging import Logger

LOGGER = Logger('ferveo-dkg')


class FerveoVariant(Enum):
    SIMPLE = 0
    PRECOMPUTED = 1


_VARIANTS = {
    FerveoVariant.SIMPLE: AggregatedTranscript.create_decryption_share_simple,
    FerveoVariant.PRECOMPUTED: AggregatedTranscript.create_decryption_share_precomputed
}


def _make_dkg(
    me: Validator,
    ritual_id: int,
    shares: int,
    threshold: int,
    nodes: List[Validator],
) -> Dkg:
    dkg = Dkg(
        tau=ritual_id,
        shares_num=shares,
        security_threshold=threshold,
        validators=nodes,
        me=me
    )
    LOGGER.debug(f"Initialized DKG backend for {threshold}/{shares} nodes: {', '.join(n.address[:6] for n in nodes)}")
    return dkg


def generate_transcript(*args, **kwargs):
    dkg = _make_dkg(*args, **kwargs)
    transcript = dkg.generate_transcript()
    return transcript


def derive_public_key(*args, **kwargs):
    dkg = _make_dkg(*args, **kwargs)
    return dkg.public_key


def aggregate_transcripts(
    transcripts: List[Tuple[Validator, Transcript]], shares: int, *args, **kwargs
) -> Tuple[AggregatedTranscript, PublicKey, DkgPublicParameters]:
    validators = [t[0] for t in transcripts]
    _dkg = _make_dkg(nodes=validators, shares=shares, *args, **kwargs)
    pvss_aggregated = _dkg.aggregate_transcripts(transcripts)
    verify_aggregate(pvss_aggregated, shares, transcripts)
    LOGGER.debug(
        f"derived final DKG key {bytes(_dkg.public_key).hex()[:10]} and {keccak(bytes(_dkg.public_params)).hex()[:10]}"
    )
    return pvss_aggregated, _dkg.public_key, _dkg.public_params


def verify_aggregate(
    pvss_aggregated: AggregatedTranscript,
    shares: int,
    transcripts: List[Tuple[Validator, Transcript]],
):
    pvss_aggregated.verify(shares, transcripts)

def derive_decryption_share(
    nodes: List[Validator],
    aggregated_transcript: AggregatedTranscript,
    keypair: Keypair,
    ciphertext: Ciphertext,
    aad: bytes,
    variant: FerveoVariant,
    *args, **kwargs
) -> Union[DecryptionShareSimple, DecryptionSharePrecomputed]:
    dkg = _make_dkg(nodes=nodes, *args, **kwargs)
    if not all((nodes, aggregated_transcript, keypair, ciphertext, aad)):
        raise Exception("missing arguments")  # sanity check
    try:
        derive_share = _VARIANTS[variant]
    except KeyError:
        raise Exception(f"invalid variant {variant}")
    share = derive_share(
        # first arg here is intended to be "self" since the method is unbound
        aggregated_transcript,
        dkg,
        ciphertext,
        aad,
        keypair
    )
    return share
