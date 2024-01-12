from collections import OrderedDict

from .configuration_v1_to_v2 import configuration_v1_to_v2
from .configuration_v3_to_v4 import configuration_v3_to_v4
from .configuration_v4_to_v5 import configuration_v4_to_v5
from .configuration_v5_to_v6 import configuration_v5_to_v6
from .configuration_v6_to_v7 import configuration_v6_to_v7
from .configuration_v7_to_v8 import configuration_v7_to_v8
from .configuration_v8_to_v9 import configuration_v8_to_v9

MIGRATIONS = OrderedDict(
    {
        (1, 2): configuration_v1_to_v2,
        (2, 3): None,  # (no-op)
        (3, 4): configuration_v3_to_v4,
        (4, 5): configuration_v4_to_v5,
        (5, 6): configuration_v5_to_v6,
        (6, 7): configuration_v6_to_v7,
        (7, 8): configuration_v7_to_v8,
        (8, 9): configuration_v8_to_v9,
    }
)
