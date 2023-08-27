from typing import List, Tuple, Union

from nucypher_core.ferveo import (
    AggregatedTranscript,
    CiphertextHeader,
    DecryptionSharePrecomputed,
    DecryptionShareSimple,
    Dkg,
    DkgPublicKey,
    FerveoVariant,
    Keypair,
    Transcript,
    Validator,
    ValidatorMessage,
)

from nucypher.utilities.logging import Logger

LOGGER = Logger('ferveo-dkg')


_VARIANTS = {
    FerveoVariant.Simple: AggregatedTranscript.create_decryption_share_simple,
    FerveoVariant.Precomputed: AggregatedTranscript.create_decryption_share_precomputed,
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


def generate_transcript(*args, **kwargs) -> Transcript:
    dkg = _make_dkg(*args, **kwargs)
    transcript = dkg.generate_transcript()
    return transcript


def derive_public_key(*args, **kwargs) -> DkgPublicKey:
    dkg = _make_dkg(*args, **kwargs)
    return dkg.public_key


def aggregate_transcripts(
    transcripts: List[Tuple[Validator, Transcript]], shares: int, *args, **kwargs
) -> Tuple[AggregatedTranscript, DkgPublicKey]:
    validators = [t[0] for t in transcripts]
    _dkg = _make_dkg(nodes=validators, shares=shares, *args, **kwargs)
    validator_msgs = [ValidatorMessage(v[0], v[1]) for v in transcripts]
    pvss_aggregated = _dkg.aggregate_transcripts(validator_msgs)
    verify_aggregate(pvss_aggregated, shares, validator_msgs)
    LOGGER.debug(f"derived final DKG key {bytes(_dkg.public_key).hex()[:10]}")
    return pvss_aggregated, _dkg.public_key


def verify_aggregate(
    pvss_aggregated: AggregatedTranscript,
    shares: int,
    transcripts: List[ValidatorMessage],
):
    pvss_aggregated.verify(shares, transcripts)


def derive_decryption_share(
    nodes: List[Validator],
    aggregated_transcript: AggregatedTranscript,
    keypair: Keypair,
    ciphertext_header: CiphertextHeader,
    aad: bytes,
    variant: FerveoVariant,
    *args, **kwargs
) -> Union[DecryptionShareSimple, DecryptionSharePrecomputed]:
    dkg = _make_dkg(nodes=nodes, *args, **kwargs)
    if not all((nodes, aggregated_transcript, keypair, ciphertext_header, aad)):
        raise Exception("missing arguments")  # sanity check
    try:
        derive_share = _VARIANTS[variant]
    except KeyError:
        raise ValueError(f"Invalid variant {variant}")
    share = derive_share(
        # first arg here is intended to be "self" since the method is unbound
        aggregated_transcript,
        dkg,
        ciphertext_header,
        aad,
        keypair
    )
    return share
