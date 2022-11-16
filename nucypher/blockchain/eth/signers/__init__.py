

from nucypher.blockchain.eth.signers.base import Signer
from nucypher.blockchain.eth.signers.software import KeystoreSigner

Signer._SIGNERS = {
    KeystoreSigner.uri_scheme(): KeystoreSigner,
}
