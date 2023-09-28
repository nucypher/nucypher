from nucypher.blockchain.eth.signers.base import Signer
from nucypher.blockchain.eth.signers.software import InMemorySigner, KeystoreSigner

Signer._SIGNERS = {
    KeystoreSigner.uri_scheme(): KeystoreSigner,
    InMemorySigner.uri_scheme(): InMemorySigner,
}
