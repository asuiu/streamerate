__author__ = "andrei.suiu@gmail.com"

import unittest

from streamerate import Procs, StartMethod, Threads, safe_call, stream
from streamerate.streams import Procs as StreamsProcs
from streamerate.streams import StartMethod as StreamsStartMethod
from streamerate.streams import Threads as StreamsThreads
from streamerate.streams import safe_call as StreamsSafeCall


class SlistTestCase(unittest.TestCase):
    def test_slist_nominal(self):
        s = stream(range(1, 4)).toList()
        self.assertListEqual([1, 2, 3], s)

    def test_root_exports_parallel_helpers(self):
        self.assertIs(Threads, StreamsThreads)
        self.assertIs(Procs, StreamsProcs)
        self.assertIs(StartMethod, StreamsStartMethod)
        self.assertIs(safe_call, StreamsSafeCall)

    def test_procs_default_start_method_is_auto(self):
        self.assertEqual(Procs(2).start_method, StartMethod.AUTO)
