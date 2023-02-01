from typing import Tuple, Dict

import os


class DKGRitual:
    domain: bytes
    index: int
    node: bytes
    pvss_params: Dict[str, bytes]


def generate_dkg_blinding_keypair(*args, **kwargs) -> Tuple[bytes, bytes]:
    """ferveo generate_blinding_keypair"""
    return os.urandom(32), os.urandom(32)


def generate_dkg_ritual(*args, **kwargs) ->:
    """ferveo generate_ritual"""
    return DKGRitual(0)


def generate_dkg_transcript(dkg, shares: int, *args, **kwargs) -> bytes:
    """ferveo generate PVSS"""
    return os.urandom(32)


def confirm_dkg_transcript(transcript, *args, **kwargs) -> bool:
    """ferveo confirm_transcript"""
    return True


def compute_dfrag(*args, **kwargs):
    """ferveo compute_dfrag"""
