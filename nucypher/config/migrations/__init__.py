from collections import OrderedDict

from .configuration_v1_to_v2 import configuration_v1_to_v2
from .configuration_v3_to_v4 import configuration_v3_to_v4
from .configuration_v4_to_v6 import configuration_v4_to_v6

MIGRATIONS = OrderedDict(
    {
        (1, 2): configuration_v1_to_v2,
        (2, 3): None,  # (no-op)
        (3, 4): configuration_v3_to_v4,
        (4, 6): configuration_v4_to_v6,
    }
)
