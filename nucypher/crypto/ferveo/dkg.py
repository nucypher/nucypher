# Based on original work here:
# https://github.com/nucypher/ferveo/blob/client-server-api/ferveo-python/examples/server_api.py

from typing import Tuple

from nucypher.crypto.ferveo.mock import *


def _make_dkg(
    ritual_id: int,
    checksum_address: ChecksumAddress,
    shares: int,
    threshold: int,
    nodes: List[ChecksumAddress],
) -> Dkg:
    _dkg = Dkg(
        tau=ritual_id,
        shares_num=shares,
        security_threshold=threshold,
        validators=nodes,
        me=checksum_address,
    )
    return _dkg


def generate_dkg_keypair() -> Keypair:
    return Keypair.random()


def generate_transcript(*args, **kwargs) -> Transcript:
    _dkg = _make_dkg(*args, **kwargs)
    transcript = _dkg.generate_transcript()
    return transcript


def aggregate_transcripts(
    transcripts: List[bytes], *args, **kwargs
) -> Tuple[AggregatedTranscript, PublicKey]:
    _dkg = _make_dkg(*args, **kwargs)
    pvss_aggregated = _dkg.aggregate_transcripts(transcripts)
    if not pvss_aggregated.validate(_dkg):
        raise Exception("validation failed")  # TODO: better exception
    public_key = _dkg.final_key
    return pvss_aggregated, public_key


def derive_decryption_share(
    aggregated_transcript: AggregatedTranscript,
    keypair: Keypair,
    ciphertext: bytes,
    aad: bytes,
    *args,
    **kwargs
) -> DecryptionShare:
    dkg = _make_dkg(*args, **kwargs)
    assert aggregated_transcript.validate(dkg)
    decryption_share = aggregated_transcript.create_decryption_share(
        dkg, ciphertext, aad, keypair
    )
    return decryption_share
