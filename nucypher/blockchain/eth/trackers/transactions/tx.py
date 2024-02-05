from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from eth_typing import ChecksumAddress
from eth_utils import encode_hex
from hexbytes import HexBytes
from web3.types import TxData, TxParams, TxReceipt

TxHash = HexBytes


@dataclass
class AsyncTx(ABC):
    id: int
    final: bool = field(default=None, init=False)
    on_broadcast: Optional[Callable] = field(default=None, init=False)
    on_finalized: Optional[Callable] = field(default=None, init=False)
    on_halt: Optional[Callable] = field(default=None, init=False)
    on_timeout: Optional[Callable] = field(default=None, init=False)
    on_revert: Optional[Callable] = field(default=None, init=False)
    on_error: Optional[Callable] = field(default=None, init=False)

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} final={self.final}>"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

    @abstractmethod
    def to_dict(self):
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: Dict):
        raise NotImplementedError


@dataclass
class FutureTx(AsyncTx):
    final: bool = field(default=False, init=False)
    params: TxParams
    _from: ChecksumAddress
    info: Optional[Dict] = None

    def __hash__(self):
        return hash(self.id)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "from": self._from,
            "params": _serialize_tx_params(self.params),
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            id=int(data["id"]),
            _from=data["from"],
            params=TxParams(data["params"]),
            info=dict(data["info"]),
        )


@dataclass
class PendingTx(AsyncTx):
    final: bool = field(default=False, init=False)
    txhash: TxHash
    created: int
    data: Optional[TxData] = None
    halt: bool = False

    def __hash__(self) -> int:
        return hash(self.txhash)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "txhash": self.txhash.hex(),
            "created": self.created,
            "data": self.data,
            "halt": self.halt,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            id=int(data["id"]),
            txhash=HexBytes(data["txhash"]),
            created=int(data["created"]),
            halt=bool(data["halt"]),
            data=dict(data) if data else dict(),
        )


@dataclass
class FinalizedTx(AsyncTx):
    final: bool = field(default=True, init=False)
    receipt: TxReceipt

    def __hash__(self) -> int:
        return hash(self.receipt["transactionHash"])

    def to_dict(self) -> Dict:
        return {"id": self.id, "receipt": _serialize_tx_receipt(self.receipt)}

    @classmethod
    def from_dict(cls, data: Dict):
        receipt = _deserialize_tx_receipt(data["receipt"])
        return cls(id=int(data["id"]), receipt=receipt)


def _serialize_tx_params(params: TxParams) -> Dict:
    """Serializes transaction parameters to a dictionary for disk storage."""
    data = params.get("data")
    if isinstance(data, bytes):
        data = encode_hex(data)
    result = {
        "nonce": params["nonce"],
        "chainId": params["chainId"],
        "gas": params["gas"],
        "type": params.get("type"),
        "to": params["to"],
        "value": params["value"],
        "data": data,
        "maxPriorityFeePerGas": params.get("maxPriorityFeePerGas"),
        "maxFeePerGas": params.get("maxFeePerGas"),
        "gasPrice": params.get("gasPrice"),
    }
    # filtrate Nones
    result = {k: v for k, v in result.items() if v is not None}
    return result


def _serialize_tx_receipt(receipt: TxReceipt) -> Dict:
    return {
        "transactionHash": encode_hex(receipt["transactionHash"]),
        "transactionIndex": receipt["transactionIndex"],
        "blockHash": encode_hex(receipt["blockHash"]),
        "blockNumber": receipt["blockNumber"],
        "from": receipt["from"],
        "to": receipt["to"],
        "cumulativeGasUsed": receipt["cumulativeGasUsed"],
        "gasUsed": receipt["gasUsed"],
        "status": receipt["status"],
    }


def _deserialize_tx_receipt(receipt: Dict) -> TxReceipt:
    return TxReceipt(
        {
            "transactionHash": HexBytes(receipt["transactionHash"]),
            "transactionIndex": receipt["transactionIndex"],
            "blockHash": HexBytes(receipt["blockHash"]),
            "blockNumber": receipt["blockNumber"],
            "from": receipt["from"],
            "to": receipt["to"],
            "cumulativeGasUsed": receipt["cumulativeGasUsed"],
            "gasUsed": receipt["gasUsed"],
            "status": receipt["status"],
        }
    )


def _make_tx_params(data: TxData) -> TxParams:
    """
    TxData -> TxParams: Creates a transaction parameters
    object from a transaction data object for broadcast.

    This operation is performed in order to "turnaround" the transaction
    data object as queried from the RPC provider (eth_getTransaction) into a transaction
    parameters object for strategics and re-broadcast (LocalAccount.sign_transaction).
    """
    params = TxParams(
        {
            "nonce": data["nonce"],
            "chainId": data["chainId"],
            "gas": data["gas"],
            "to": data["to"],
            "value": data["value"],
            "data": data.get("data", b""),
        }
    )
    if "gasPrice" in data:
        params["type"] = "0x01"
        params["gasPrice"] = data["gasPrice"]
    elif "maxFeePerGas" in data:
        params["type"] = "0x02"
        params["maxFeePerGas"] = data["maxFeePerGas"]
        params["maxPriorityFeePerGas"] = data["maxPriorityFeePerGas"]
    return params
