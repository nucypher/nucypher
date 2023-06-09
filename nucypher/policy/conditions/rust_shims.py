import json
from typing import List

from nucypher_core import ReencryptionRequest, Conditions

from nucypher.policy.conditions.lingo import ConditionLingo


def _serialize_rust_lingos(lingos: List[Conditions]) -> Conditions:
    lingo_lists = list()
    for lingo in lingos:
        if lingo:
            lingo = json.loads((str(lingo)))
        lingo_lists.append(lingo)
    rust_lingos = Conditions(json.dumps(lingo_lists))
    return rust_lingos


def _deserialize_rust_lingos(reenc_request: ReencryptionRequest):
    """Shim for nucypher-core lingos"""
    json_lingos = json.loads(str(reenc_request.conditions))
    lingo = [
        ConditionLingo.from_dict(lingo) if lingo else None for lingo in json_lingos
    ]
    return lingo
