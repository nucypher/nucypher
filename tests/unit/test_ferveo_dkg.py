from nucypher.crypto.ferveo.dkg import (
    _make_dkg,
    generate_transcript,
    generate_dkg_keypair,
    aggregate_transcripts,
    derive_decryption_share,
)


def test_make_dkg():
    ritual_id = 1
    checksum_address = "0x1234"
    shares = 2
    threshold = 2
    nodes = ["0x1234", "0x5678", "0x9abc"]
    dkg = _make_dkg(ritual_id, checksum_address, shares, threshold, nodes)
    assert dkg.tau == ritual_id
    assert dkg.me == checksum_address
    assert dkg.shares_num == shares
    assert dkg.security_threshold == threshold
    assert dkg.validators == nodes


def test_generate_random_keypair():
    keypair = generate_dkg_keypair()
    assert keypair.public_key
    assert keypair.secret_key


def test_generate_transcript():
    ritual_id = 1
    checksum_address = "0x1234"
    shares = 2
    threshold = 2
    nodes = ["0x1234", "0x5678", "0x9abc"]
    transcript = generate_transcript(
        ritual_id, checksum_address, shares, threshold, nodes
    )
    assert transcript
    assert transcript.validate(_make_dkg(ritual_id, checksum_address, shares, threshold, nodes))



def test_aggregate_transcripts():
    ritual_id = 1
    checksum_address = "0x1234"
    shares = 2
    threshold = 2
    nodes = ["0x1234", "0x5678", "0x9abc"]
    transcripts = [
        bytes(generate_transcript(
            ritual_id, checksum_address, shares, threshold, nodes
        ))
        for _ in range(threshold)
    ]
    aggregated_transcript, public_key = aggregate_transcripts(
        transcripts, ritual_id, checksum_address, shares, threshold, nodes
    )
    assert aggregated_transcript
    assert public_key


def test_derive_decryption_share():
    ritual_id = 1
    checksum_address = "0x1234"
    shares = 2
    threshold = 2
    nodes = ["0x1234", "0x5678", "0x9abc"]
    transcripts = [
        bytes(generate_transcript(
            ritual_id, checksum_address, shares, threshold, nodes
        ))
        for _ in range(threshold)
    ]
    aggregated_transcript, public_key = aggregate_transcripts(
        transcripts, ritual_id, checksum_address, shares, threshold, nodes
    )
    keypair = generate_dkg_keypair()
    ciphertext = b"hello"
    aad = b"world"
    decryption_share = derive_decryption_share(
        aggregated_transcript,
        keypair,
        ciphertext,
        aad,
        ritual_id,
        checksum_address,
        shares,
        threshold,
        nodes,
    )
    assert decryption_share
    assert decryption_share.validate(
        aggregated_transcript, ciphertext, aad, public_key
    )
