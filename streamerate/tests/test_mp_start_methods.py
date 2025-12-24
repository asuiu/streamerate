import multiprocessing
import os
import signal
import threading
import unittest

from streamerate.streams import stream

LOCK = threading.Lock()


def PICKABLE_LOCK_ACQUIRER(x):
    LOCK.acquire()
    try:
        return x
    finally:
        LOCK.release()


class MpStartMethodsTestCase(unittest.TestCase):
    """Verify that using 'spawn' (the default) avoids the classic fork-with-threads
    deadlock where a child process can inherit a locked mutex from a background
    thread that no longer exists in the child.

    The tests assert that invoking `mpmap`/`mpfastmap` with a `spawn` start method
    completes even when the parent has active threads holding locks, while an
    explicit `fork` start method reproduces the hang on platforms that support it.
    """

    def test_mpmap_spawn_default_avoids_fork_deadlock(self):
        self._assert_spawn_completes(self._run_mpmap_spawn_default, [0, 1, 2])
        self._assert_fork_deadlocks(self._run_mpmap_fork_deadlock)

    def test_mpfastmap_spawn_default_avoids_fork_deadlock(self):
        self._assert_spawn_completes(self._run_mpfastmap_spawn_default, {0, 1, 2})
        self._assert_fork_deadlocks(self._run_mpfastmap_fork_deadlock)

    def _assert_spawn_completes(self, target, expected):
        ctx = multiprocessing.get_context("spawn") if "spawn" in multiprocessing.get_all_start_methods() else multiprocessing.get_context()
        queue = ctx.Queue()
        process = ctx.Process(target=target, args=(queue,))
        process.start()
        process.join(timeout=1.0)
        try:
            if process.is_alive():
                process.terminate()
                process.join(timeout=1.0)
                self.fail("spawn start method did not finish in time")
            if process.exitcode not in (0, None):
                self.fail(f"spawn process exited with code {process.exitcode}")
            try:
                status, payload = queue.get(timeout=1.0)
            except Exception as exc:  # pylint: disable=broad-except,broad-exception-caught
                self.fail(f"spawn process returned no result: {exc!s}")
            self.assertEqual(status, "ok")
            self.assertEqual(payload, expected)
        finally:
            queue.close()
            queue.join_thread()

    def _assert_fork_deadlocks(self, target):
        if "fork" not in multiprocessing.get_all_start_methods():
            return
        ctx = multiprocessing.get_context("spawn") if "spawn" in multiprocessing.get_all_start_methods() else multiprocessing.get_context()
        process = ctx.Process(target=target)
        process.start()
        process.join(timeout=1.0)
        if not process.is_alive():
            self.fail("fork start method finished unexpectedly")
        os.killpg(process.pid, signal.SIGKILL)
        process.join(timeout=1.0)
        self.assertFalse(process.is_alive())

    @staticmethod
    def _start_lock_holder():
        ready = threading.Event()
        release = threading.Event()

        def _hold_lock():
            LOCK.acquire()
            try:
                ready.set()
                release.wait()
            finally:
                LOCK.release()

        thread = threading.Thread(target=_hold_lock, daemon=True)
        thread.start()
        return thread, ready, release

    @classmethod
    def _run_mpmap_spawn_default(cls, result_queue):
        lock_holder, ready, release = cls._start_lock_holder()
        if not ready.wait(timeout=1.0):
            result_queue.put(("error", "lock_holder_not_ready"))
            return
        try:
            result = stream(range(3)).mpmap(PICKABLE_LOCK_ACQUIRER, poolSize=2).toList()
            result_queue.put(("ok", result))
        except Exception as exc:  # pylint: disable=broad-except,broad-exception-caught
            result_queue.put(("error", repr(exc)))
        finally:
            release.set()
            lock_holder.join(timeout=1.0)

    @classmethod
    def _run_mpfastmap_spawn_default(cls, result_queue):
        lock_holder, ready, release = cls._start_lock_holder()
        if not ready.wait(timeout=1.0):
            result_queue.put(("error", "lock_holder_not_ready"))
            return
        try:
            result = stream(range(3)).mpfastmap(PICKABLE_LOCK_ACQUIRER, poolSize=2).toSet()
            result_queue.put(("ok", result))
        except Exception as exc:  # pylint: disable=broad-except,broad-exception-caught
            result_queue.put(("error", repr(exc)))
        finally:
            release.set()
            lock_holder.join(timeout=1.0)

    @classmethod
    def _run_mpmap_fork_deadlock(cls):
        os.setsid()
        lock_holder, ready, release = cls._start_lock_holder()
        if not ready.wait(timeout=1.0):
            return
        try:
            stream(range(3)).mpmap(PICKABLE_LOCK_ACQUIRER, poolSize=2, start_method="fork").toList()
        finally:
            release.set()
            lock_holder.join(timeout=1.0)

    @classmethod
    def _run_mpfastmap_fork_deadlock(cls):
        os.setsid()
        lock_holder, ready, release = cls._start_lock_holder()
        if not ready.wait(timeout=1.0):
            return
        try:
            stream(range(3)).mpfastmap(PICKABLE_LOCK_ACQUIRER, poolSize=2, start_method="fork").toSet()
        finally:
            release.set()
            lock_holder.join(timeout=1.0)
