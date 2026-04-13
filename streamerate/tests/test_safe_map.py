import time
import unittest

from streamerate import stream
from streamerate.streams import Procs, Threads, safe_call


class FailUntilN:
    def __init__(self, fails_needed, exception_type=ValueError):
        self.fails_needed = fails_needed
        self.exception_type = exception_type
        self.calls = 0

    def __call__(self, x):
        self.calls += 1
        if self.calls <= self.fails_needed:
            raise self.exception_type(f"Fail {self.calls}")
        return x * 2


def failing_func(x):
    if x % 2 == 0:
        raise ValueError(f"Even number: {x}")
    return x * 2


def unhandled_fail_func(x):
    raise KeyError("Unhandled")


class TestSafeCall(unittest.TestCase):
    def test_safe_call_success(self):
        f = safe_call(lambda x: x * 2)
        self.assertEqual(f(5), 10)

    def test_safe_call_catch(self):
        f = safe_call(failing_func, exceptions=(ValueError,))
        res = f(2)
        self.assertIsInstance(res, ValueError)
        self.assertEqual(str(res), "Even number: 2")

    def test_safe_call_raise(self):
        f = safe_call(unhandled_fail_func, exceptions=(ValueError,))
        with self.assertRaises(KeyError):
            f(2)

    def test_safe_call_retry_success(self):
        f = safe_call(FailUntilN(2, ValueError), exceptions=(ValueError,), retries=2)
        res = f(5)
        self.assertEqual(res, 10)

    def test_safe_call_retry_exhausted(self):
        f = safe_call(FailUntilN(3, ValueError), exceptions=(ValueError,), retries=2)
        res = f(5)
        self.assertIsInstance(res, ValueError)
        self.assertEqual(str(res), "Fail 3")

    def test_safe_call_delay_backoff(self):
        start = time.time()
        f = safe_call(FailUntilN(2, ValueError), exceptions=(ValueError,), retries=2, delay=0.1, backoff=2.0)
        res = f(5)
        end = time.time()
        self.assertEqual(res, 10)
        # Should wait 0.1s + 0.2s = 0.3s approx
        self.assertTrue(0.25 <= (end - start) < 0.45, f"Took {end - start}")


class TestSafeMap(unittest.TestCase):
    def test_safe_map_sequential(self):
        s = stream([1, 2, 3, 4]).safe_map(failing_func, exceptions=(ValueError,))
        res = s.toList()
        self.assertEqual(res[0], 2)
        self.assertIsInstance(res[1], ValueError)
        self.assertEqual(res[2], 6)
        self.assertIsInstance(res[3], ValueError)

    def test_safe_map_threads(self):
        s = stream([1, 2, 3, 4]).safe_map(failing_func, parallel=Threads(2), exceptions=(ValueError,))
        res = s.toList()
        self.assertEqual(res[0], 2)
        self.assertIsInstance(res[1], ValueError)
        self.assertEqual(res[2], 6)
        self.assertIsInstance(res[3], ValueError)

    def test_safe_map_procs(self):
        # We need functions to be picklable, so failing_func is defined at module level
        s = stream([1, 2, 3, 4]).safe_map(failing_func, parallel=Procs(2), exceptions=(ValueError,))
        res = s.toList()
        self.assertEqual(res[0], 2)
        self.assertIsInstance(res[1], ValueError)
        self.assertEqual(res[2], 6)
        self.assertIsInstance(res[3], ValueError)


if __name__ == "__main__":
    unittest.main()
