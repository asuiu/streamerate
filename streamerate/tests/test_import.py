__author__ = 'andrei.suiu@gmail.com'

import unittest

from streamerate import stream


class SlistTestCase(unittest.TestCase):
    def test_slist_nominal(self):
        l = [1, 2, 3]
        s = stream(range(1, 4)).toList()
        self.assertListEqual(s, l)