import os

G1_SIZE = 48
G2_SIZE = 48 * 2


def threshold_from_shares(shares):
    return shares // 2 + 1


def ritual_transcript_size(shares, threshold):
    return 40 + (1 + shares) * G2_SIZE + threshold * G1_SIZE


def generate_fake_ritual_transcript(shares, threshold):
    return os.urandom(ritual_transcript_size(shares, threshold))
