from abc import ABC
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from hexbytes import HexBytes
from web3.types import TxData, TxParams, TxReceipt

TxHash = HexBytes


@dataclass
class AsyncTx(ABC):
    id: int
    final: bool = field(default=None, init=False)


@dataclass
class FutureTx(AsyncTx):
    final: bool = field(default=False, init=False)
    params: TxParams
    signer: Callable
    info: Optional[Dict] = None

    def __hash__(self):
        return hash(self.id)

    def to_dict(self):
        return {
            "id": self.id,
            "params": _serialize_tx_params(self.params),
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, data: Dict, signer: Optional[Callable] = None):
        if not signer:
            raise NotImplementedError(
                "Signer must be provided to deserialize a FutureTx"
            )
        return cls(
            id=int(data["id"]),
            params=TxParams(data["params"]),
            info=dict(data["info"]),
            signer=signer,
        )


@dataclass
class PendingTx(AsyncTx):
    final: bool = field(default=False, init=False)
    txhash: TxHash
    created: int
    data: Optional[TxData] = None
    capped: bool = False

    def __hash__(self) -> int:
        return hash(self.txhash)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "txhash": self.txhash.hex(),
            "created": self.created,
            "data": self.data,
            "capped": self.capped,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            id=int(data["id"]),
            txhash=HexBytes(data["txhash"]),
            created=int(data["created"]),
            capped=bool(data["capped"]),
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
        return cls(id=int(data["id"]), receipt=TxReceipt(data["receipt"]))


def _serialize_tx_params(params: TxParams) -> Dict:
    """Serializes transaction parameters to a dictionary for disk storage."""
    data = params.get("data", b"")
    if isinstance(data, bytes):
        data = data.hex()
    return {
        "nonce": params["nonce"],
        "maxPriorityFeePerGas": params["maxPriorityFeePerGas"],
        "maxFeePerGas": params["maxFeePerGas"],
        "chainId": params["chainId"],
        "gas": params["gas"],
        "type": params.get("type", ""),
        "from": params["from"],
        "to": params["to"],
        "value": params["value"],
        "data": data,
    }


def _serialize_tx_receipt(receipt: TxReceipt) -> Dict:
    return {
        "transactionHash": receipt["transactionHash"].hex(),
        "transactionIndex": receipt["transactionIndex"],
        "blockHash": receipt["blockHash"].hex(),
        "blockNumber": receipt["blockNumber"],
        "from": receipt["from"],
        "to": receipt["to"],
        "cumulativeGasUsed": receipt["cumulativeGasUsed"],
        "gasUsed": receipt["gasUsed"],
        "contractAddress": receipt["contractAddress"],
        "logs": [dict(_log) for _log in receipt["logs"]],
        "status": receipt["status"],
        "logsBloom": receipt["logsBloom"].hex(),
        "root": receipt["root"].hex(),
        "type": receipt["type"],
        "effectiveGasPrice": receipt["effectiveGasPrice"],
    }


def _make_tx_params(tx: TxData) -> TxParams:
    """Creates a transaction parameters object from a transaction data object for broadcast."""
    return TxParams(
        {
            "nonce": tx["nonce"],
            "maxPriorityFeePerGas": tx["maxPriorityFeePerGas"],
            "maxFeePerGas": tx["maxFeePerGas"],
            "chainId": tx["chainId"],
            "gas": tx["gas"],
            "type": "0x2",
            "from": tx["from"],
            "to": tx["to"],
            "value": tx["value"],
            "data": tx.get("data", b""),
        }
    )
