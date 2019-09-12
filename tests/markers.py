import os
import pytest


circleci_only = pytest.mark.skipif(condition=('CIRCLECI' not in os.environ),
                                   reason='Only run on CircleCI')
