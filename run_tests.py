#!/usr/bin/env python
# Author: ASU --<andrei.suiu@gmail.com>
import os
import sys
import unittest

if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    packageDir = os.path.dirname(__file__)
    testsDir = os.path.join(packageDir, "streamerate", "tests")

    # Run tests with output
    trunner = unittest.TextTestRunner(sys.stdout, descriptions=True, verbosity=2)
    testSuite = testLoader.discover(start_dir=testsDir, pattern="test_*.py", top_level_dir=packageDir)
    result = trunner.run(testSuite)

    # Exit with error code if tests failed
    if not result.wasSuccessful():
        sys.exit(1)
    sys.exit(0)
