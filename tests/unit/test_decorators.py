

import pytest

from nucypher.blockchain.eth.decorators import InvalidChecksumAddress, validate_checksum_address


def test_validate_checksum_address(get_random_checksum_address):

    # Simple case: just one parameter, called "checksum_address"
    @validate_checksum_address
    def just_one_address(checksum_address):
        return True

    with pytest.raises(InvalidChecksumAddress):
        just_one_address("0x_NOT_VALID")

    with pytest.raises(TypeError):
        just_one_address(123)

    assert just_one_address(get_random_checksum_address())

    # More complex case: the parameter is optional
    @validate_checksum_address
    def optional_checksum_address(whatever, staking_address=None):
        return True

    with pytest.raises(InvalidChecksumAddress):
        optional_checksum_address(12, "0x_NOT_VALID")

    with pytest.raises(InvalidChecksumAddress):
        optional_checksum_address("whatever", get_random_checksum_address().lower())

    assert optional_checksum_address(123)

    assert optional_checksum_address(None, staking_address=get_random_checksum_address())

    # Even more complex: there are multiple checksum addresses
    @validate_checksum_address
    def multiple_checksum_addresses(whatever, operator_address, staking_address=None):
        return True

    with pytest.raises(InvalidChecksumAddress):
        multiple_checksum_addresses(12, "0x_NOT_VALID")

    with pytest.raises(InvalidChecksumAddress):
        multiple_checksum_addresses(12, get_random_checksum_address(), "0x_NOT_VALID")

    with pytest.raises(InvalidChecksumAddress):
        multiple_checksum_addresses(12, "0x_NOT_VALID", get_random_checksum_address())

    with pytest.raises(TypeError):
        multiple_checksum_addresses(12, None)

    assert multiple_checksum_addresses(123, get_random_checksum_address(), None)
    assert multiple_checksum_addresses(123, get_random_checksum_address())

    assert multiple_checksum_addresses(42,
                                       operator_address=get_random_checksum_address(),
                                       staking_address=get_random_checksum_address())
