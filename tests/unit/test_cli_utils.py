import sys

import pytest

from nucypher.cli.utils import strtobool

# Both custom and old implementations of strtobool can be directly compared in python < 3.12 to
# ensure they behave identically. In python >= 3.12, only the custom implementation is tested
STRTOBOOL_IMPLS = [("custom", strtobool)]
# Distutils was deprecated in Python 3.10 and removed in Python 3.12
if sys.version_info < (3, 12):
    from distutils.util import strtobool as old_strtobool

    STRTOBOOL_IMPLS.append(("old", old_strtobool))


@pytest.mark.parametrize(
    "value, expected",
    [
        ("y", True),
        ("yes", True),
        ("t", True),
        ("true", True),
        ("on", True),
        ("1", True),
        ("n", False),
        ("no", False),
        ("f", False),
        ("false", False),
        ("off", False),
        ("0", False),
        ("maybe", None),  # expecting ValueError
        ("", None),  # expecting ValueError
        ("2", None),  # expecting ValueError
        ("tru", None),  # expecting ValueError
        ("ye", None),  # expecting ValueError
        ("of", None),  # expecting ValueError
        ("yesno", None),  # expecting ValueError
        ("1.0", None),  # expecting ValueError
        ("0.0", None),  # expecting ValueError
        (" TRUE ", None),  # expecting ValueError due to spaces
    ],
)
@pytest.mark.parametrize("impl_name, strtobool_impl", STRTOBOOL_IMPLS)
def test_strtobool(impl_name, strtobool_impl, value, expected):
    if expected is None:
        # expecting ValueError
        with pytest.raises(ValueError) as exc_info:
            strtobool_impl(value)

        # ensure exception message is the same (not just a regex partial match)
        assert str(exc_info.value) == f"invalid truth value '{value.lower()}'"
        return

    assert (
        strtobool_impl(value) == expected
    ), f"{value} should yield {expected} for {impl_name} implementation"

    # upper case
    value_upper = value.upper()
    assert (
        strtobool_impl(value_upper) == expected
    ), f"{value_upper} should yield {expected} for {impl_name} implementation"

    # lower case
    value_lower = value.lower()
    assert (
        strtobool_impl(value_lower) == expected
    ), f"{value_lower} should yield {expected} for {impl_name} implementation"

    # alternate upper and lower
    value_even_index_upper = "".join(
        c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(value)
    )
    assert (
        strtobool_impl(value_even_index_upper) == expected
    ), f"{value_even_index_upper} should yield {expected} for {impl_name} implementation"

    value_even_index_lower = "".join(
        c.lower() if i % 2 == 0 else c.upper() for i, c in enumerate(value)
    )
    if len(value) > 1:
        assert value_even_index_lower != value_even_index_upper
    assert (
        strtobool_impl(value_even_index_lower) == expected
    ), f"{value_even_index_lower} should yield {expected} for {impl_name} implementation"
