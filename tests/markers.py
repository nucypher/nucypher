

import os
import pytest


circleci_only = pytest.mark.skipif(condition=('CIRCLECI' not in os.environ), reason='Only run on CircleCI')
skip_on_circleci = pytest.mark.skipif(condition=('CIRCLECI' in os.environ), reason='Do not run on CircleCI')
