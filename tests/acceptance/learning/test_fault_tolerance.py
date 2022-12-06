from nucypher_core import MetadataResponse, MetadataResponsePayload
from twisted.logger import LogLevel, globalLogPublisher

from nucypher.acumen.perception import FleetSensor
from nucypher.config.constants import TEMPORARY_DOMAIN


def test_ursula_stamp_verification_tolerance(ursulas, mocker):
    #
    # Setup
    #

    lonely_learner, teacher, unsigned, *the_others = list(ursulas)

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    # Make a bad identity evidence
    unsigned._Ursula__operator_signature = unsigned._Ursula__operator_signature[:-5] + (b'\x00' * 5)
    # Reset the metadata cache
    unsigned._metadata = None

    # Wipe known nodes!
    lonely_learner._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    lonely_learner._current_teacher_node = teacher
    lonely_learner.remember_node(teacher)

    globalLogPublisher.addObserver(warning_trapper)
    lonely_learner.learn_from_teacher_node(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    # We received one warning during learning, and it was about this very matter.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert str(unsigned) in warning
    assert "Verification Failed" in warning  # TODO: Cleanup logging templates

    # TODO: Buckets!  #567
    # assert unsigned not in lonely_learner.known_nodes

    # minus 2: self and the unsigned ursula.
    # assert len(lonely_learner.known_nodes) == len(ursulas) - 2
    assert teacher in lonely_learner.known_nodes

    # Learn about a node with a badly signed payload

    def bad_bytestring_of_known_nodes():
        # Signing with the learner's signer instead of the teacher's signer
        response_payload = MetadataResponsePayload(
            timestamp_epoch=teacher.known_nodes.timestamp.epoch, announce_nodes=[]
        )
        response = MetadataResponse(
            signer=lonely_learner.stamp.as_umbral_signer(), payload=response_payload
        )
        return bytes(response)

    mocker.patch.object(
        teacher, "bytestring_of_known_nodes", bad_bytestring_of_known_nodes
    )

    globalLogPublisher.addObserver(warning_trapper)
    lonely_learner.learn_from_teacher_node(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    assert len(warnings) == 2
    warning = warnings[1]['log_format']
    assert str(teacher) in warning
    assert "Failed to verify MetadataResponse from Teacher" in warning  # TODO: Cleanup logging templates
