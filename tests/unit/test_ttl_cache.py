import random
from concurrent.futures import ThreadPoolExecutor, wait
from unittest.mock import patch

import maya
import pytest

from nucypher.utilities.cache import TTLCache


def test_cache_invalid_ttl():
    with pytest.raises(ValueError):
        TTLCache(ttl=0)

    with pytest.raises(ValueError):
        TTLCache(ttl=-1)


def test_cache_invalid_key_value_pair():
    ttl_cache = TTLCache(ttl=60)
    with pytest.raises(ValueError):
        ttl_cache[None] = "a"

    with pytest.raises(ValueError):
        ttl_cache["a"] = None


def test_cache_get_remove_non_existent_entry():
    ttl_cache = TTLCache(ttl=60)

    # try to get non-existent entry
    assert ttl_cache[1] is None

    # try to remove non-existent entry
    ttl_cache.remove(1)


def test_cache_pop():
    ttl = 60
    ttl_cache = TTLCache(ttl=ttl)

    now = maya.now()
    ttl_cache[1] = "a"
    ttl_cache[2] = "b"
    ttl_cache[3] = "c"
    ttl_cache[4] = "c"

    assert len(ttl_cache) == 4

    assert ttl_cache.pop(3) == "c"
    assert len(ttl_cache) == 3

    # pop non-existent entry with default none
    assert ttl_cache.pop(42) is None
    assert len(ttl_cache) == 3

    # pop non-existent entry with default specified
    assert ttl_cache.pop(42, "-1") == "-1"
    assert len(ttl_cache) == 3

    assert ttl_cache.pop(1) == "a"
    assert len(ttl_cache) == 2

    assert ttl_cache.pop(2) == "b"
    assert len(ttl_cache) == 1

    # ensure last entry still present
    assert ttl_cache[4] == "c"

    # pop expired entry
    def maya_now():
        # pretend time has passed
        return now.add(seconds=ttl + 1)

    with patch("maya.now", maya_now):
        assert ttl_cache.pop(4) is None, "entry should be expired"


def test_cache_items():
    ttl = 60  # 60s
    ttl_cache = TTLCache(ttl=ttl)

    now = maya.now()

    ttl_cache[1] = "a"
    ttl_cache[2] = "b"
    assert len(ttl_cache) == 2

    def maya_now_1():
        # pretend time has passed
        return now.add(seconds=ttl / 2)

    with patch("maya.now", maya_now_1):
        # items added later and will not be expired
        ttl_cache[3] = "c"
        ttl_cache[4] = "d"
        ttl_cache[5] = "e"

    assert len(ttl_cache) == 5

    cache_key_value_pairs = dict(ttl_cache.items())
    assert len(cache_key_value_pairs) == len(ttl_cache)
    assert cache_key_value_pairs[1] == "a"
    assert cache_key_value_pairs[2] == "b"
    assert cache_key_value_pairs[3] == "c"
    assert cache_key_value_pairs[4] == "d"
    assert cache_key_value_pairs[5] == "e"

    def maya_now_2():
        # pretend time has passed
        return now.add(seconds=ttl + 1)

    with patch("maya.now", maya_now_2):
        latest_cache_key_value_pairs = dict(ttl_cache.items())
        # 2 expired entries not returned
        assert len(latest_cache_key_value_pairs) == 3
        assert cache_key_value_pairs[3] == "c"
        assert cache_key_value_pairs[4] == "d"
        assert cache_key_value_pairs[5] == "e"


def test_cache_simple_no_expiry():
    ttl = 60  # 60s
    ttl_cache = TTLCache(ttl=ttl)

    key_value_pairs = {1: "a", 2: "b", 3: "c", 4: "d"}

    for key, value in key_value_pairs.items():
        ttl_cache[key] = value
        assert ttl_cache[key] == value

    assert len(ttl_cache) == len(key_value_pairs)

    cached_key_value_pairs = dict(ttl_cache.items())
    assert cached_key_value_pairs == key_value_pairs

    key_to_remove = list(key_value_pairs.keys())[0]
    ttl_cache.remove(key_to_remove)
    assert len(ttl_cache) == len(key_value_pairs) - 1
    assert ttl_cache[key_to_remove] is None

    # no expired entries - no change in length after purge
    ttl_cache.purge_expired()
    assert len(ttl_cache) == len(key_value_pairs) - 1

    ttl_cache.clear()
    assert len(ttl_cache) == 0
    assert ttl_cache[list(key_value_pairs.keys())[2]] is None


def test_cache_expiry_all_entries():
    ttl = 60  # 60s
    ttl_cache = TTLCache(ttl=ttl)

    now = maya.now()

    ttl_cache[1] = "a"
    ttl_cache[2] = "b"

    def maya_now():
        # pretend time has passed
        return now.add(seconds=ttl + 1)

    with patch("maya.now", maya_now):
        assert ttl_cache[1] is None, "entry should be expired"
        assert ttl_cache[2] is None, "entry should be expired"

    assert len(ttl_cache) == 0


def test_cache_expiry_some_entries():
    ttl = 60  # 60s
    ttl_cache = TTLCache(ttl=ttl)

    now = maya.now()

    ttl_cache[1] = "a"
    assert len(ttl_cache) == 1
    assert ttl_cache[1] == "a"

    def maya_now_1():
        # pretend time has passed
        return now.add(seconds=ttl / 3)  # 20s

    with patch("maya.now", maya_now_1):
        ttl_cache[2] = "b"
        assert len(ttl_cache) == 2
        assert ttl_cache[1] == "a"
        assert ttl_cache[2] == "b"

    def maya_now_2():
        return now.add(seconds=(ttl / 3) * 2)  # 40s

    with patch("maya.now", maya_now_2):
        ttl_cache[3] = "c"
        assert len(ttl_cache) == 3
        assert ttl_cache[1] == "a"
        assert ttl_cache[2] == "b"
        assert ttl_cache[3] == "c"

    def maya_now_expired_1():
        return now.add(seconds=ttl + 1)

    with patch("maya.now", maya_now_expired_1):
        assert ttl_cache[1] is None  # expired entry
        assert ttl_cache[2] == "b"
        assert ttl_cache[3] == "c"
        assert len(ttl_cache) == 2

    def maya_now_expired_2():
        return now.add(seconds=(ttl / 3) + ttl + 1)

    with patch("maya.now", maya_now_expired_2):
        assert ttl_cache[1] is None
        assert ttl_cache[2] is None
        assert ttl_cache[3] == "c"
        assert len(ttl_cache) == 1

    def maya_now_expired_3():
        return now.add(seconds=(ttl / 3 * 2) + ttl + 1)

    with patch("maya.now", maya_now_expired_3):
        assert ttl_cache[1] is None
        assert ttl_cache[2] is None
        assert ttl_cache[3] is None
        assert len(ttl_cache) == 0


def test_cache_purge_expired_entries():
    ttl = 60  # 60s
    ttl_cache = TTLCache(ttl=ttl)

    now = maya.now()

    ttl_cache[1] = "a"
    ttl_cache[2] = "b"
    ttl_cache[3] = "c"

    assert len(ttl_cache) == 3
    assert ttl_cache[1] == "a"
    assert ttl_cache[2] == "b"
    assert ttl_cache[3] == "c"

    def maya_now():
        # pretend time has passed
        return now.add(seconds=ttl + 1)

    with patch("maya.now", maya_now):
        ttl_cache.purge_expired()
        assert len(ttl_cache) == 0


def test_cache_simple_concurrency():
    ttl = 60  # 60s
    ttl_cache = TTLCache(ttl=ttl)

    def store_random_entries(ttl_cache: TTLCache):
        num_times = 30
        for i in range(num_times):
            # run 30 times with some repeats
            key = random.randint(1, 25)
            value = random.randint(1, 100)
            ttl_cache[key] = value

            if i > int(num_times * 2 / 3):
                # pick a random key to possibly remove
                random_key_to_remove = random.randint(1, 25)
                ttl_cache.remove(random_key_to_remove)

        # do some purging - does nothing since no entries expire but
        # ensures that locks are acquired/released
        ttl_cache.purge_expired()

    num_total_executions = 30
    assert len(ttl_cache) == 0

    # use thread pool
    n_threads = 10
    with ThreadPoolExecutor(n_threads) as executor:
        # download each url and save as a local file
        futures = []
        for _ in range(num_total_executions):
            f = executor.submit(store_random_entries, ttl_cache)
            futures.append(f)

        wait(futures, timeout=5)  # only wait max 5s

    # probability that at the end of concurrent execution there is no entry
    # is very low (not 0) - but I can live with that.
    assert (
        len(ttl_cache) > 0
    ), "this can fail with a very low probability - most likely rerun test"
