# Based on original work here:
# https://github.com/nucypher/ferveo/blob/client-server-api/ferveo-python/examples/server_api.py
from ferveo_py import *
from typing import List, Tuple, Any


def _make_dkg(
    me: ExternalValidator,
    ritual_id: int,
    shares: int,
    threshold: int,
    nodes: List[ExternalValidator],
) -> Dkg:
    dkg = Dkg(
        tau=ritual_id,
        shares_num=shares,
        security_threshold=threshold,
        validators=nodes,
        me=me
    )
    return dkg


def generate_transcript(*args, **kwargs):
    dkg = _make_dkg(*args, **kwargs)
    transcript = dkg.generate_transcript()
    return transcript


def _validate_pvss_aggregated(pvss_aggregated: AggregatedTranscript, dkg) -> bool:
    valid = pvss_aggregated.validate(dkg)
    if not valid:
        raise Exception("validation failed")  # TODO: better exception handling
    return valid


def aggregate_transcripts(
        transcripts: List[Tuple[ExternalValidator, Transcript]],
        *args, **kwargs
) -> Tuple[AggregatedTranscript, PublicKey, Any]:
    validators = [t[0] for t in transcripts]
    _dkg = _make_dkg(nodes=validators, *args, **kwargs)
    pvss_aggregated = _dkg.aggregate_transcripts(transcripts)
    pvss_aggregated.validate(_dkg)
    return pvss_aggregated, _dkg.final_key, _dkg.g1_inv


def derive_decryption_share(
    nodes: List[ExternalValidator],
    aggregated_transcript: AggregatedTranscript,
    keypair: Keypair,
    ciphertext: Ciphertext,
    aad: bytes,
    *args, **kwargs
) -> DecryptionShare:
    dkg = _make_dkg(nodes=nodes, *args, **kwargs)
    if not all((nodes, aggregated_transcript, keypair, ciphertext, aad)):
        raise Exception("missing arguments")
    decryption_share = aggregated_transcript.create_decryption_share(
        dkg, ciphertext, aad, keypair
    )
    return decryption_share
