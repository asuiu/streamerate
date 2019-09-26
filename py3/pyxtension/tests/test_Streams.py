import io
import pickle
import random
import sys
import time
import unittest
from functools import partial
from io import BytesIO
from unittest.mock import MagicMock

from pyxtension.Json import JsonList, Json
from pyxtension.streams import stream, slist, sset, sdict, ItrFromFunc, defaultstreamdict, TqdmMapper

ifilter = filter
xrange = range

__author__ = 'ASU'


def PICKABLE_DUMB_FUNCTION(x):
    return x


def PICKABLE_SLEEP_FUNC(el):
    time.sleep(0.05)
    return el * el


class SlistTestCase(unittest.TestCase):
    def test_slist_str_nominal(self):
        l = [1, 2, 3]
        s = slist(l)
        s1 = str(s)
        self.assertEqual(str(s), str(l))

    def test_slist_repr_nominal(self):
        l = [1, 2, 3]
        s = slist(l)
        self.assertEqual(repr(s), repr(l))

    def test_slist_add_list(self):
        l1 = slist([1, 2])
        l2 = slist([3, 4])
        l3 = (l1 + l2)
        self.assertIsInstance(l3, stream)
        self.assertIsInstance(l3, slist)
        self.assertListEqual(l3.toList(), [1, 2, 3, 4])

    def test_slist_add_stream(self):
        l1 = slist([1, 2])
        l2 = stream([3, 4])
        l3 = (l1 + l2)
        self.assertIsInstance(l3, stream)
        self.assertNotIsInstance(l3, slist)
        self.assertListEqual(l3.toList(), [1, 2, 3, 4])

    def test_slist_iadd(self):
        l1 = slist([1, 2])
        l2 = slist([3, 4])
        l1 += l2
        self.assertIsInstance(l1, slist)
        self.assertListEqual(l1.toList(), [1, 2, 3, 4])

    def testStreamList(self):
        l = lambda: slist((1, 2, 3))
        self.assertEqual(l().toList(), [1, 2, 3])
        self.assertEqual(l()[-1], 3)

    def test_reversedNominal(self):
        s = stream([1, 2, 3])
        self.assertListEqual(s.reversed().toList(), [3, 2, 1])


class SdictTestCase(unittest.TestCase):
    def testSdictToJson(self):
        j = stream((("a", 2), (3, 4))).toMap().toJson()
        self.assertIsInstance(j, Json)
        self.assertEqual(j.a, 2)
        self.assertDictEqual(j, {'a': 2, 3: 4})

    def test_sdict(self):
        d = sdict({1: 2, 3: 4})
        self.assertListEqual(d.items().map(lambda t: t).toList(), [(1, 2), (3, 4)])

    def test_sdict_copy(self):
        d = sdict({1: 2, 3: 4})
        copy = d.copy()
        self.assertIsInstance(copy, sdict)
        self.assertSetEqual(set(d.items()), set(copy.items()))
        d[1] = 3
        self.assertEqual(copy[1], 2)

    def test_reversed_raises(self):
        s = sdict({1: 1, 2: 2})
        with self.assertRaises(TypeError):
            s.reversed().toList()


class SsetTestCase(unittest.TestCase):
    def testStreamSet(self):
        s = lambda: sset([1, 2, 3, 2])
        self.assertEqual(s().size(), 3)
        self.assertEqual(s().map(lambda x: x).toList(), [1, 2, 3])
        self.assertEqual(len(s()), 3)

    def test_sset_updateReturnsSelf(self):
        s = sset((1, 2))
        l = s.update((2, 3))
        self.assertEqual(l, set((1, 2, 3)))

    def test_sset_intersection_updateReturnsSelf(self):
        self.assertEqual(sset((1, 2)).update(set((2, 3))), set((1, 2, 3)))

    def test_ssetChaining(self):
        s = sset().add(0).clear().add(1).add(2).remove(2).discard(3).update(set((3, 4, 5))) \
            .intersection_update(set((1, 3, 4))).difference_update(set((4,))).symmetric_difference_update(set((3, 4)))
        self.assertEqual(s, set((1, 4)))

    def test_reversed_raises(self):
        s = sset(iter(range(1, 4)))
        with self.assertRaises(TypeError):
            s.reversed().toList()

    def test_disjunction(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s3 = s1 | s2
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {1, 2, 3, 4})

    def test_conjunction(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s3 = s1 & s2
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {1, 2})

    def test_sub(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s3 = s1 - s2
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {3})

    def test_xor(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s3 = s1 ^ s2
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {3, 4})

    def test_union(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s2_2 = sset({1, 2, 5})
        s3 = s1.union(s2, s2_2)
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {1, 2, 3, 4, 5})

    def test_intersection(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s2_2 = sset({1, 2, 5})
        s3 = s1.intersection(s2, s2_2)
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {1, 2})

    def test_difference(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s2_2 = sset({1, 2, 5})
        s3 = s1.difference(s2, s2_2)
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {3, })

    def test_symmetric_difference(self):
        s1 = sset({1, 2, 3})
        s2 = sset({1, 2, 4})
        s3 = s1.symmetric_difference(s2)
        self.assertIsInstance(s3, sset)
        self.assertSetEqual(s3, {3, 4})

class StreamTestCase(unittest.TestCase):
    def setUp(self):
        self.s = lambda: stream((1, 2, 3))

    def test_fastFlatMap_reiteration(self):
        l = stream(ItrFromFunc(lambda: (xrange(i) for i in xrange(5)))).fastFlatMap()
        self.assertEqual(l.toList(), [0, 0, 1, 0, 1, 2, 0, 1, 2, 3])
        self.assertEqual(l.toList(),
                         [0, 0, 1, 0, 1, 2, 0, 1, 2, 3])  # second time to assert the regeneration of generator

    def test_fastmap_reiteration(self):
        l = stream(ItrFromFunc(lambda: (xrange(i) for i in xrange(5)))).fastmap(len)
        self.assertEqual(l.toList(), [0, 1, 2, 3, 4])
        self.assertEqual(l.toList(), [0, 1, 2, 3, 4])  # second time to assert the regeneration of generator

    def testStream(self):
        s = self.s
        self.assertEqual(list(ifilter(lambda i: i % 2 == 0, s())), [2])
        self.assertEqual(list(s().filter(lambda i: i % 2 == 0)), [2])
        self.assertEqual(s().filter(lambda i: i % 2 == 0).toList(), [2])
        self.assertEqual(s()[1], 2)
        self.assertEqual(s()[1:].toList(), [2, 3])
        self.assertEqual(s().take(2).toList(), [1, 2])
        self.assertAlmostEqual(stream((0, 1, 2, 3)).filter(lambda x: x > 0).entropy(), 1.4591479)
        self.assertEqual(stream([(1, 2), (3, 4)]).zip().toList(), [(1, 3), (2, 4)])

    def test_filterFromGeneratorReinstantiatesProperly(self):
        s = stream(ItrFromFunc(lambda: (i for i in xrange(5))))
        s = s.filter(lambda e: e % 2 == 0)
        self.assertEqual(s.toList(), [0, 2, 4])
        self.assertEqual(s.toList(), [0, 2, 4])
        s = stream(xrange(5)).filter(lambda e: e % 2 == 0)
        self.assertEqual(s.toList(), [0, 2, 4])
        self.assertEqual(s.toList(), [0, 2, 4])

    def test_streamExists(self):
        s = stream([0, 1])
        self.assertEqual(s.exists(lambda e: e == 0), True)
        self.assertEqual(s.exists(lambda e: e == 2), False)

    def test_stream_str_doesntChangeStream(self):
        s = stream(iter((1, 2, 3, 4)))
        str(s)
        self.assertListEqual(s.toList(), [1, 2, 3, 4])

    def test_stream_repr_doesntChangeStream(self):
        s = stream(iter((1, 2, 3, 4)))
        repr(s)
        self.assertListEqual(s.toList(), [1, 2, 3, 4])

    def testStreamToJson(self):
        j = stream((("a", 2), (3, 4))).toJson()
        self.assertIsInstance(j, JsonList)
        self.assertListEqual(j, [["a", 2], [3, 4]])

    def testStreamsFromGenerator(self):
        sg = stream(ItrFromFunc(lambda: (i for i in range(4))))
        self.assertEqual(sg.size(), 4)
        self.assertEqual(sg.size(), 4)
        self.assertEqual(sg.filter(lambda x: x > 1).toList(), [2, 3])
        self.assertEqual(sg.filter(lambda x: x > 1).toList(), [2, 3])
        self.assertEqual(sg.map(lambda x: x > 1).toList(), [False, False, True, True])
        self.assertEqual(sg.map(lambda x: x > 1).toList(), [False, False, True, True])
        self.assertEqual(sg.head(), 0)
        self.assertEqual(sg.head(), 0)
        self.assertEqual(sg.map(lambda i: i ** 2).enumerate().toList(), [(0, 0), (1, 1), (2, 4), (3, 9)])
        self.assertEqual(sg.reduce(lambda x, y: x + y, 5), 11)

    def testStreamPickling(self):
        sio = BytesIO()
        expected = slist(slist((i,)) for i in xrange(10))
        expected.dumpToPickle(sio)
        sio = BytesIO(sio.getvalue())

        result = stream.loadFromPickled(sio)
        self.assertListEqual(expected, list(result))

    def test_StreamFileReading(self):
        sio = BytesIO()
        expected = slist(slist((i,)) for i in xrange(10))
        expected.dumpToPickle(sio)
        sio = BytesIO(sio.getvalue())

        result = stream.loadFromPickled(sio)
        self.assertEqual(list(expected), list(result))

    def test_flatMap_nominal(self):
        s = stream([[1, 2], [3, 4], [4, 5]])
        self.assertListEqual(s.flatMap().toList(), [1, 2, 3, 4, 4, 5])

    def test_flatMap_withPredicate(self):
        s = stream(({1: 2, 3: 4}, {5: 6, 7: 8}))
        self.assertEqual(s.flatMap(dict.items).toSet(), set(((1, 2), (5, 6), (3, 4), (7, 8))))

    def test_flatMap_reiteration(self):
        l = stream(ItrFromFunc(lambda: (xrange(i) for i in xrange(5)))).flatMap()
        self.assertEqual(l.toList(), [0, 0, 1, 0, 1, 2, 0, 1, 2, 3])
        self.assertEqual(l.toList(),
                          [0, 0, 1, 0, 1, 2, 0, 1, 2, 3])  # second time to assert the regeneration of generator

    def test_flatMap_defaultIdentityFunction(self):
        l = slist(({1: 2, 3: 4}, {5: 6, 7: 8}))
        self.assertEqual(l.flatMap().toSet(), set((1, 3, 5, 7)))

    def test_reduceUsesInitProperly(self):
        self.assertEqual(slist([sset((1, 2)), sset((3, 4))]).reduce(lambda x, y: x.update(y)), set((1, 2, 3, 4)))
        self.assertEqual(slist([sset((1, 2)), sset((3, 4))]).reduce(lambda x, y: x.update(y), sset()),
                          set((1, 2, 3, 4)))

    def test_maxes(self):
        self.assertEqual(stream(['a', 'abc', 'abcd', 'defg', 'cde']).maxes(lambda s: len(s)), ['abcd', 'defg'])

    def test_mins(self):
        self.assertEqual(stream(['abc', 'a', 'abcd', 'defg', 'cde']).mins(lambda s: len(s)), ['a'])

    def test_min_nominal(self):
        self.assertEqual(stream([2, 1]).min(), 1)
        self.assertEqual(stream(['abc', 'a']).min(key=len), 'a')

    def test_min_raises_on_empty_sequence(self):
        with self.assertRaises(ValueError):
            stream().min()

    def test_min_default_nominal(self):
        self.assertEqual(stream([2, 1]).min_default('default'), 1)
        self.assertEqual(stream(['abc', 'a']).min_default('default', key=len), 'a')
        self.assertEqual(stream().min_default('default'), 'default')

    def test_defaultstreamdictBasics(self):
        dd = defaultstreamdict(slist)
        dd[1].append(2)
        self.assertEqual(dd, {1: [2]})

    def test_defaultstreamdictSerialization(self):
        dd = defaultstreamdict(slist)
        dd[1].append(2)
        s = pickle.dumps(dd)
        newDd = pickle.loads(s)
        self.assertEqual(newDd, dd)
        self.assertIsInstance(newDd[1], slist)

    def test_stream_add(self):
        s1 = stream([1, 2])
        s2 = stream([3, 4])
        s3 = s1 + s2
        ll = s3.toList()
        self.assertEqual(s3.toList(), [1, 2, 3, 4])
        self.assertEqual(s3.toList(), [1, 2, 3, 4])  # second time to exclude one time iterator bug
        s1 = s1 + s2
        self.assertEqual(s1.toList(), [1, 2, 3, 4])
        self.assertEqual(s1.toList(), [1, 2, 3, 4])  # second time to exclude one time iterator bug

    def test_stream_iadd(self):
        s1 = stream([1, 2])
        s1 += [3, 4]
        s1 += stream(xrange(5, 6))  # use xrange to cover the iterator case
        self.assertEqual(s1.toList(), [1, 2, 3, 4, 5])
        self.assertEqual(s1.toList(), [1, 2, 3, 4, 5])  # second time to exclude one time iterator bug
        self.assertEqual(s1.toList(), [1, 2, 3, 4, 5])

    def test_stream_getitem(self):
        s = stream(i for i in xrange(1))
        self.assertEqual(s[0], 0)

    def test_fastFlatMap_nominal(self):
        s = stream([[1, 2], [3, 4], [4, 5]])
        self.assertListEqual(s.fastFlatMap(poolSize=2).toList(), [1, 2, 3, 4, 4, 5])

    def test_fastFlatMap_random_sleep_function(self):
        s = stream([1, 2, 5, 3, 4])

        def random_sleep(i):
            time.sleep(random.randrange(0, 10) * 0.01)
            return range(i)

        self.assertListEqual(s.fastFlatMap(random_sleep, poolSize=2).sorted(),
                             [0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 3, 3, 4])

    def test_fastFlatMap_withPredicate(self):
        s = stream(({1: 2, 3: 4}, {5: 6, 7: 8}))
        self.assertEqual(s.fastFlatMap(dict.items).toSet(), set(((1, 2), (5, 6), (3, 4), (7, 8))))

    def test_fastFlatMap_defaultIdentityFunction(self):
        l = slist(({1: 2, 3: 4}, {5: 6, 7: 8}))
        self.assertEqual(l.fastFlatMap().toSet(), set((1, 3, 5, 7)))

    def test_fastmap_time(self):
        def sleepFunc(el):
            time.sleep(0.3)
            return el * el

        s = stream(xrange(100))
        t1 = time.time()
        res = s.fastmap(sleepFunc, poolSize=50).toSet()
        dt = time.time() - t1
        expected = set(i * i for i in xrange(100))
        self.assertSetEqual(res, expected)
        self.assertLessEqual(dt, 1.5)

    def test_fastmap_nominal(self):
        s = stream(xrange(100))
        res = s.fastmap(lambda x: x * x, poolSize=4).toSet()
        expected = set(i * i for i in xrange(100))
        self.assertSetEqual(res, expected)

    def test_fastmap_one_el(self):
        s = stream([1, ])
        res = s.fastmap(lambda x: x * x, poolSize=4).toSet()
        expected = set((1,))
        self.assertSetEqual(res, expected)

    def test_fastmap_no_el(self):
        s = stream([])
        res = s.fastmap(lambda x: x * x, poolSize=4).toSet()
        expected = set()
        self.assertSetEqual(res, expected)

    def test_fastmap_None_el(self):
        s = stream([None])
        res = s.fastmap(lambda x: x, poolSize=4).toSet()
        expected = set([None])
        self.assertSetEqual(res, expected)

    def test_fastmap_take_less(self):
        arr = []
        def m(i):
            arr.append(i)
            return i
        s = stream(range(100)).map(m).fastmap(lambda x: x, poolSize=4,bufferSize=5).take(20)
        res = s.toList()
        self.assertLessEqual(len(arr),30)
        self.assertEqual(len(res),20)

    def test_fastmap_raises_exception(self):
        s = stream([None])
        with self.assertRaises(TypeError):
            res = s.fastmap(lambda x: x * x, poolSize=4).toSet()

    def test_mpfastmap_time(self):
        N = 10
        s = stream(xrange(N))
        t1 = time.time()
        res = s.mpfastmap(PICKABLE_SLEEP_FUNC, poolSize=4).toSet()
        dt = time.time() - t1
        expected = set(i * i for i in xrange(N))
        self.assertSetEqual(res, expected)
        self.assertLessEqual(dt, 2)

    def test_mpfastmap_nominal(self):
        s = stream(xrange(10))
        f = partial(pow, 2)
        res = s.mpfastmap(f, poolSize=4).toSet()
        expected = set(f(i) for i in xrange(10))
        self.assertSetEqual(res, expected)

    def test_mpfastmap_one_el(self):
        s = stream([2, ])
        f = partial(pow, 2)
        res = s.mpfastmap(f, poolSize=4).toSet()
        expected = set((4,))
        self.assertSetEqual(res, expected)

    def test_mpfastmap_no_el(self):
        s = stream([])
        res = s.mpfastmap(lambda x: x * x, poolSize=4).toSet()
        expected = set()
        self.assertSetEqual(res, expected)

    def test_mpfastmap_None_el(self):
        s = stream([None])
        res = s.mpfastmap(PICKABLE_DUMB_FUNCTION, poolSize=4).toSet()
        expected = set([None])
        self.assertSetEqual(res, expected)

    # ToDo: fix the Pool.imap not true lazyness
    @unittest.skip("Pool.imap has bug. Workaround: https://stackoverflow.com/Questions/5318936/Python-Multiprocessing-Pool-Lazy-Iteration")
    def test_mpfastmap_take_less(self):
        arr = []

        def m(i):
            arr.append(i)
            return i

        s = stream(range(100)).map(m).mpfastmap(PICKABLE_DUMB_FUNCTION, poolSize=4, bufferSize=5).take(20)
        res = s.toList()
        self.assertLessEqual(len(arr), 30)
        self.assertEqual(len(res), 20)

    def test_mpfastmap_raises_exception(self):
        s = stream([None])
        f = partial(pow, 2)
        with self.assertRaises(TypeError):
            res = s.mpfastmap(f, poolSize=4).toSet()

    def test_mpmap_time(self):
        N = 10
        s = stream(xrange(N))
        t1 = time.time()
        res = s.mpmap(PICKABLE_SLEEP_FUNC, poolSize=4).toSet()
        dt = time.time() - t1
        expected = set(i * i for i in xrange(N))
        self.assertSetEqual(res, expected)
        self.assertLessEqual(dt, 2)

    def test_mpmap_nominal(self):
        s = stream(xrange(10))
        f = partial(pow, 2)
        res = s.mpmap(f, poolSize=4).toSet()
        expected = set(f(i) for i in xrange(10))
        self.assertSetEqual(res, expected)

    def test_mpmap_one_el(self):
        s = stream([2, ])
        f = partial(pow, 2)
        res = s.mpmap(f, poolSize=4).toSet()
        expected = set((4,))
        self.assertSetEqual(res, expected)

    def test_mpmap_no_el(self):
        s = stream([])
        res = s.mpmap(lambda x: x * x, poolSize=4).toSet()
        expected = set()
        self.assertSetEqual(res, expected)

    def test_mpmap_None_el(self):
        s = stream([None])
        res = s.mpmap(PICKABLE_DUMB_FUNCTION, poolSize=4).toSet()
        expected = set([None])
        self.assertSetEqual(res, expected)

    # ToDo: fix the Pool.imap not true lazyness
    @unittest.skip("Pool.imap has bug. Workaround: https://stackoverflow.com/Questions/5318936/Python-Multiprocessing-Pool-Lazy-Iteration")
    def test_mpmap_take_less(self):
        arr = []

        def m(i):
            arr.append(i)
            return i

        s = stream(range(100)).map(m).mpmap(PICKABLE_DUMB_FUNCTION, poolSize=4, bufferSize=5).take(20)
        res = s.toList()
        self.assertLessEqual(len(arr), 30)
        self.assertEqual(len(res), 20)

    def test_mpmap_raises_exception(self):
        s = stream([None])
        f = partial(pow, 2)
        with self.assertRaises(TypeError):
            res = s.mpmap(f, poolSize=4).toSet()

    def test_unique_nominal(self):
        s = stream([1, 2, 3, 1, 2])
        self.assertListEqual(s.unique().toList(), [1, 2, 3])

    def test_unique_mapping(self):
        s = stream(['abc', 'def', 'a', 'b', 'ab'])
        self.assertListEqual(s.unique(len).toList(), ['abc', 'a', 'ab'])

    def test_unique_empty_stream(self):
        s = stream([])
        self.assertListEqual(s.unique().toList(), [])

    def test_unique_generator_stream(self):
        s = stream(ItrFromFunc(lambda: xrange(4)))
        u = s.unique()
        self.assertListEqual(u.toList(), [0, 1, 2, 3])
        self.assertListEqual(u.toList(), [0, 1, 2, 3])

    def test_pstddev_nominal(self):
        s = stream([1, 2, 3, 4])
        self.assertAlmostEqual(s.pstddev(), 1.118033988749895)

    def test_pstddev_exception(self):
        with self.assertRaises(ValueError):
            stream([]).pstddev()

    def test_mean(self):
        self.assertAlmostEqual(stream([1, 2, 3, 4]).mean(), 2.5)

    def test_mean_exception(self):
        with self.assertRaises(ValueError):
            stream([]).mean()

    def test_toSumCounter_nominal(self):
        s = stream([('a', 2), ('a', 4), ('b', 2.1), ('b', 3), ('c', 2)])
        self.assertDictEqual(s.toSumCounter(), {'a': 6, 'b': 5.1, 'c': 2})

    def test_toSumCounter_onEmptyStream(self):
        s = stream([])
        self.assertDictEqual(s.toSumCounter(), {})

    def test_toSumCounter_onStrings(self):
        s = stream([('a', 'b'), ('a', 'c')])
        self.assertDictEqual(s.toSumCounter(), {'a': 'bc'})

    def test_keyBy_nominal(self):
        self.assertListEqual(stream(['a', 'bb', '']).keyBy(len).toList(), [(1, 'a'), (2, 'bb'), (0, '')])

    def test_keys_nominal(self):
        self.assertListEqual(stream([(1, 'a'), (2, 'bb'), (0, '')]).keystream().toList(), [1, 2, 0])

    def test_values_nominal(self):
        self.assertListEqual(stream([(1, 'a'), (2, 'bb'), (0, '')]).values().toList(), ['a', 'bb', ''])

    def test_toMap(self):
        self.assertDictEqual(stream(((1, 2), (3, 4))).toMap(), {1: 2, 3: 4})

    def test_joinWithString(self):
        s = "|"
        strings = ('a', 'b', 'c')
        self.assertEqual(stream(iter(strings)).join(s), s.join(strings))

    def test_joinWithNone(self):
        s = ""
        strings = ('a', 'b', 'c')
        self.assertEqual(stream(iter(strings)).join(), s.join(strings))

    def test_joinWithFunction(self):
        class F:
            def __init__(self):
                self.counter = 0

            def __call__(self, *args, **kwargs):
                self.counter += 1
                return str(self.counter)

        strings = ('a', 'b', 'c')
        f = F()
        self.assertEqual(stream(iter(strings)).join(f), "a1b2c")

    def test_mkString(self):
        streamToTest = stream(('a', 'b', 'c'))
        mock = MagicMock()
        joiner = ","
        streamToTest.join = mock
        streamToTest.mkString(joiner)
        mock.assert_called_once_with(joiner)

    def test_reversedNominal(self):
        s = stream([1, 2, 3])
        self.assertListEqual(s.reversed().toList(), [3, 2, 1])

    def test_reverse_iterable(self):
        s = stream(range(1, 4))
        self.assertListEqual(s.reversed().toList(), [3, 2, 1])

    def test_reversedException(self):
        s = stream(iter(range(1, 4)))
        with self.assertRaises(TypeError):
            s.reversed().toList()

    def test_len(self):
        # On iterable as init
        s = stream(range(1, 4))
        with self.assertRaises(TypeError):
            len(s)
        self.assertEqual(3, s.size())
        # On container as init
        s = stream([1, 2, 3])
        with self.assertRaises(TypeError):
            len(s)

    def test_tqdm_nominal(self):
        N = 4
        TM = r'(00:00|\?)'
        s = stream(range(N))
        out = io.StringIO()
        self.assertListEqual(list(range(N)), s.tqdm(file=out).toList())
        expected = rf'\r0it \[00:00, {TM}it/s\]' \
                   rf'\r{N}it \[00:00, {TM}it/s\]\n'
        self.assertRegex(out.getvalue(), expected)

    def test_tqdm_total(self):
        N = 4
        s = stream(range(N))
        FLT = r'(\d+\.\d+|\?)'
        TM = r'(00:00|\?)'
        out = io.StringIO()
        self.assertListEqual(list(range(N)), s.tqdm(total=N, file=out).toList())
        expected = rf'\r  0%\|          \| 0/{N} \[00:00<\?, \?it/s\]' \
                   rf'\r100%\|##########\| {N}/{N} \[00:00<{TM}, {FLT}it/s\]\n'
        a = rf'\r  0%|          | 0/4 [00:00<?, ?it/s]' \
            rf'\r100%|##########| 4/4 [00:00<00:00, 4011.77it/s]\n'
        self.assertRegex(out.getvalue(), expected)

    def test_tqdm_containers(self):
        N = 4
        FLT = r'(\d+\.\d+|\?)'
        TM = r'(00:00|\?)'
        s = stream(list(range(N)))
        out = io.StringIO()
        self.assertListEqual(list(range(N)), s.toList().tqdm(file=out).toList())
        expected = rf'\r  0%\|          \| 0/{N} \[00:00<\?, \?it/s\]' \
                   rf'\r100%\|##########\| {N}/{N} \[00:00<{TM}, {FLT}it/s\]\n'
        self.assertRegex(out.getvalue(), expected)

        out = io.StringIO()
        self.assertListEqual(list(range(N)), s.toSet().tqdm(file=out).toList())
        expected = rf'\r  0%\|          \| 0/{N} \[00:00<\?, \?it/s\]' \
                   rf'\r100%\|##########\| {N}/{N} \[00:00<{TM}, {FLT}it/s\]\n'
        self.assertRegex(out.getvalue(), expected)

        s = stream(((i, i + 1) for i in range(N))).toMap()
        self.assertListEqual([i for i in range(N)], s.tqdm(file=out).toList())
        expected = rf'\r  0%\|          \| 0/{N} \[00:00<\?, \?it/s\]' \
                   rf'\r100%\|##########\| {N}/{N} \[00:00<{TM}, {FLT}it/s\]\n'
        self.assertRegex(out.getvalue(), expected)

    def test_TqdmMapper_total(self):
        N = 4
        FLT = r'(\d+\.\d+|\?)'
        TM = r'(00:00|\?)'
        s = stream(range(N))
        out = io.StringIO()
        self.assertListEqual(list(range(N)), s.map(TqdmMapper(total=N, file=out)).toList())
        expected = rf'\r  0%\|          \| 0/{N} \[00:00<\?, \?it/s\]' \
                   rf'\r100%\|##########\| {N}/{N} \[00:00<{TM}, {FLT}it/s\]\n'
        self.assertRegex(out.getvalue(), expected)

    def test_TqdmMapper_nominal(self):
        N = 4
        TM = r'(00:00|\?)'
        s = stream(range(N))
        out = io.StringIO()
        self.assertListEqual(list(range(N)), s.map(TqdmMapper(file=out)).toList())
        expected = rf'\r0it \[00:00, {TM}it/s\]' \
                   rf'\r{N}it \[00:00, {TM}it/s\]\n'
        self.assertRegex(out.getvalue(), expected)


"""
Allow for these test cases to be run from the command line
"""
if __name__ == '__main__':
    all_tests = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    unittest.TextTestRunner(verbosity=2).run(all_tests)
