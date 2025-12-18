# Author: ASU --<andrei.suiu@gmail.com>
# Purpose: utility library for >=Python3.8
# pylint: disable=too-many-lines
import collections
import copy
import io
import itertools
import math
import numbers
import operator
import pickle
import struct
import sys
import threading
from abc import ABC, abstractmethod
from collections import abc, defaultdict
from functools import partial, reduce
from itertools import groupby
from multiprocessing import cpu_count
from multiprocessing.pool import Pool
from operator import itemgetter
from queue import Queue
from random import Random, shuffle
from types import GeneratorType
from typing import (
    AbstractSet,
    Any,
    BinaryIO,
    Callable,
    Dict,
    Generator,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableSet,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
    overload,
)

try:
    import gevent.pool as gpool
except ImportError:
    gpool = None

try:
    from pydantic_core.core_schema import any_schema as pydantic_any_schema
    from pydantic_core.core_schema import list_schema as pydantic_list_schema
    from pydantic_core.core_schema import (
        no_info_after_validator_function as pydantic_no_info_after_validator_function,
    )
except ImportError:

    def __func_raising(*args, **kwargs):
        raise ImportError("pydantic V2 is not installed")

    pydantic_list_schema = __func_raising
    pydantic_any_schema = __func_raising
    pydantic_no_info_after_validator_function = __func_raising

from tblib import pickling_support
from throttlex import Throttler
from tqdm import tqdm

__author__ = "andrei.suiu@gmail.com"

_K = TypeVar("_K")
_K2 = TypeVar("_K2")
_V = TypeVar("_V")
_V2 = TypeVar("_V2")
_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)


def _IDENTITY_FUNC(x: _T) -> _T:
    return x


class ItrFromFunc(Iterable[_K]):
    def __init__(self, f: Callable[[], Iterable[_K]], length_hint: Optional[int] = None):
        if callable(f):
            self._f = f
        else:
            raise TypeError(f"Argument f to {self.__class__!s} should be callable, but f.__class__={f.__class__!s}")
        self._length_hint = length_hint

    def __iter__(self) -> Iterator[_T_co]:
        return iter(self._f())

    def length_hint(self, default: Optional[int] = None) -> Optional[int]:
        """
        Returns the length hint for this iterable, or default if unknown.
        """
        return self._length_hint if self._length_hint is not None else default

    def __length_hint__(self) -> int:
        """
        Protocol method for length_hint. Raises TypeError if length is unknown.
        """
        if self._length_hint is None:
            raise TypeError("length is unknown")
        return self._length_hint


class _EndQueue:
    pass


class _MapException:
    def __init__(self, exc_info):
        self.exc_info = exc_info
        self.exc_type, self.exc_value, self.tb = exc_info

    def get_adjusted_exception(self) -> Exception:
        """
        Returns the exception instance from the stored exc_info.
        """
        return self.exc_value.with_traceback(self.tb)


class _QElement(NamedTuple):
    i: int
    el: Any


class TqdmMapper:
    def __init__(self, *args, **kwargs) -> None:
        """
        :param args: same args that are passed to tqdm
        :param kwargs: same args that are passed to tqdm
        """
        self._tqdm = tqdm(*args, **kwargs)

    def __call__(self, el: _K) -> _K:
        self._tqdm.update()
        return el


class _IStream(Iterable[_K], ABC):
    # pylint: disable=too-many-public-methods
    @staticmethod
    def _init_itr(itr: Optional[Union[Iterator[_K], Callable[[], Iterable[_K]]]] = None) -> Tuple[Optional[Iterable[_K]], Optional[Callable[[], Iterable[_K]]]]:
        _f = None
        if itr is None:
            _itr = []
        elif isinstance(itr, (abc.Iterable, abc.Iterator)) or hasattr(itr, "__iter__") or hasattr(itr, "__getitem__"):
            _itr = itr
        elif callable(itr):
            _f = itr
            _itr = None
        else:
            raise TypeError(f"Argument f to _IStream should be callable or iterable, but itr.__class__={itr.__class__!s}")
        return _itr, _f

    def length_hint(self, default: Optional[int] = None) -> Optional[int]:
        """Returns the length hint for this stream, or default if unknown."""
        try:
            return self.__length_hint__()
        except (TypeError, AttributeError):
            verified_default = default if default is not None else -1
            res = operator.length_hint(self, verified_default)
            if res != -1:
                return res
            return default

    @staticmethod
    def __fastmap_thread(f, qin, qout):
        while True:
            el = qin.get()
            if isinstance(el, _EndQueue):
                qin.put(el)
                return
            try:
                newEl = f(el)
                qout.put(newEl)
            except Exception:  # pylint: disable=broad-except
                qout.put(_MapException(sys.exc_info()))

    @staticmethod
    def __mtmap_thread(f, qin, qout):
        """
        :type qin:  Queue[Union[_QElement, _EndQueue]]
        :type qout: Queue[Union[_QElement, _MapException]]
        """
        while True:
            q_el = qin.get()

            if isinstance(q_el, _EndQueue):
                qin.put(q_el)
                return
            try:
                newEl = f(q_el.el)
                qout.put(_QElement(q_el.i, newEl))
            except Exception:  # pylint: disable=broad-except
                qout.put(_MapException(sys.exc_info()))

    @staticmethod
    def __fastFlatMap_thread(f, qin, qout):
        while True:
            itr = qin.get()
            if isinstance(itr, _EndQueue):
                qin.put(itr)
                qout.put(_EndQueue())
                return
            try:
                newItr = f(itr)
                for el in newItr:
                    qout.put(el)
            except Exception:  # pylint: disable=broad-except
                qout.put(_MapException(sys.exc_info()))

    def __fastmap_generator(self, f: Callable[[_K], _V], poolSize: int, bufferSize: int):
        # pylint: disable=too-many-branches
        qin = Queue(bufferSize)
        qout = Queue(max(bufferSize, poolSize + 1))  # max() is needed to not block when exiting

        threadPool = [threading.Thread(target=_IStream.__fastmap_thread, args=(f, qin, qout)) for _ in range(poolSize)]
        for t in threadPool:
            t.start()

        i = 0
        itr = iter(self)
        hasNext = True
        while i < bufferSize and hasNext:
            try:
                el = next(itr)
                i += 1
                qin.put(el)
            except StopIteration:
                hasNext = False

        try:
            while 1:
                try:
                    el = next(itr)
                except StopIteration:
                    qin.put(_EndQueue())
                    for t in threadPool:
                        t.join()
                    while not qout.empty():
                        newEl = qout.get()
                        if isinstance(newEl, _MapException):
                            # pylint: disable=raise-missing-from
                            raise newEl.get_adjusted_exception()

                        yield newEl
                    break
                else:
                    qin.put(el)
                    newEl = qout.get()
                    if isinstance(newEl, _MapException):
                        raise newEl.get_adjusted_exception()
                    yield newEl
        finally:
            while not qin.empty():
                qin.get()
            qin.put(_EndQueue())
            while not qout.empty() or not qout.empty():
                qout.get()
            for t in threadPool:
                t.join()

    def __mtmap_generator(self, f: Callable[[_K], _V], poolSize: int, bufferSize: int):
        # pylint: disable=too-many-branches, too-many-statements
        qin = Queue(bufferSize)
        qout = Queue(max(bufferSize, poolSize + 1))  # max() is needed to not block when exiting

        threadPool = [threading.Thread(target=_IStream.__mtmap_thread, args=(f, qin, qout)) for _ in range(poolSize)]
        for t in threadPool:
            t.start()

        in_i = 0
        itr = iter(self)
        hasNext = True
        while in_i < bufferSize and hasNext:
            try:
                el = next(itr)
            except StopIteration:
                hasNext = False
            else:
                in_i += 1
                qin.put(_QElement(in_i, el))
        cache = {}
        out_i = 1

        def extract_all_from_cache():
            nonlocal out_i
            nonlocal in_i
            nonlocal cache
            while out_i in cache:
                yield cache[out_i]
                out_i += 1

        def wait_for_all():
            nonlocal out_i
            nonlocal in_i
            nonlocal cache
            while not qout.empty():
                q_el = qout.get()
                if isinstance(q_el, _MapException):
                    raise q_el.get_adjusted_exception()
                cache[q_el.i] = q_el.el
            yield from extract_all_from_cache()
            if out_i != in_i + 1:
                raise RuntimeError("__mtmap_generator Expecting for all elements to be in cache")

        try:
            while 1:
                try:
                    el = next(itr)
                except StopIteration:
                    qin.put(_EndQueue())
                    for t in threadPool:
                        t.join()
                    yield from wait_for_all()
                    break
                else:
                    in_i += 1
                    qin.put(_QElement(in_i, el))
                    q_el = qout.get()
                    if isinstance(q_el, _MapException):
                        raise q_el.get_adjusted_exception()
                    cache[q_el.i] = q_el.el
                yield from extract_all_from_cache()
        finally:
            while not qin.empty():
                qin.get()
            qin.put(_EndQueue())
            while not qout.empty() or not qout.empty():
                qout.get()
            for t in threadPool:
                t.join()

    @staticmethod
    def __fastFlatMap_input_thread(itr: Iterator[_K], qin: Queue):
        while 1:
            try:
                el = next(itr)
            except StopIteration:
                qin.put(_EndQueue())
                return
            qin.put(el)

    def __fastFlatMap_generator(self, predicate, poolSize: int, bufferSize: int):
        qin = Queue(bufferSize)
        qout = Queue(bufferSize * 2)
        threadPool = [threading.Thread(target=_IStream.__fastFlatMap_thread, args=(predicate, qin, qout)) for i in range(poolSize)]
        for t in threadPool:
            t.start()
        i = 0
        itr = iter(self)
        hasNext = True
        while i < bufferSize and hasNext:
            try:
                el = next(itr)
                i += 1
                qin.put(el)
            except StopIteration:
                hasNext = False
        inputThread = threading.Thread(target=_IStream.__fastFlatMap_input_thread, args=(itr, qin))
        inputThread.start()

        qout_counter = 0
        while qout_counter < len(threadPool):
            newEl = qout.get()
            if isinstance(newEl, _MapException):
                raise newEl.get_adjusted_exception()
            if isinstance(newEl, _EndQueue):
                qout_counter += 1
                if qout_counter >= len(threadPool):
                    inputThread.join()
                    for t in threadPool:
                        t.join()
                    while not qout.empty():
                        newEl = qout.get()
                        if isinstance(newEl, _MapException):
                            raise newEl.get_adjusted_exception()
                        yield newEl
            else:
                yield newEl

    @staticmethod
    def exc_info_decorator(f: Callable[[_K], _V], el: _K) -> Union[_MapException, _V]:
        """This decorates f to pass the exception traceback properly"""
        try:
            return f(el)
        except Exception as e:  # pylint: disable=broad-except,broad-exception-caught
            pickling_support.install(e)
            return _MapException(sys.exc_info())

    def _mp_pool_generator(self, f: Callable[[_K], _V], poolSize: int, bufferSize: int) -> Generator[_V, None, None]:
        p = Pool(poolSize)
        decorated_f_with_exc_passing = partial(self.exc_info_decorator, f)
        for el in p.imap(decorated_f_with_exc_passing, self, chunksize=bufferSize):
            if isinstance(el, _MapException):
                raise el.get_adjusted_exception()
            yield el
        p.close()
        p.join()

    def __gt_pool_generator(self, f: Callable[[_K], _V], poolSize: int) -> Generator[_V, None, None]:
        if not gpool:
            raise ImportError("gevent is not installed")
        p = gpool.Pool(size=poolSize)
        decorated_f_with_exc_passing = partial(self.exc_info_decorator, f)
        for el in p.imap(decorated_f_with_exc_passing, self):
            if isinstance(el, _MapException):
                raise el.get_adjusted_exception()
            yield el
        p.join()

    def __gt_fast_pool_generator(self, f: Callable[[_K], _V], poolSize: int) -> Generator[_V, None, None]:
        if not gpool:
            raise ImportError("gevent is not installed")
        p = gpool.Pool(size=poolSize)
        decorated_f_with_exc_passing = partial(self.exc_info_decorator, f)
        for el in p.imap_unordered(decorated_f_with_exc_passing, self):
            if isinstance(el, _MapException):
                raise el.get_adjusted_exception()
            yield el
        p.join()

    def _mp_fast_pool_generator(self, f: Callable[[_K], _V], poolSize: int, bufferSize: int) -> Generator[_V, None, None]:
        p = Pool(poolSize)
        try:
            decorated_f_with_exc_passing = partial(self.exc_info_decorator, f)
            for el in p.imap_unordered(decorated_f_with_exc_passing, iter(self), chunksize=bufferSize):
                if isinstance(el, _MapException):
                    raise el.get_adjusted_exception()
                yield el
        except GeneratorExit:
            p.terminate()
        finally:
            p.close()
            p.join()

    @staticmethod
    def __unique_generator(itr, f: Optional[Callable[[_K], _V]]):
        st = set()
        if f is None:
            for el in itr:
                if el not in st:
                    st.add(el)
                    yield el
        else:
            for el in itr:
                m_el = f(el)
                if m_el not in st:
                    st.add(m_el)
                    yield el

    def __add_observer_generator(self, observer: Callable[[_K], None]) -> Iterator[_K]:
        for el in self:
            observer(el)
            yield el

    def map(self: "stream[_K]", f: Callable[[_K], _V]) -> "stream[_V]":
        return stream(partial(map, f, self), source=self)

    def starmap(self: "stream[_K]", f: Callable[[_K], _V]) -> "stream[_V]":
        return stream(partial(itertools.starmap, f, self), source=self)

    def mpmap(self: "stream[_K]", f: Callable[[_K], _V], poolSize: int = cpu_count(), bufferSize: Optional[int] = 1) -> "stream[_V]":
        """
        Parallel ordered map using multiprocessing.Pool.imap
        :param poolSize: number of processes in Pool
        :param bufferSize: passed as chunksize param to imap()
        """
        # Validations
        if not isinstance(poolSize, int) or poolSize <= 0 or poolSize > 2**12:
            raise ValueError(f"poolSize should be an integer between 1 and 2^12. Received: {poolSize}")
        if poolSize == 1:
            return self.map(f)
        if bufferSize is None:
            bufferSize = poolSize * 2
        if not isinstance(bufferSize, int) or bufferSize <= 0 or bufferSize > 2**12:
            raise ValueError(f"bufferSize should be an integer between 1 and 2^12. Received: {poolSize!s}")

        return stream(self._mp_pool_generator(f, poolSize, bufferSize), source=self)

    def mpstarmap(self, f: Callable[[_K], _V], poolSize: Union[int, Pool] = cpu_count(), bufferSize: Optional[int] = 1) -> "stream[_V]":
        """
        Parallel unordered map using multiprocessing.Pool.imap_unordered
        :param f: function to apply
        :param poolSize: number of processes in Pool
        :param bufferSize: passed as chunksize param to imap_unordered(), so it default to 1 as imap_unordered
        """
        return self.mpmap(partial(self._star_mapper, f), poolSize, bufferSize)

    def mpfastmap(self: "stream[_K]", f: Callable[[_K], _V], poolSize: Union[int, Pool] = cpu_count(), bufferSize: Optional[int] = 1) -> "stream[_V]":
        """
        Parallel unordered map using multiprocessing.Pool.imap_unordered
        :param poolSize: number of processes in Pool
        :param bufferSize: passed as chunksize param to imap_unordered(), so it default to 1 as imap_unordered
        """
        # Validations
        if not isinstance(poolSize, int) or poolSize <= 0 or poolSize > 2**12:
            raise ValueError(f"poolSize should be an integer between 1 and 2^12. Received: {poolSize!s}")
        if poolSize == 1:
            return self.map(f)
        if bufferSize is None:
            bufferSize = poolSize * 2
        if not isinstance(bufferSize, int) or bufferSize <= 0 or bufferSize > 2**12:
            raise ValueError(f"bufferSize should be an integer between 1 and 2^12. Received: {poolSize!s}")

        return stream(self._mp_fast_pool_generator(f, poolSize, bufferSize), source=self)

    @staticmethod
    def _star_mapper(f, el):
        return f(*el)

    def mpfaststarmap(self, f: Callable[[_K], _V], poolSize: Union[int, Pool] = cpu_count(), bufferSize: Optional[int] = 1) -> "stream[_V]":
        """
        Parallel unordered map using multiprocessing.Pool.imap_unordered
        :param poolSize: number of processes in Pool
        :param bufferSize: passed as chunksize param to imap_unordered(), so it default to 1 as imap_unordered
        """
        return self.mpfastmap(partial(_IStream._star_mapper, f), poolSize, bufferSize)

    def fastmap(self, f: Callable[[_K], _V], poolSize: int = cpu_count(), bufferSize: Optional[int] = None) -> "stream[_V]":
        """
        Parallel unordered map using multithreaded pool.
        It spawns at most poolSize threads and applies the f function.
        The elements in the result stream appears in the unpredicted order.
        It's most usefull for I/O or CPU intensive consuming functions.
        :param poolSize: number of threads to spawn
        """
        if not isinstance(poolSize, int) or poolSize <= 0 or poolSize > 2**12:
            raise ValueError(f"poolSize should be an integer between 1 and 2^12. Received: {poolSize!s}")
        if poolSize == 1:
            return self.map(f)
        if bufferSize is None:
            bufferSize = poolSize
        if not isinstance(bufferSize, int) or bufferSize <= 0 or bufferSize > 2**12:
            raise ValueError(f"bufferSize should be an integer between 1 and 2^12. Received: {poolSize!s}")

        return stream(ItrFromFunc(lambda: self.__fastmap_generator(f, poolSize, bufferSize), length_hint=self.length_hint()))

    def faststarmap(self, f: Callable[[_K], _V], poolSize: int = cpu_count(), bufferSize: Optional[int] = None) -> "stream[_V]":
        """
        Parallel unordered starmap using multithreaded pool.
        It spawns at most poolSize threads and applies the f function.
        The elements in the result stream appears in the unpredicted order.
        It's most usefull for I/O or CPU intensive consuming functions.
        :param poolSize: number of threads to spawn
        """
        return self.fastmap(lambda el: f(*el), poolSize, bufferSize)

    def mtmap(self, f: Callable[[_K], _V], poolSize: int = cpu_count(), bufferSize: Optional[int] = None) -> "stream[_V]":
        """
        Parallel ORDERED map using multithreaded pool.
        It spawns at most poolSize threads and applies the f function.
        The elements in the result stream appears in the same order as at input.
        It's most usefull for I/O or CPU intensive consuming functions.
        :param poolSize: number of threads to spawn
        """
        if not isinstance(poolSize, int) or poolSize <= 0 or poolSize > 2**12:
            raise ValueError(f"poolSize should be an integer between 1 and 2^12. Received: {poolSize!s}")
        if poolSize == 1:
            return self.map(f)
        if bufferSize is None:
            bufferSize = poolSize
        if not isinstance(bufferSize, int) or bufferSize <= 0 or bufferSize > 2**12:
            raise ValueError(f"bufferSize should be an integer between 1 and 2^12. Received: {poolSize!s}")

        return stream(ItrFromFunc(lambda: self.__mtmap_generator(f, poolSize, bufferSize), length_hint=self.length_hint()))

    def gtmap(self, f: Callable[[_K], _V], poolSize: int = cpu_count()) -> "stream[_V]":
        """
        Applies a given function to each item in the stream in parallel using Green Threads, provided by the gevent library.
        This method offers a way to parallelize operations without the overhead of traditional threading or multiprocessing,
            making it efficient for I/O-bound tasks.
        The output order is guaranteed to be the same as the input order.

        :param poolSize: number of greenlets in Pool
        """
        if not isinstance(poolSize, int) or poolSize <= 0 or poolSize > 2**12:
            raise ValueError(f"poolSize should be an integer between 1 and 2^12. Received: {poolSize!s}")
        if poolSize == 1:
            return self.map(f)

        return stream(ItrFromFunc(lambda: self.__gt_pool_generator(f, poolSize), length_hint=self.length_hint()))

    def gtfastmap(self, f: Callable[[_K], _V], poolSize: int = cpu_count()) -> "stream[_V]":
        """
        Applies a given function to each item in the stream in parallel using Green Threads, provided by the gevent library.
        This method offers a way to parallelize operations without the overhead of traditional threading or multiprocessing,
            making it efficient for I/O-bound tasks.
        The output order is NOT guaranteed to be the same as the input order, which makes it faster than gtmap.

        :param poolSize: number of greenlets in Pool
        """
        if not isinstance(poolSize, int) or poolSize <= 0 or poolSize > 2**12:
            raise ValueError(f"poolSize should be an integer between 1 and 2^12. Received: {poolSize!s}")
        if poolSize == 1:
            return self.map(f)

        return stream(ItrFromFunc(lambda: self.__gt_fast_pool_generator(f, poolSize), length_hint=self.length_hint()))

    def mtstarmap(self, f: Callable[[_K], _V], poolSize: int = cpu_count(), bufferSize: Optional[int] = None) -> "stream[_V]":
        """
        Parallel ORDERED map using multithreaded pool.
        It spawns at most poolSize threads and applies the f function.
        The elements in the result stream appears in the same order as at input.
        It's most usefull for I/O or CPU intensive consuming functions.
        :param poolSize: number of threads to spawn
        """
        return self.mtmap(lambda el: f(*el), poolSize, bufferSize)

    def gtstarmap(self, f: Callable[[_K], _V], poolSize: int = cpu_count()) -> "stream[_V]":
        """
        Parallel ORDERED map using eventlet.Pool with Green threads.
        It spawns at most poolSize green threads and applies the f function.
        The elements in the result stream appears in the same order as at input.
        It's usefull only for I/O intensive consuming functions (and please not that it has to use eventlet.sleep in order to benefit from green threads).
        :param poolSize: number of threads to spawn
        """
        return self.gtmap(lambda el: f(*el), poolSize)

    def fastFlatMap(
        self, predicate: Callable[[_K], Iterable[_V]] = _IDENTITY_FUNC, poolSize: int = cpu_count(), bufferSize: Optional[int] = None
    ) -> "stream[_V]":
        if not isinstance(poolSize, int) or poolSize <= 0 or poolSize > 2**12:
            raise ValueError(f"poolSize should be an integer between 1 and 2^12. Received: {poolSize!s}")
        if poolSize == 1:
            return self.flatMap(predicate)
        if bufferSize is None:
            bufferSize = poolSize
        if not isinstance(bufferSize, int) or bufferSize <= 0 or bufferSize > 2**12:
            raise ValueError(f"bufferSize should be an integer between 1 and 2^12. Received: {poolSize!s}")
        return stream(lambda: self.__fastFlatMap_generator(predicate, poolSize, bufferSize))

    def into(self: "stream[_K]", f: Callable[["stream[_K]"], _T]) -> _T:
        return f(self)

    def via(self: "stream[_K]", func: Callable[["stream[_K]"], Iterator[_V]]) -> "stream[_V]":
        return stream(partial(func, self))

    def enumerate(self: "stream[_K]") -> "stream[Tuple[int,_K]]":
        return stream(zip(range(0, sys.maxsize), self), source=self)

    def flatMap(self, predicate: Callable[[_K], Iterable[_V]] = _IDENTITY_FUNC) -> "stream[_V]":
        """
        :param predicate: predicate is a function that will receive elements of self collection and return an iterable
            By default predicate is an identity function
        :return: will return stream of objects of the same type of elements from the stream returned by predicate()
        """
        if id(predicate) == id(_IDENTITY_FUNC):
            return stream(ItrFromFunc(lambda: itertools.chain.from_iterable(self)))
        return stream(ItrFromFunc(lambda: itertools.chain.from_iterable(self.map(predicate))))

    def pairWith(self: "stream[_K]", f: Callable[[_K], _V]) -> "stream[Tuple[_K, _V]]":
        """Apply a unary function to a stream of values x and produce a
        stream of tuples (x, f(x)). Useful for chaining with `.toMap()`.
        """
        return self.map(lambda x: (x, f(x)))

    def pairBy(self: "stream[_V]", f: Callable[[_V], _K]) -> "stream[Tuple[_K, _V]]":
        """As makeMapping, but returns a tuple of (f(x), x). Useful
        when building a dict where it's the f(x)'s that are hashable,
        not the x's.
        """
        return self.map(lambda x: (f(x), x))

    def mapKeys(self: "stream[Tuple[_K, _V]]", f: Callable[[_K], _K2]) -> "stream[Tuple[_K2, _V]]":
        """Apply a unary function to the first elements of a stream of
        binary tuples. Useful when applying a tranformation to a stream
        but you want to keep the original values for a later
        transformation or filter, e.g. if you want to transform the keys
        of a dict but not the values.
        """
        return self.map(lambda kv: (f(kv[0]), kv[1]))

    def mapValues(self: "stream[Tuple[_K, _V]]", f: Callable[[_V], _V2]) -> "stream[Tuple[_K, _V2]]":
        """As mapKeys but to the second element of each tuple."""
        return self.map(lambda kv: (kv[0], f(kv[1])))

    def filterKeys(self: "stream[Tuple[_K, _V]]", predicate: Callable[[_K], bool]) -> "stream[Tuple[_K, _V]]":
        """Filter a stream of binary tuples according to a predicate on
        the first element.
        """
        return self.filter(lambda kv: predicate(kv[0]))

    def filterValues(self: "stream[Tuple[_K, _V]]", predicate: Callable[[_V], bool]) -> "stream[Tuple[_K, _V]]":
        """Filter a stream of binary tuples according to a predicate on
        the second element.
        """
        return self.filter(lambda kv: predicate(kv[1]))

    def for_each(self, f: Callable[[_K], None]) -> None:
        for el in self:
            f(el)

    def tap(self, f: Callable[[_K], Any]) -> "stream[_K]":
        """Apply a unary function to each element of this stream, but
        discard any return value and just return the original stream.
        Useful for functions with side effects, like logging.

        Example:

            >>> stream(...).tap(print).map(...).tap(print).toList()

        will print the stream twice, before and after the map.

        Use a `functools.partial`  to pass additional keyword arguments:

            >>> stream(...).tap(partial(print, sep=' ')).map(...).toList()
        """

        def tap_f(x):
            f(x)
            return x

        return self.map(tap_f)

    def add_observer(self, f: Callable[[_K], None]) -> "stream[_K]":
        """
        :param f: f is observer that will receive elements of self collection and return None
        :return: will return stream of objects of the same type of elements from the stream
        """
        return stream(ItrFromFunc(lambda: self.__add_observer_generator(f), length_hint=self.length_hint()))

    def filter(self, predicate: Optional[Callable[[_K], bool]] = None) -> "stream[_K]":
        """
        :param predicate: If predicate is None, return the items that are true.
        """
        return stream(ItrFromFunc(lambda: filter(predicate, self)))

    def starfilter(self, predicate: Callable[[_K], bool]) -> "stream[_K]":
        """
        :param predicate:  Applies predicate unpacks the current item when calling predicate function.
            If predicate is None, returns the items that are true,
        :return: stream over iterable containing only the items where pred(*item) is True.
        """
        return self.filter(lambda el: predicate(*el))

    def reversed(self: "stream[_K]") -> "stream[_K]":
        try:
            return reversed(self)  # pylint: disable=bad-reversed-sequence
        except AttributeError:
            return stream(lambda: reversed(self.toList()))

    def exists(self, f: Callable[[_K], bool]) -> bool:
        """
        Tests whether a predicate holds for some of the elements of this sequence.
        """
        for e in self:
            if f(e):
                return True
        return False

    def keyBy(self, keyfunc: Callable[[_K], _V] = _IDENTITY_FUNC) -> "stream[Tuple[_K, _V]]":
        """
        :param keyfunc: function to map values to keys
        :return: stream of Key, Value pairs
        """
        return self.map(lambda h: (keyfunc(h), h))

    def keystream(self: "stream[Tuple[_T,_V]]") -> "stream[_T]":
        """
        Applies only on streams of 2-uples
        :return: stream consisted of first element of tuples
        """
        return self.map(itemgetter(0))

    def values(self: "stream[Tuple[_T,_V]]") -> "stream[_V]":
        """
        Applies only on streams of 2-uples
        :return: stream consisted of second element of tuples
        """
        return self.map(itemgetter(1))

    def groupBy(self, keyfunc: Callable[[_K], _T] = _IDENTITY_FUNC) -> "slist[Tuple[_T, slist[_K]]]":
        """
        groupBy([keyfunc]) -> Make a slist with consecutive keys and groups from the iterable.
        The iterable needs not to be sorted on the same key function, but the keyfunction need to return hashable objects.
        :param keyfunc: [Optional] The key is a function computing a key value for each element.
        :return: (key, sub-iterator) grouped by each value of key(value).
        """
        h = defaultdict(slist)
        for v in self:
            h[keyfunc(v)].append(v)
        return slist(h.items())

    @staticmethod
    def __order_key_func(order_fn: Callable[[_K], _T], x: Tuple[int, _K]):
        return x[0] - order_fn(x[1])

    @classmethod
    def __group_consecutive_generator(cls, itr, order_fn: Callable[[_K], _T] = lambda x: x) -> "Generator[Tuple[_T, stream[_K]],None,None]":
        """
        Produce groups of consecutive elements using itertools.groupby.
        The function order_fn defines the consecutive logic by assigning a position to each element.
        By default, order_fn is an identity function which works for consecutive numbers:

        >>> numbers = stream([1, 10, 11, 12, 20, 30, 31, 32, 33, 40])
        >>> for grp in numbers.group_consecutive():
        ...     print(list(grp))
        [1]
        [10, 11, 12]
        [20]
        [30, 31, 32, 33]
        [40]

        To identify consecutive letters, use the index method from a string:

        >>> from string import ascii_lowercase
        >>> letters = stream('abcdfgilmnop')
        >>> order_fn = ascii_lowercase.index
        >>> for grp in letters.group_consecutive(order_fn):
        ...     print(list(grp))
        ['a', 'b', 'c', 'd']
        ['f', 'g']
        ['i']
        ['l', 'm', 'n', 'o', 'p']

        Note: Each group shares its source with the main iterable. To retain groups,
        ensure to copy its elements, like storing in a list.

        >>> numbers = stream([1, 2, 11, 12, 21, 22])
        >>> stored_grps = [list(grp) for grp in numbers.group_consecutive()]
        >>> stored_grps
        [[1, 2], [11, 12], [21, 22]]

        """

        # key_fn = lambda x: x[0] - order_fn(x[1])
        key_fn = partial(cls.__order_key_func, order_fn)
        for _, group in groupby(enumerate(itr), key=key_fn):
            yield stream(group).map(itemgetter(1))

    def group_consecutive(self, order_fn: Callable[[_K], _T] = lambda x: x) -> "stream[Tuple[_T, stream[_K]]]":
        return stream(self.__group_consecutive_generator(self, order_fn))

    @staticmethod
    def __stream_on_second_el(t: Tuple[_K, Iterable[_T]]) -> "Tuple[_K, stream[_T]]":
        return t[0], stream(t[1])

    @staticmethod
    def __slist_on_second_el(t: Tuple[_K, Iterable[_T]]) -> "Tuple[_K, slist[_T]]":
        return t[0], slist(t[1])

    def groupBySorted(self, keyfunc: Optional[Callable[[_K], _T]] = None) -> "stream[Tuple[_T, stream[_K]]]":
        """
        Make a stream of consecutive keys and groups (as streams) from the self.
        The iterable needs to already be sorted on the same key function.
        :param keyfunc: a function computing a key value for each element. Defaults to an identity function and returns the element unchanged.
        :return: (key, sub-iterator) grouped by each value of key(value).
        """
        return stream(partial(groupby, iterable=self, key=keyfunc)).map(self.__stream_on_second_el)

    def groupBySortedToList(self, keyfunc: Callable[[_K], _T] = _IDENTITY_FUNC) -> "stream[Tuple[_T, slist[_K]]]":
        """
        Make a stream of consecutive keys and groups (as streams) from the self.
        The iterable needs to already be sorted on the same key function.
        :param keyfunc: a function computing a key value for each element. Defaults to an identity function and returns the element unchanged.
        :return: (key, sub-iterator) grouped by each value of key(value).
        """
        return stream(partial(groupby, iterable=self, key=keyfunc)).map(self.__slist_on_second_el)

    def countByValue(self) -> "sdict[_K,int]":
        return sdict(collections.Counter(self))

    @overload
    def reduce(self, f: Callable[[_K, _K], _K], init: Optional[_K] = None) -> _K: ...

    @overload
    def reduce(self, f: Callable[[_T, _K], _T], init: _T = None) -> _T: ...

    @overload
    def reduce(self, f: Callable[[Union[_K, _T], _K], _T], init: Optional[_T] = None) -> _T: ...

    @overload
    def reduce(self, f: Callable[[Union[_K, _T], _K], _T], init: Optional[_K] = None) -> _T: ...

    @overload
    def reduce(self, f: Callable[[_T, _K], _T], init: _T = None) -> _T: ...

    def reduce(self, f, init=None):
        if init is None:
            return reduce(f, self)
        return reduce(f, self, init)

    def transform(self, f: Callable[[Iterable[_K]], Iterable[_V]]) -> "stream[_V]":
        return stream(partial(f, self))

    def shuffle(self, seed: Optional[Union[int, float, str, bytes, bytearray]] = None) -> "slist[_K]":
        lst = self.toList()
        if seed is not None:
            rng = Random(seed)
            rng.shuffle(lst)
        else:
            shuffle(lst)
        return lst

    def toSet(self) -> "sset[_K]":
        return sset(self)

    def toList(self) -> "slist[_K]":
        return slist(self)

    def sorted(self, key=None, reverse=False):
        return slist(sorted(self, key=key, reverse=reverse))

    def toMap(self: "stream[Tuple[_T,_V]]") -> "sdict[_T,_V]":
        return sdict(self)

    to_list = toList
    to_set = toSet
    to_map = toMap
    to_dict = toMap

    def toSumCounter(self: "stream[Tuple[_T,_V]]") -> "sdict[_T,_V]":
        """
        Elements should be tuples (T, V) where V can be summed
        :return: sdict on stream elements
        :rtype: sdict[ T, V ]
        """
        res = sdict()
        for k, v in self:
            if k in res:
                res[k] += v
            else:
                res[k] = v
        return res

    def toDataFrame(self: "stream[Dict[str, _V]]", *args, **kwargs) -> "pd.DataFrame":
        """Convert a stream of records into a Pandas dataframe."""
        try:
            import pandas as pd
        except ImportError as e:
            raise RuntimeError("pandas is not available") from e

        return pd.DataFrame.from_records(self.toList(), *args, **kwargs)

    @overload
    def __getitem__(self, i: slice) -> "stream[_K]": ...

    @overload
    def __getitem__(self, i: int) -> _K: ...

    def __getitem__(self, i: Union[slice, int]):
        if isinstance(i, slice):
            return self.__getslice(i.start, i.stop, i.step)
        tk = 0
        while tk < i:
            self.next()
            tk += 1
        return self.next()

    def __getslice(self, start: Optional[int] = None, stop: Optional[int] = None, step: Optional[int] = None) -> "stream[_K]":
        # ToDo:fix this for cases where self._itr is generator from fastmap(), so have to be closed()
        return stream(lambda: itertools.islice(self, start, stop, step))

    def __add__(self, other) -> "stream[_K]":
        if not isinstance(other, (ItrFromFunc, stream)):
            othItr = stream(lambda: other)
            other_len = operator.length_hint(other, -1)
            if other_len == -1:
                other_len = None
        else:
            othItr = other
            other_len = other.length_hint()
        if isinstance(self._itr, (ItrFromFunc, stream)):
            i = self._itr
        elif self._itr is None:
            i = ItrFromFunc(self._f)
        else:
            i = ItrFromFunc(lambda: self._itr)

        # Compute combined length hint
        self_hint = self.length_hint()
        combined_hint = None
        if self_hint is not None and other_len is not None:
            combined_hint = self_hint + other_len

        return stream(partial(itertools.chain.from_iterable, (i, othItr)), length_hint=combined_hint)

    def __iadd__(self: "stream[_K]", other) -> "stream[_K]":
        if not isinstance(other, (ItrFromFunc, stream)):
            othItr = stream(lambda: other)
        else:
            othItr = other
        if isinstance(self._itr, ItrFromFunc):
            i = self._itr
        elif self._itr is None:
            i = ItrFromFunc(self._f)
        else:
            j = self._itr
            i = ItrFromFunc(lambda: j)
        self._itr, self._f = self._init_itr(partial(itertools.chain.from_iterable, (i, othItr)))
        return self

    def size(self: "stream[_K]") -> int:
        try:
            return len(self)
        except TypeError:
            pass
        return sum(1 for _ in iter(self))

    def join(self, f: Callable[[_K], _V] = None) -> Union[_K, str]:
        if f is None:
            return "".join(self)
        if isinstance(f, str):
            return f.join(self)
        itr = iter(self)
        r = next(itr)
        last = r
        while True:
            try:
                n = next(itr)
                r += f(last)
                last = n
                r += n
            except StopIteration:
                break
        return r

    def mkString(self, c) -> str:
        return self.join(c)

    def batch(self, size: int) -> "stream[slist[_K]]":
        """
        :param size: size of batch
        It groups elements of stream into batches of size `size` and returns stream of batches which are slists

        >>> stream(range(10)).batch(3).toList()
        [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]
        """

        def batch_gen(itr):
            while True:
                batch = slist(itertools.islice(itr, 0, size))
                if not batch:
                    break
                yield batch

        return stream(lambda: stream(batch_gen(iter(self))))

    def take(self, n: int) -> "stream[_K]":
        """Return a stream that consists of the first n elements of this
        stream. This stream itself is not mutated.
        """

        def gen(other_gen: GeneratorType, n):
            count = 0
            while count < n:
                if count < n:
                    try:
                        el = next(other_gen)
                        count += 1
                        yield el
                    except StopIteration:
                        break
            other_gen.close()

        # Compute new length hint
        original_hint = self.length_hint()
        new_hint = min(n, original_hint) if original_hint is not None else None

        if isinstance(self._itr, GeneratorType):
            return stream(gen(self._itr, n), length_hint=new_hint)
        return stream(self[:n], length_hint=new_hint)

    def takeWhile(self, predicate: Callable[[_K], bool]) -> "stream[_K]":
        def gen(other_gen: Union[GeneratorType, Iterable[_K]], pred: Callable[[_K], bool]):
            isGen = True
            if not isinstance(other_gen, GeneratorType):
                isGen = False
                other_gen = iter(other_gen)
            while True:
                try:
                    el = next(other_gen)
                    if pred(el):
                        yield el
                    else:
                        break
                except StopIteration:
                    break
            if isGen:
                other_gen.close()

        return stream(gen(self, predicate))

    def drop(self, n: int):
        """Return a stream that doesn't have the first n elements of
        this stream. If there aren't enough elements then the new stream
        is empty. This stream itself is not mutated.
        """
        # Compute new length hint
        original_hint = self.length_hint()
        new_hint = max(0, original_hint - n) if original_hint is not None else None

        s = stream(self, length_hint=new_hint)

        for _ in range(n):
            try:
                s.next()
            except StopIteration:
                break

        return s

    def dropWhile(self, predicate: Callable[[_K], bool]):
        return stream(partial(itertools.dropwhile, predicate, self))

    def next(self: "stream[_K]") -> _K:
        """Remove the next element from this stream, and return it.
        Raise StopIteration if there are no more elements.
        """
        if self._itr is not None:
            try:
                n = next(self._itr)
                return n
            except TypeError:
                self._itr = iter(self._itr)
                return next(self._itr)
        else:
            self._itr = iter(self)
            self._f = None
            return next(self._itr)

    def head(self, n: int) -> "stream[_K]":
        "Return a stream over the first n items"
        return stream(itertools.islice(self, n))

    def tail(self, n: int):
        "Return a steam over the last n items"
        return stream(collections.deque(self, maxlen=n))

    def all_equal(self) -> bool:
        "Returns True if all the elements are equal to each other"
        g = groupby(self)
        return next(g, True) and not next(g, False)

    def quantify(self, predicate: Callable[[_K], bool]) -> int:
        "Count how many times the predicate is true"
        return sum(self.map(predicate))

    def pad_with(self, pad: Any) -> "stream[Union[Any,_K]]":
        """Returns the sequence elements and then returns pad indefinitely.

        Useful for emulating the behavior of the built-in map() function.
        """
        return stream(itertools.chain(self, itertools.repeat(pad)))

    def roundrobin(self: "stream[_K]") -> "stream":
        """
        roundrobin('ABC', 'D', 'EF') --> A D E B F C
        Recipe credited to https://docs.python.org/3/library/itertools.html#itertools.chain.from_iterable
        """

        def gen(s: "stream"):
            num_active = s.size()
            nexts = itertools.cycle(iter(it).__next__ for it in s)
            while num_active:
                try:
                    for _next in nexts:
                        yield _next()
                except StopIteration:
                    # Remove the iterator we just exhausted from the cycle.
                    num_active -= 1
                    nexts = itertools.cycle(itertools.islice(nexts, num_active))

        return stream(lambda: gen(self))

    def sum(self) -> numbers.Real:
        return sum(self)

    def min(self, key: Callable[[_K], _V] = _IDENTITY_FUNC) -> _V:
        return min(self, key=key)

    def min_default(self, default: _T, key: Callable[[_K], _V] = _IDENTITY_FUNC) -> Union[_V, _T]:
        """
        :param default: returned if there's no minimum in stream (ie empty stream)
        :param key: the same meaning as used for the builtin min()
        """
        try:
            return min(self, key=key)
        except ValueError as e:
            if "empty" in e.args[0]:
                return default
            raise

    def max(self, key: Callable[[_K], _V] = _IDENTITY_FUNC) -> _V:
        return max(self, key=key)

    def maxes(self, key: Callable[[_K], _V] = _IDENTITY_FUNC) -> "slist[_V]":
        i = iter(self)
        aMaxes = slist([next(i)])
        mval = key(aMaxes[0])
        for v in i:
            k = key(v)
            if k > mval:
                mval = k
                aMaxes = slist([v])
            elif k == mval:
                aMaxes.append(v)
        return aMaxes

    def mins(self, key: Callable[[_K], _V] = _IDENTITY_FUNC) -> "slist[_V]":
        i = iter(self)
        aMaxes = slist([next(i)])
        mval = key(aMaxes[0])
        for v in i:
            k = key(v)
            if k < mval:
                mval = k
                aMaxes = slist([v])
            elif k == mval:
                aMaxes.append(v)
        return aMaxes

    def entropy(self: "stream[numbers.Real]") -> numbers.Real:
        """Calculates the Shannon entropy of the stream elements in single pass."""
        sum_x = 0.0
        sum_x_log_x = 0.0

        for x in self:
            val = float(x)
            if val <= 0:
                raise ValueError("Entropy is only defined for non-negative values")
            sum_x += val
            sum_x_log_x += val * math.log2(val)

        if sum_x == 0:
            return 0.0

        return math.log2(sum_x) - (sum_x_log_x / sum_x)

    def pstddev(self) -> float:
        """Calculates the population standard deviation."""
        sm = 0
        n = 0
        for el in self:
            sm += el
            n += 1
        if n < 1:
            raise ValueError("Standard deviation requires at least one data point")
        mean = float(sm) / n
        ss = sum((x - mean) ** 2 for x in self)
        pvar = ss / n  # the population variance
        return pvar**0.5

    def mean(self) -> float:
        """Return the sample arithmetic mean of data. in one single pass"""
        sm = 0
        n = 0
        for el in self:
            sm += el
            n += 1
        if n < 1:
            raise ValueError("Mean requires at least one data point")
        return sm / float(n)

    def zip(self: "stream[_K]") -> "stream[_V]":
        return stream(zip(*(tuple(self))))

    def distinct(self, key: Optional[Callable[[_K], _V]] = None) -> "stream[_K]":
        """
        The stream items should be hashable and comparable.
        :param key: optional, maps the elements to comparable objects
        :return: Unique elements appearing in the same order. Following copies of same elements will be ignored.
        :rtype: stream[_K]
        """
        return stream(lambda: _IStream.__unique_generator(self, key))

    unique = distinct

    def product(self, repeat: Optional[int] = None) -> "stream[Tuple[_V,...]]":
        """
        Generates the Cartesian Product of stream, similar with itertools.product.

        If repeat is 1, the elements of the stream should be iterables.

        :param repeat: number of times to repeat each element

        >>> stream([1,2,3]).product(2).toList()
        [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3), (3, 1), (3, 2), (3, 3)]

        >>> stream([[1,2],[3,4,5]]).product().toList()
        [(1, 3), (1, 4), (1, 5), (2, 3), (2, 4), (2, 5)]
        """
        if repeat is None:
            return stream(ItrFromFunc(lambda: itertools.product(*self)))
        return stream(ItrFromFunc(lambda: itertools.product(self, repeat=repeat)))

    # pylint: disable=too-many-arguments
    def tqdm(
        self,
        desc: Optional[str] = None,
        total: Optional[int] = None,
        leave: bool = True,
        file: Optional[io.TextIOWrapper] = None,
        ncols: Optional[int] = None,
        mininterval: float = 0.1,
        maxinterval: float = 10.0,
        ascii: Optional[Union[str, bool]] = None,  # pylint: disable=redefined-builtin
        unit: str = "it",
        unit_scale: Optional[Union[bool, int, float]] = False,
        dynamic_ncols: Optional[bool] = False,
        smoothing: Optional[float] = 0.3,
        initial: int = 0,
        position: Optional[int] = None,
        postfix: Optional[dict] = None,
        gui: bool = False,
        **kwargs,
    ) -> "stream[_K]":
        """
        :param desc: Prefix for the progressbar.
        :param total: The number of expected iterations. If unspecified,
            len(iterable) is used if possible. If float("inf") or as a last
            resort, only basic progress statistics are displayed
            (no ETA, no progressbar).
            If `gui` is True and this parameter needs subsequent updating,
            specify an initial arbitrary large positive integer,
            e.g. int(9e9).
        :param leave: If [default: True], keeps all traces of the progressbar
            upon termination of iteration.
        :param file: Specifies where to output the progress messages
            (default: sys.stderr). Uses `file.write(str)` and `file.flush()`
            methods.  For encoding, see `write_bytes`.
        :param ncols: The width of the entire output message. If specified,
            dynamically resizes the progressbar to stay within this bound.
            If unspecified, attempts to use environment width. The
            fallback is a meter width of 10 and no limit for the counter and
            statistics. If 0, will not print any meter (only stats).
        :param mininterval: Minimum progress display update interval [default: 0.1] seconds.
        :param maxinterval: Maximum progress display update interval [default: 10] seconds.
            Automatically adjusts `miniters` to correspond to `mininterval`
            after long display update lag. Only works if `dynamic_miniters`
            or monitor thread is enabled.
        :param ascii: If unspecified or False, use unicode (smooth blocks) to fill
            the meter. The fallback is to use ASCII characters " 123456789#".
        :param unit: String that will be used to define the unit of each iteration
            [default: it].
        :param unit_scale: If 1 or True, the number of iterations will be reduced/scaled
            automatically and a metric prefix following the
            International System of Units standard will be added
            (kilo, mega, etc.) [default: False]. If any other non-zero
            number, will scale `total` and `n`.
        :param dynamic_ncols: If set, constantly alters `ncols` to the environment (allowing
            for window resizes) [default: False].
        :param smoothing: Exponential moving average smoothing factor for speed estimates
            (ignored in GUI mode). Ranges from 0 (average speed) to 1
            (current/instantaneous speed) [default: 0.3].
        :param initial: The initial counter value. Useful when restarting a progress bar [default: 0].
        :param position: Specify the line offset to print this bar (starting from 0)
            Automatic if unspecified.
            Useful to manage multiple bars at once (eg, from threads).
        :param postfix: Specify additional stats to display at the end of the bar.
            Calls `set_postfix(**postfix)` if possible (dict).
        :param gui: WARNING: internal parameter - do not use.
            Use tqdm_gui(...) instead. If set, will attempt to use
            matplotlib animations for a graphical output [default: False].
        :param kwargs: Params to be sent to tqdm()
        :return: self stream
        """
        # Use length_hint if total is not provided
        len_hint = self.length_hint()
        effective_total = total if total is not None else len_hint

        return stream(
            tqdm(
                iterable=self,
                desc=desc,
                total=effective_total,
                leave=leave,
                file=file,
                ncols=ncols,
                mininterval=mininterval,
                maxinterval=maxinterval,
                ascii=ascii,
                unit=unit,
                unit_scale=unit_scale,
                dynamic_ncols=dynamic_ncols,
                smoothing=smoothing,
                initial=initial,
                position=position,
                postfix=postfix,
                gui=gui,
                **kwargs,
            ),
            length_hint=len_hint,
        )

    def throttle(self, max_req: int, interval: float) -> "stream[_K]":
        """
        Throttles the stream.

        :param max_req: number of requests
        :param interval: period in number of seconds
        :return: throttled stream

        Example:
            ```py
            >>> s = Stream()
            >>> throttled_stream = s.throttle(10, 1.5)
            >>> for item in throttled_stream:
            ...     print(item)
            ```
        """
        throttler = Throttler(max_req, interval)
        return self.map(throttler.throttle)

    @staticmethod
    def binaryToChunk(binaryData: bytes) -> bytes:
        """
        :param binaryData: binary data to transform into chunk with header
        :type binaryData: str
        :return: chunk of data with header
        :rtype: str
        """
        sz = len(binaryData)
        p = struct.pack("<L", sz)
        assert len(p) == 4
        return p + binaryData

    def dumpToPickle(self, fileStream):
        """
        :param fileStream: should be binary output stream
        :type fileStream: file
        :return: Nothing
        """

        for el in self.map(lambda _: pickle.dumps(_, pickle.HIGHEST_PROTOCOL, fix_imports=True)).map(stream.binaryToChunk):
            fileStream.write(el)

    def dumpPickledToWriter(self, writer: Callable[[bytes], _T]) -> None:
        """
        :param writer: should be binary output callable stream
        """
        for el in self:
            writer(stream._picklePack(el))  # pylint: disable=protected-access

    @staticmethod
    def _picklePack(el) -> bytes:
        return stream.binaryToChunk(pickle.dumps(el, pickle.HIGHEST_PROTOCOL))

    def exceptIndexes(self, *indexes: List[int]) -> "stream[_K]":
        """
        Doesn't support negative indexes as the stream doesn't have a length
        :return: the stream with filtered out elements on <indexes> positions
        """

        def indexIgnorer(indexSet, _stream):
            i = 0
            for el in _stream:
                if i not in indexSet:
                    yield el
                i += 1

        indexSet = frozenset(indexes)
        return stream(lambda: indexIgnorer(indexSet, self))


class _PydanticCoercingValidated:
    @classmethod
    def __get_validators__(cls):
        yield cls._pydantic_validator

    @classmethod
    def _pydantic_validator(cls, v):
        if not isinstance(v, cls):
            return cls(v)
        return v

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any):
        # return pydantic_no_info_plain_validator_function(cls)

        return pydantic_no_info_after_validator_function(
            cls, pydantic_list_schema(items_schema=pydantic_any_schema())  # Convert the list into an stream instance after validation
        )


class stream(_IStream, Iterable[_K], _PydanticCoercingValidated):
    def __init__(
        self,
        itr: Optional[Union[Iterable[_K], Iterator[_K], Callable[[], Iterable[_K]]]] = None,
        length_hint: Optional[int] = None,
        source: Optional["stream"] = None,
    ):
        self._itr, self._f = self._init_itr(itr)
        self._length_hint = length_hint
        self._source = source  # Reference to source stream for dynamic length computation

    def __iter__(self) -> Iterator[_K]:
        return iter(self.__get_itr())

    def __get_itr(self) -> Iterable[_K]:
        if self._itr is not None:
            return self._itr
        return self._f()

    def __repr__(self):
        if isinstance(self._itr, list):
            return repr(self._itr)
        return object.__repr__(self)

    def __str__(self):
        if isinstance(self._itr, list):
            return str(self._itr)
        return object.__str__(self)

    def __length_hint__(self) -> int:
        """
        Protocol method for length_hint. Raises TypeError if length is unknown.
        This is compatible with Python's length_hint protocol and operator.length_hint().
        """
        if self._length_hint is not None:
            return self._length_hint

        source = self._source if self._source is not None else self._itr
        if source is not None:
            if isinstance(source, stream):
                result = source.length_hint(default=-1)
                if result != -1:
                    return result
            else:
                len_hint = operator.length_hint(source, -1)
                if len_hint != -1:
                    return len_hint

        raise TypeError("length is unknown")

    def __reversed__(self: "stream[_K]") -> "stream[_K]":
        try:
            return stream(reversed(self.__get_itr()), source=self)
        except TypeError:
            return stream(lambda: reversed(self.toList()), source=self)

    @staticmethod
    def __binaryChunksStreamGenerator(fs, format="<L", statHandler: Optional[Callable[[int, int], None]] = None):
        # pylint: disable=redefined-builtin
        """
        :param fs:
        :type fs: file
        :param format:
        :type format: str
        :param statHandler: statistics handler, will be called before every yield with a tuple (n,size)
        :type statHandler: callable
        :return: unpickled element
        :rtype: T
        """
        count = 0
        sz = 0
        while True:
            s = fs.read(4)
            if s == b"":
                return
            if len(s) != 4:
                raise IOError("Wrong pickled file format")
            next_read_sz = struct.unpack(format, s)[0]
            _struct = fs.read(next_read_sz)
            if statHandler is not None:
                count += 1
                sz += 4 + next_read_sz
                statHandler((count, sz))
            yield _struct

    # pylint: disable=redefined-builtin
    @staticmethod
    def readFromBinaryChunkStream(readStream: BinaryIO, format: str = "<L", statHandler: Optional[Callable[[int, int], None]] = None) -> "stream[_V]":
        """
        :param statHandler: statistics handler, will be called before every yield with a tuple (n,size)
        """
        return stream(stream.__binaryChunksStreamGenerator(readStream, format, statHandler))

    @staticmethod
    def loadFromPickled(file: BinaryIO, format: str = "<L", statHandler: Optional[Callable[[int, int], None]] = None) -> "stream[_V]":
        """
        :param file: should be path or binary file stream
        :param format: format of the header
        :param statHandler: statistics handler, will be called before every yield with a tuple (n,size)
        """
        return stream.readFromBinaryChunkStream(file, format, statHandler).map(pickle.loads)


class AbstractSynchronizedBufferedStream(stream):
    """
    Thread-safe buffered stream.
    Just implement the _getNextBuffer() to return a slist() and you are good to go.
    """

    def __init__(self):
        self.__queue = collections.deque()
        self.__lock = threading.RLock()
        super().__init__()

    def __next__(self):
        with self.__lock:
            try:
                val = self.__queue.popleft()
            except IndexError:
                self.__queue.extend(self._getNextBuffer())
                if len(self.__queue) == 0:
                    raise StopIteration  # pylint: disable=raise-missing-from
                val = self.__queue.popleft()

            return val

    def __iter__(self):
        return self

    @abstractmethod
    def _getNextBuffer(self) -> Iterable[_K]:
        """
        :return: a list of items for the buffer
        """
        raise NotImplementedError

    def __str__(self):
        return object.__str__(self)

    def __repr__(self):
        return object.__repr__(self)


class buffered_stream(AbstractSynchronizedBufferedStream):
    def __init__(self, buffers: "Iterable[Iterable[_T]]"):
        self.__buffers = iter(buffers)
        super().__init__()

    def _getNextBuffer(self) -> Iterable[_T]:
        try:
            return next(self.__buffers)
        except StopIteration:
            return []


class sset(set, MutableSet[_K], _IStream):
    @property
    def _itr(self):
        return ItrFromFunc(lambda: iter(self))

    def __init__(self, *args, **kwrds):
        set.__init__(self, *args, **kwrds)

    def __iter__(self):
        return set.__iter__(self)

    # Below methods enable chaining and lambda using
    def update(self, *args, **kwargs) -> "sset[_K]":
        # ToDo: Add option to update with iterables, as set.update supports only other set
        set.update(self, *args, **kwargs)
        return self

    def intersection_update(self, *args, **kwargs) -> "sset[_K]":
        set.intersection_update(self, *args, **kwargs)
        return self

    def difference_update(self, *args, **kwargs) -> "sset[_K]":
        set.difference_update(self, *args, **kwargs)
        return self

    def symmetric_difference_update(self, *args, **kwargs) -> "sset[_K]":
        super().symmetric_difference_update(*args, **kwargs)
        return self

    def clear(self) -> "sset[_K]":
        set.clear(self)
        return self

    def remove(self, *args, **kwargs) -> "sset[_K]":
        super().remove(*args, **kwargs)
        return self

    def add(self, *args, **kwargs) -> "sset[_K]":
        super().add(*args, **kwargs)
        return self

    def discard(self, *args, **kwargs) -> "sset[_K]":
        super().discard(*args, **kwargs)
        return self

    def __reversed__(self):
        raise TypeError("'sset' object is not reversible")

    def __or__(self, s: AbstractSet[_V]) -> Set[Union[_K, _V]]:
        return sset(super().__or__(s))

    def union(self, *s: Iterable[_K]) -> Set[_K]:
        return sset(super().union(*s))

    # pylint: disable=too-many-arguments
    def tqdm(
        self,
        desc: Optional[str] = None,
        total: Optional[int] = None,
        leave: bool = True,
        file: Optional[io.TextIOWrapper] = None,
        ncols: Optional[int] = None,
        mininterval: float = 0.1,
        maxinterval: float = 10.0,
        ascii: Optional[Union[str, bool]] = None,  # pylint: disable=redefined-builtin
        unit: str = "it",
        unit_scale: Optional[Union[bool, int, float]] = False,
        dynamic_ncols: Optional[bool] = False,
        smoothing: Optional[float] = 0.3,
        initial: int = 0,
        position: Optional[int] = None,
        postfix: Optional[dict] = None,
        gui: bool = False,
        **kwargs,
    ) -> "stream[_K]":
        if total is None:
            total = self.size()
        return super().tqdm(
            desc,
            total,
            leave,
            file,
            ncols,
            mininterval,
            maxinterval,
            ascii,
            unit,
            unit_scale,
            dynamic_ncols,
            smoothing,
            initial,
            position,
            postfix,
            gui,
            **kwargs,
        )

    def __and__(self, other):
        return sset(super().__and__(other))

    def intersection(self, *s: Iterable[object]) -> Set[_K]:
        return sset(super().intersection(*s))

    def __sub__(self, s: AbstractSet[object]) -> Set[_K]:
        return sset(super().__sub__(s))

    def __xor__(self, s: AbstractSet[_V]) -> Set[Union[_K, _V]]:
        return sset(super().__xor__(s))

    def difference(self, *s: Iterable[_V]) -> Set[Union[_K, _V]]:
        return sset(super().difference(*s))

    def symmetric_difference(self, s: Iterable[_V]) -> Set[Union[_K, _V]]:
        return sset(super().symmetric_difference(s))


class slist(List[_K], stream):
    @property
    def _itr(self):
        return ItrFromFunc(lambda: iter(self))

    # pylint: disable=super-init-not-called, non-parent-init-called
    def __init__(self, *args, **kwrds):
        list.__init__(self, *args, **kwrds)

    def __getitem__(self, item) -> "Union[_K,slist[_K]]":
        if isinstance(item, slice):
            return slist(list.__getitem__(self, item))
        return list.__getitem__(self, item)

    def extend(self, iterable: Iterable[_K]) -> "slist[_K]":
        list.extend(self, iterable)
        return self

    def append(self, x) -> "slist[_K]":
        list.append(self, x)
        return self

    def remove(self, x) -> "slist[_K]":
        list.remove(self, x)
        return self

    def insert(self, i, x) -> "slist[_K]":
        list.insert(self, i, x)
        return self

    def exceptIndexes(self, *indexes: List[int]) -> "stream[_K]":
        """
        Supports negative indexes
        :type indexes: list[int]
        :return: the stream with filtered out elements on <indexes> positions
        :rtype: stream [ T ]
        """

        def indexIgnorer(indexSet: frozenset, _stream: "stream[_K]"):
            i = 0
            for el in _stream:
                if i not in indexSet:
                    yield el
                i += 1

        sz = self.size()
        indexSet = frozenset(stream(indexes).map(lambda i: i if i >= 0 else i + sz))
        return stream(lambda: indexIgnorer(indexSet, self))

    def __iadd__(self, other) -> "stream[_K]":
        list.__iadd__(self, other)
        return self

    def __add__(self, x: List[_K]) -> Union[stream[_K], List[_K]]:
        if not isinstance(x, list) and isinstance(x, stream):
            return stream(self) + x
        return slist(super().__add__(x))

    def __length_hint__(self) -> int:
        return len(self)


class sdict(Dict[_K, _V], dict, _IStream):
    @property
    def _itr(self):
        return ItrFromFunc(lambda: iter(self))

    def __init__(self, *args, **kwrds):
        dict.__init__(self, *args, **kwrds)

    def __iter__(self):
        return dict.__iter__(self)

    def __reversed__(self):
        raise TypeError("'sset' object is not reversible")

    def keys(self) -> stream[_K]:
        return stream(dict.keys(self))

    def values(self) -> stream[_V]:
        return stream(dict.values(self))

    def items(self) -> stream[Tuple[_K, _V]]:
        return stream(dict.items(self))

    def update(self, other=None, **kwargs) -> "sdict[_K,_V]":
        dict.update(self, other, **kwargs)
        return self

    def copy(self) -> "sdict[_K,_V]":
        return sdict(self.items())

    def __length_hint__(self) -> int:
        return len(self)


class defaultstreamdict(sdict):
    @property
    def _itr(self):
        return ItrFromFunc(lambda: iter(self))

    # pylint: disable=keyword-arg-before-vararg
    def __init__(self, default_factory=None, *a, **kw):
        if default_factory is not None and not callable(default_factory):
            raise TypeError("first argument must be callable")
        super().__init__(*a, **kw)
        if default_factory is None:
            self.__default_factory = object
        else:
            self.__default_factory = default_factory

    def __getitem__(self, key: _K) -> _V:
        try:
            return super().__getitem__(key)
        except KeyError:
            return self.__missing__(key)

    def __missing__(self, key):
        self[key] = value = self.__default_factory()
        return value

    def __reduce__(self):
        args = (self.__default_factory,)
        itms = list(self.items())
        return type(self), args, None, None, iter(itms)

    def copy(self) -> Mapping[_K, _V]:
        return self.__copy__()  # pylint: disable=unnecessary-dunder-call

    def __copy__(self):
        return type(self)(self.__default_factory, self)

    def __deepcopy__(self, memo):
        return type(self)(self.__default_factory, copy.deepcopy(list(self.items())))

    def __repr__(self) -> str:
        return f"defaultdict({self.__default_factory!s}, {super(self.__class__, self)!r})"

    def __str__(self) -> str:
        return dict.__str__(self)

    def __length_hint__(self) -> int:
        return len(self)


def smap(f, itr: Iterable[_K]) -> stream[_K]:
    return stream(itr).map(f)


def sfilter(f, itr: Iterable[_K]) -> stream[_K]:
    return stream(itr).filter(f)


def iter_except(func: Callable[[], _K], exc: Exception, first: Optional[Callable[[], _K]] = None) -> _K:
    """Call a function repeatedly until an exception is raised.

    Converts a call-until-exception interface to an iterator interface.
    Like builtins.iter(func, sentinel) but uses an exception instead
    of a sentinel to end the loop.

    Examples:
        iter_except(functools.partial(heappop, h), IndexError)   # priority queue iterator
        iter_except(d.popitem, KeyError)                         # non-blocking dict iterator
        iter_except(d.popleft, IndexError)                       # non-blocking deque iterator
        iter_except(q.get_nowait, Queue.Empty)                   # loop over a producer Queue
        iter_except(s.pop, KeyError)                             # non-blocking set iterator

    """
    try:
        if first is not None:
            yield first()  # For database APIs needing an initial cast to db.first()
        while True:
            yield func()
    except exc:
        pass
