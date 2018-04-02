from crypto_kits.kits import MessageKit
from nkms.crypto.splitters import key_splitter, capsule_splitter


class UmbralMessageKit(MessageKit):
    splitter = capsule_splitter + key_splitter
