import maya
import pytest
from eth_account import Account
from eth_account.messages import defunct_hash_message
from hexbytes import HexBytes
from siwe import SiweMessage
from web3.contract import Contract

from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.policy.conditions.auth.evm import (
    EIP712Auth,
    EIP1271Auth,
    EIP4361Auth,
    EvmAuth,
)
from nucypher.policy.conditions.exceptions import NoConnectionToChain
from nucypher.policy.conditions.utils import ConditionProviderManager
from tests.constants import TESTERCHAIN_CHAIN_ID


def test_auth_scheme():
    expected_schemes = {
        EvmAuth.AuthScheme.EIP712: EIP712Auth,
        EvmAuth.AuthScheme.EIP4361: EIP4361Auth,
        EvmAuth.AuthScheme.EIP1271: EIP1271Auth,
    }

    for scheme in EvmAuth.AuthScheme:
        expected_scheme = expected_schemes.get(scheme)
        assert EvmAuth.from_scheme(scheme=scheme.value) == expected_scheme

    # non-existent scheme
    with pytest.raises(ValueError):
        _ = EvmAuth.from_scheme(scheme="rando")


def test_authenticate_eip712(valid_eip712_auth_message, get_random_checksum_address):
    data = valid_eip712_auth_message["typedData"]
    signature = valid_eip712_auth_message["signature"]
    address = valid_eip712_auth_message["address"]

    # invalid data
    invalid_data = dict(data)  # make a copy
    del invalid_data["domain"]
    with pytest.raises(EvmAuth.InvalidData):
        EIP712Auth.authenticate(
            data=invalid_data, signature=signature, expected_address=address
        )

    invalid_data = dict(data)  # make a copy
    del invalid_data["message"]
    with pytest.raises(EvmAuth.InvalidData):
        EIP712Auth.authenticate(
            data=invalid_data, signature=signature, expected_address=address
        )

    # signature not for expected address
    incorrect_signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    with pytest.raises(EvmAuth.AuthenticationFailed):
        EIP712Auth.authenticate(
            data=data, signature=incorrect_signature, expected_address=address
        )

    # invalid signature
    invalid_signature = "0xdeadbeef"
    with pytest.raises(EvmAuth.InvalidData):
        EIP712Auth.authenticate(
            data=data, signature=invalid_signature, expected_address=address
        )

    # mismatch with expected address
    with pytest.raises(
        EvmAuth.AuthenticationFailed, match="signature not valid for expected address"
    ):
        EIP712Auth.authenticate(
            data=data,
            signature=signature,
            expected_address=get_random_checksum_address(),
        )

    # everything valid
    EIP712Auth.authenticate(data, signature, address)


def test_authenticate_eip4361(get_random_checksum_address):
    signer = InMemorySigner()
    siwe_message_data = {
        "domain": "login.xyz",
        "address": f"{signer.accounts[0]}",
        "statement": "Sign-In With Ethereum Example Statement",
        "uri": "did:key:z6Mkf55NiCvhxbLg6waBsJ58Hq4Nx6diedT7MGv1189gxV4i",
        "version": "1",
        "nonce": "bTyXgcQxn2htgkjJn",
        "chain_id": 1,
        "issued_at": f"{maya.now().iso8601()}",
        "resources": ["ceramic://*"],
    }
    valid_message = SiweMessage(**siwe_message_data).prepare_message()
    valid_message_signature = signer.sign_message(
        account=signer.accounts[0], message=valid_message.encode()
    )
    valid_address_for_signature = signer.accounts[0]

    # everything valid
    EIP4361Auth.authenticate(
        valid_message, valid_message_signature, valid_address_for_signature
    )

    # invalid data
    invalid_data = "just a regular old string"
    with pytest.raises(EvmAuth.InvalidData):
        EIP4361Auth.authenticate(
            data=invalid_data,
            signature=valid_message_signature,
            expected_address=valid_address_for_signature,
        )

    # signature not for expected address
    incorrect_signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - InvalidSignature",
    ):
        EIP4361Auth.authenticate(
            data=valid_message,
            signature=incorrect_signature,
            expected_address=valid_address_for_signature,
        )

    # invalid signature
    invalid_signature = "0xdeadbeef"
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - InvalidSignature",
    ):
        EIP4361Auth.authenticate(
            data=valid_message,
            signature=invalid_signature,
            expected_address=valid_address_for_signature,
        )

    # mismatch with expected address
    with pytest.raises(
        EvmAuth.AuthenticationFailed, match="signature not valid for expected address"
    ):
        EIP4361Auth.authenticate(
            data=valid_message,
            signature=valid_message_signature,
            expected_address=get_random_checksum_address(),
        )

    # expiration provided - not yet reached
    expiration_message_data = dict(siwe_message_data)
    expiration_message_data["expiration_time"] = maya.now().add(hours=1).iso8601()
    expiration_message = SiweMessage(**expiration_message_data).prepare_message()
    expiration_message_signature = signer.sign_message(
        account=valid_address_for_signature, message=expiration_message.encode()
    )
    EIP4361Auth.authenticate(
        expiration_message,
        expiration_message_signature.hex(),
        valid_address_for_signature,
    )  # authentication works

    # expiration provided - already expired
    already_expired_message_data = dict(siwe_message_data)
    already_expired_message_data["expiration_time"] = (
        maya.now().subtract(minutes=45).iso8601()
    )
    already_expired_message_data["issued_at"] = (
        maya.now().subtract(minutes=60).iso8601()
    )
    already_expired_message = SiweMessage(
        **already_expired_message_data
    ).prepare_message()
    already_expired_message_signature = signer.sign_message(
        account=valid_address_for_signature, message=already_expired_message.encode()
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - ExpiredMessage",
    ):
        EIP4361Auth.authenticate(
            already_expired_message,
            already_expired_message_signature.hex(),
            valid_address_for_signature,
        )  # authentication fails

    # not_before not yet reached
    not_before_message_data = dict(siwe_message_data)
    not_before_message_data["not_before"] = maya.now().add(hours=1).iso8601()
    not_before_message = SiweMessage(**not_before_message_data).prepare_message()
    not_before_signature = signer.sign_message(
        account=valid_address_for_signature, message=not_before_message.encode()
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - NotYetValidMessage",
    ):
        EIP4361Auth.authenticate(
            not_before_message, not_before_signature.hex(), valid_address_for_signature
        )

    # not_before already reached
    not_before_message_data = dict(siwe_message_data)
    not_before_message_data["not_before"] = maya.now().subtract(hours=1).iso8601()
    not_before_message = SiweMessage(**not_before_message_data).prepare_message()
    not_before_signature = signer.sign_message(
        account=valid_address_for_signature, message=not_before_message.encode()
    )
    EIP4361Auth.authenticate(
        not_before_message, not_before_signature.hex(), valid_address_for_signature
    )  # all is well

    # issued at in the future (sneaky!)
    futuristic_issued_at_message_data = dict(siwe_message_data)
    futuristic_issued_at_message_data["issued_at"] = (
        f"{maya.now().add(minutes=30).iso8601()}"
    )
    futuristic_issued_at_message = SiweMessage(
        **futuristic_issued_at_message_data
    ).prepare_message()
    futuristic_issued_at_message_signature = signer.sign_message(
        account=valid_address_for_signature,
        message=futuristic_issued_at_message.encode(),
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 issued-at datetime is in the future",
    ):
        EIP4361Auth.authenticate(
            futuristic_issued_at_message,
            futuristic_issued_at_message_signature.hex(),
            valid_address_for_signature,
        )

    # stale message - issued_at
    stale_message_data = dict(siwe_message_data)
    stale_message_data["issued_at"] = (
        f"{maya.now().subtract(hours=EIP4361Auth.FRESHNESS_IN_HOURS + 1).iso8601()}"
    )
    stale_message = SiweMessage(**stale_message_data).prepare_message()
    stale_message_signature = signer.sign_message(
        account=valid_address_for_signature, message=stale_message.encode()
    )
    with pytest.raises(
        EvmAuth.StaleMessage,
        match=f"EIP4361 message is more than {EIP4361Auth.FRESHNESS_IN_HOURS} hours old",
    ):
        EIP4361Auth.authenticate(
            stale_message, stale_message_signature.hex(), valid_address_for_signature
        )

    # old, but not stale and still valid
    old_but_not_stale_message_data = dict(siwe_message_data)
    old_but_not_stale_message_data["issued_at"] = (
        f"{maya.now().subtract(hours=EIP4361Auth.FRESHNESS_IN_HOURS - 1).iso8601()}"
    )
    old_but_not_stale_message = SiweMessage(
        **old_but_not_stale_message_data
    ).prepare_message()
    old_not_stale_message_signature = signer.sign_message(
        account=valid_address_for_signature, message=old_but_not_stale_message.encode()
    )
    EIP4361Auth.authenticate(
        old_but_not_stale_message,
        old_not_stale_message_signature.hex(),
        valid_address_for_signature,
    )

    # old but not stale; fails due to expiry time used in message itself
    not_stale_but_past_expiry = dict(old_but_not_stale_message_data)
    not_stale_but_past_expiry["expiration_time"] = (
        f"{maya.now().subtract(seconds=30).iso8601()}"
    )
    not_stale_but_past_expiry_message = SiweMessage(
        **not_stale_but_past_expiry
    ).prepare_message()
    not_stale_but_past_expiry_signature = signer.sign_message(
        account=valid_address_for_signature,
        message=not_stale_but_past_expiry_message.encode(),
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - ExpiredMessage",
    ):
        EIP4361Auth.authenticate(
            not_stale_but_past_expiry_message,
            not_stale_but_past_expiry_signature.hex(),
            valid_address_for_signature,
        )


def test_authenticate_eip1271(mocker, get_random_checksum_address):
    # smart contract wallet
    eip1271_mock_contract = mocker.Mock(spec=Contract)
    contract_address = get_random_checksum_address()
    eip1271_mock_contract.address = contract_address

    # signer for wallet
    data = f"I'm the owner of the smart contract wallet address {eip1271_mock_contract.address}"
    wallet_signer = InMemorySigner()
    valid_message_signature = wallet_signer.sign_message(
        account=wallet_signer.accounts[0], message=data.encode()
    )
    data_hash = defunct_hash_message(text=data)
    typedData = {"chain": TESTERCHAIN_CHAIN_ID, "dataHash": data_hash.hex()}

    def _isValidSignature(data_hash, signature_bytes):
        class ContractCall:
            def __init__(self, hash, signature):
                self.hash = hash
                self.signature = signature

            def call(self):
                recovered_address = Account._recover_hash(
                    message_hash=self.hash, signature=self.signature
                )
                if recovered_address == wallet_signer.accounts[0]:
                    return bytes(HexBytes("0x1626ba7e"))

                return bytes(HexBytes("0xffffffff"))

        return ContractCall(data_hash, signature_bytes)

    eip1271_mock_contract.functions.isValidSignature.side_effect = _isValidSignature

    # condition provider manager
    providers = mocker.Mock(spec=ConditionProviderManager)
    w3 = mocker.Mock()
    w3.eth.contract.return_value = eip1271_mock_contract
    providers.web3_endpoints.return_value = [w3]

    # valid signature
    EIP1271Auth.authenticate(
        typedData, valid_message_signature, eip1271_mock_contract.address, providers
    )

    # invalid typed data - no chain id
    with pytest.raises(EvmAuth.InvalidData):
        EIP1271Auth.authenticate(
            {
                "dataHash": data_hash.hex(),
            },
            valid_message_signature,
            eip1271_mock_contract.address,
            providers,
        )

    # invalid typed data - no data hash
    with pytest.raises(EvmAuth.InvalidData):
        EIP1271Auth.authenticate(
            {
                "chainId": TESTERCHAIN_CHAIN_ID,
            },
            valid_message_signature,
            eip1271_mock_contract.address,
            providers,
        )

    # use invalid signer
    invalid_signer = InMemorySigner()
    invalid_message_signature = invalid_signer.sign_message(
        account=invalid_signer.accounts[0], message=data.encode()
    )
    with pytest.raises(EvmAuth.AuthenticationFailed):
        EIP1271Auth.authenticate(
            typedData,
            invalid_message_signature,
            eip1271_mock_contract.address,
            providers,
        )

    # bad w3 instance failed for some reason
    w3_bad = mocker.Mock()
    w3_bad.eth.contract.side_effect = ValueError("something went wrong")
    providers.web3_endpoints.return_value = [w3_bad]
    with pytest.raises(EvmAuth.AuthenticationFailed, match="something went wrong"):
        EIP1271Auth.authenticate(
            typedData, valid_message_signature, eip1271_mock_contract.address, providers
        )
    assert w3_bad.eth.contract.call_count == 1, "one call that failed"

    # fall back to good w3 instances
    providers.web3_endpoints.return_value = [w3_bad, w3_bad, w3]
    EIP1271Auth.authenticate(
        typedData, valid_message_signature, eip1271_mock_contract.address, providers
    )
    assert w3_bad.eth.contract.call_count == 3, "two more calls that failed"

    # no connection to chain
    providers.web3_endpoints.side_effect = NoConnectionToChain(
        chain=TESTERCHAIN_CHAIN_ID
    )
    with pytest.raises(EvmAuth.AuthenticationFailed, match="No connection to chain ID"):
        EIP1271Auth.authenticate(
            typedData, valid_message_signature, eip1271_mock_contract.address, providers
        )
