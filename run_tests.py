#!/usr/bin/env python
# Author: ASU --<andrei.suiu@gmail.com>
import os
import sys
import unittest


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    pymajorVersion = sys.version_info[0]
    packageDir = os.path.join(os.path.dirname(__file__), "streamerate")
    testsDir = os.path.join(packageDir, "tests")
    trunner = unittest.TextTestRunner(sys.stdout, descriptions=True, verbosity=0)
    testSuite = testLoader.discover(start_dir=testsDir, pattern="test_*.py", top_level_dir=testsDir)
    res = trunner.run(testSuite)

    testSuite = testLoader.discover(start_dir=testsDir, pattern="test_*.py", top_level_dir=testsDir)
    testResult = unittest.TestResult()
    res = testSuite.run(testResult)
    assert not res.errors, "Unittests error: %s" % res.errors
    print(res)
