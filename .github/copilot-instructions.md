---
applyTo: '**/*.py'
---

# Streamerate Project Guide for AI Agents

## Project Overview
A small, single-package Python library providing a fluent, chainable API for processing iterables (`stream`) with single-threaded, multithreaded, and multiprocessing variants (`map`, `fastmap`, `mtmap`, `mpmap`).

**Architecture**: Wrapper-based data flow: Iterable → `stream` wrapper → Lazy Transformation Chain → Terminal Operation (`toList`, `toSet`, `toMap`, or consumption)

## Critical Development Environment

### Working Directory & Test Execution
**Always work from the project root (where `pyproject.toml` exists).** All tests, imports, and scripts assume this as the working directory.

```bash
# Correct test execution pattern
poetry install
poetry run ./run_tests.py  # Uses unittest discovery, returns non-zero on failure
# OR
poetry run python -m unittest discover streamerate/tests -v

```

### Environment Setup

* Python Version: **>= 3.10**
* Dependency Manager: **Poetry**
* Linter/Formatter: `pre-commit` (Black, Isort, Pylint, Ruff)

### Test Framework: stdlib `unittest` ONLY

**Never use pytest/nose.** Project uses `unittest.TestCase` exclusively.
Tests are located in `streamerate/tests/`.

## Data Architecture & Key Components

### Core Components

1. **The `stream` Class** (`streamerate/streams.py`)
* The main entry point. Wraps an iterable to provide fluent methods.
* Output types: `slist`, `sset`, `sdict`, `defaultstreamdict` (preserve chainability).


2. **Lazy Evaluation** (`_IStream`, `ItrFromFunc`)
* Most operations must remain lazy (generator-based).
* Constructors often accept a callable returning an iterable to allow re-iteration.


3. **Concurrency Primitives**
* **`fastmap` / `mtmap**`: Multithreaded mappings. Be mindful of GIL and I/O vs CPU-bound logic.
* **`mpmap` / `mpfastmap**`: Multiprocessing mappings. **CRITICAL**: Functions MUST be picklable.


4. **Exception Handling** (`_MapException`, `tblib`)
* Internal map helpers wrap exceptions to preserve original tracebacks across threads/processes.
* Tests assert specific stack lines; do not break this behavior.



### Integration Patterns

* **Gevent**: Optional dependency. Code paths try to import `gevent.pool` gracefully.
* **Pydantic**: Compatibility checks for v1 and v2 exist; degrade gracefully if missing.

## Critical Code Patterns

### Fluent Chaining: Use `stream`

```python
from streamerate import stream

# NEVER use list comprehensions for complex chains if stream is available
data = stream(range(100))\
    .filter(lambda x: x % 2 == 0)\
    .map(lambda x: x * 2)\
    .batch(10)\
    .toList()

```

### Multiprocessing Safety

```python
# Functions passed to mpmap MUST be top-level or picklable
def picklable_func(x):
    return x * x

# BAD: Lambda inside mpmap (often fails pickling on some OS/start methods)
# stream(data).mpmap(lambda x: x*x)

# GOOD:
stream(data).mpmap(picklable_func)

```

### Type Hints & Stubs

The file `streamerate/__init__.pyi` is authoritative for public API type signatures.
Keep it in sync with `streamerate/streams.py`.

## Testing Principles

### Test Execution Order

1. **Run `run_tests.py**` - This is the primary gatekeeper.
2. **Run pre-commit hooks** - Ensure linting passes (`pre-commit run --all-files`).

### Test Coverage Requirements

* **All new code MUST have unit tests** in `streamerate/tests/` covering:
* **Laziness**: Ensure generators are not consumed prematurely.
* **Re-iteration**: Ensure streams created from callables can be iterated multiple times.
* **Picklability**: Ensure `mpmap` works with standard picklable functions.
* **Tracebacks**: Ensure exceptions raised in threads/processes point to the correct source line.


* **No sleeps/flaky tests** - Use deterministic synchronization or `join`.
* **Performance**: Tests should be fast; avoid heavy compute in unit tests.

### Common Test Patterns

```python
class TestStreamFeatures(TestCase):
    def test_lazy_evaluation(self):
        # specific test ensuring code doesn't execute until terminal op
        ...

    def test_mpmap_exception_traceback(self):
        # specific test ensuring traceback is preserved
        ...

```

## Tools & Scripts

### Test Runner (`./run_tests.py`)

Custom script wrapping `unittest` discovery. Returns proper exit codes for CI.

### Configuration Files

* `pyproject.toml`: Poetry config, Black settings (line-length 160), Ruff, Pylint.
* `.pre-commit-config.yaml`: Hooks for linting.

## Code Style & Conventions

### Line Length: 160 characters (configured in `pyproject.toml`)

Use full width to reduce line count while maintaining readability.

### Type Annotations: Required

Update `__init__.pyi` alongside implementation changes.

### Import Style: Explicit top-level imports

```python
from streamerate import stream, slist  # GOOD

# BAD: Inline imports or wildcard imports
from streamerate.streams import *

```

### Design Principles

* **YAGNI**: Don't add features/abstractions not explicitly requested.
* **Laziness**: Default to lazy evaluation wherever possible.
* **SOLID**: Respect Single Responsibility in stream operators.
* **No over-engineering**: Keep the API surface clean and chainable.

## CI/CD (GitHub Actions/Poetry)

### Build Trigger

1. Push triggers test run via Poetry.
2. Semantic versioning managed via Commitizen conventions.
3. All tests must pass before merge.

## Common Pitfalls to Avoid

1. **Running tests from wrong directory** → Always run from root (pyproject.toml location).
2. **Using pytest** → Project uses `unittest` exclusively.
3. **Breaking Picklability** → Using lambdas or locals in `mpmap` tests.
4. **Eager Evaluation** → Consuming iterators in intermediate steps (map/filter).
5. **Ignoring Tracebacks** → changing exception handling without checking `tblib` logic.
6. **Adding new dependencies** → Dependencies should remain minimal (tqdm, throttlex, tblib).
7. **Changing test expectations to pass** → Fix implementation, not tests.
8. **Generating documentation files** → Provide findings in conversation.

## Key Files Reference

* `streamerate/streams.py` - Core implementation.
* `streamerate/__init__.pyi` - Authoritative Type Stubs.
* `streamerate/tests/` - Exhaustive unit tests.
* `run_tests.py` - Test execution entry point.
* `pyproject.toml` - Build and Style config.

---

# Detailed Ground Rules (especially for code generation and testing):

Sequential Thinking MCP server – usage rules:

* If a step-tracking reasoning facility is available (e.g., MCP for sequential reasoning), use it for every step.
* For each step, persist a record with camelCase keys and proper JSON types:
* thought (string), thoughtNumber (number, 1-based), totalThoughts (number), nextThoughtNeeded (boolean).
Optional: isRevision (boolean), revisesThought (number), branchFromThought (number), branchId (string).


* Decide the planned total first; keep thoughtNumber ≤ totalThoughts.
Set nextThoughtNeeded: false on the final step.
* No wrappers or banners around the JSON. Do not stringify numbers/bools.
* On a revision, send a new record with isRevision: true and revisesThought: <n>.
* If the facility is unavailable, state it explicitly and stop (don’t simulate).
Use these rules for every task; then do the task normally and produce the final deliverable.

Terminal/command run instructions:
You are running over powershell! The PyCharm will run you in this context:
`"%CONDA_BAT%" run -n <ENV_NAME> powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command %*`
Use `mvn.bat` for Maven, and `gradle.cmd` for Gradle projects. These are expected to be avail from cmdline.

Python: `streamerate` poetry env, Python >= 3.10.

Try to perform as much as possible changes at a time. Don't do small iterations - do bigger iterations. Run tests only after the code is done for all of the task, and check then what works or not. Never adapt the tests to the code - follow the business logic based on the Class/Method names and comments, and write the tests regardless of what you read in the code. Decide the logic only based on interfaces/ high-level namings in the code - not the actual existing logic there.
Project context: High-performance Python streaming. Performance matters, but readability and correctitude matters even more! Follow the best practices from Python industry, write clean and maintainable code. Reach internet if needed for search.
Don't upgrade or downgrade the Python versions of the or lib binaries unless this is explicitly needed.

When writing tests, use the best practices from QA like partitioning equivalence, boundary testing, orthogonal arrays, and think also about corner cases and negative scenarios. Be careful also with the unit-tests running time, to be lightning fast, think of every wasted millisecond, avoid sleeps where possible.
Ensure that the tests you write, also pass by running them, but only at the end, avoid excessive test running to save time, and develop the task faster.

Don't introduce new project dependencies, unless this is the only way to do stuff, or this would lead to lot of redundant code. If you have a suggestion of adding a dependency library which would solve issues, please suggest and ask this first.

# Testing Rules

* Tests should fail when the functionality they're testing fails, and should fail fast.
* If you change code somewhere, at the end of development, ensure the tests in the whole project also pass. Avoid excessive test-running, but never finish the dev task without ensuring the tests pass.
* If the existing test uses some external resource/data (e.g., gevent), and now it's missing - fail the task and notify the user;
* NEVER skip/disable the tests, even if the dependency is missing; When you consider that the dependency is missing or connection to an external resource fails, fail the test, DON'T skip test;
* NEVER skip/disable the tests, even if the data is missing; When you consider that the input data or connection to an external resource is missing, just notify me about this, DON'T skip test;

## Testing Rules - CRITICAL

### NEVER Mask Errors in Tests

**ABSOLUTE RULE**: When a test fails, you MUST fix the underlying issue, NOT change the test to accept the error as valid.

#### Forbidden Actions:

1. ❌ NEVER change test assertions to accept both SUCCESS and ERROR when only SUCCESS was expected
2. ❌ NEVER change expected values in assertions to match actual (wrong) values
3. ❌ NEVER add try-catch blocks to suppress exceptions in tests
4. ❌ NEVER skip or disable failing tests
5. ❌ NEVER add conditions like "if (error) { /* ignore */ }" in tests
6. ❌ NEVER change test expectations to match broken behavior

#### Required Actions:

1. ✅ ALWAYS fix the root cause of test failures
2. ✅ ALWAYS investigate WHY a test is failing before making any changes
3. ✅ ALWAYS ask the user if the expected behavior should change
4. ✅ ALWAYS assume the test expectations are correct unless explicitly told otherwise
5. ✅ ALWAYS treat test failures as bugs in the implementation, not in the test
6. ✅ ALWAYS make the implementation match the test, not the other way around

### When a Test Fails:

1. Read the test expectations carefully - they define the CORRECT behavior
2. Analyze WHY the implementation doesn't meet those expectations
3. Fix the implementation to meet the test expectations
4. If you believe the test expectations are wrong, ASK the user first
5. NEVER change the test to accept the broken behavior
6. NEVER skip the test if resources missing, like: `if not has_gevent: self.skipTest("Gevent missing")`

### Example of WRONG approach (FORBIDDEN):

```python
# Test expects List[int]
self.assertEqual(result, [1, 2, 3])

# Test fails with [1, 2]
# ❌ WRONG: Change test to accept result
self.assertTrue(result == [1, 2] or result == [1, 2, 3])

```

### Example of CORRECT approach:

```python
# Test expects List[int]
self.assertEqual(result, [1, 2, 3])

# Test fails with [1, 2]
# ✅ CORRECT: Fix the implementation so it returns [1, 2, 3]
# Investigate why the item was dropped and fix the root cause

```

### Critical: Never Change Test Intent

**ABSOLUTE RULE**: When fixing a failing test, you MUST preserve the test's original intent and what it's testing.

#### Forbidden Actions:

1. ❌ NEVER change test parameters to make the test pass
2. ❌ NEVER simplify test conditions to avoid failures
3. ❌ NEVER remove the core functionality being tested
4. ❌ NEVER change any test parameters to work around errors

#### Required Actions:

1. ✅ ALWAYS fix the implementation/environment to match the test requirements
2. ✅ ALWAYS preserve the original test parameters
3. ✅ If the test requires specific features (like Multiprocessing), ensure the environment supports them, otherwise fail the test
4. ✅ If environment doesn't support the feature, ASK the user before changing the test
5. ✅ The test name indicates what it tests - preserve that functionality

#### Example:

* Test name: `testMpMapWithPicklableFunc`
* ❌ WRONG: Change to `fastmap` (threading) to avoid pickling issues
* ✅ CORRECT: Fix the function to be picklable, OR ask user if test intent should change

## Critical: NEVER Change Tests to Pass

**ABSOLUTE RULE**: When a test fails, you MUST fix the underlying implementation, NOT change the test to make it pass.

### Forbidden Actions:

1. ❌ NEVER remove assertions from failing tests
2. ❌ NEVER change assertions to be less strict (e.g., assertTrue instead of assertEqual)
3. ❌ NEVER add conditional logic to skip assertions
4. ❌ NEVER change expected values to match actual (wrong) values
5. ❌ NEVER add logging and remove the assertion
6. ❌ NEVER change the test to accept both success and failure

### Required Actions:

1. ✅ ALWAYS keep the original test assertions unchanged
2. ✅ ALWAYS fix the implementation to make the test pass as written
3. ✅ ALWAYS assume the test defines the correct behavior
4. ✅ If you believe the test is wrong, ASK the user first before changing it

### When User Says "Don't change the test, ONLY code":

* This means: Keep ALL test assertions exactly as they are
* Fix ONLY the production code (`streamerate/`)
* Do NOT modify ANY test files (`streamerate/tests/`)

## Critical: YAGNI and Minimalism

* **DO NOT add features, classes, or code that were not explicitly requested**
* **DO NOT create "helpful" additions** - if the user didn't ask for it, don't add it
* **DO NOT anticipate needs** - implement exactly what was asked, nothing more
* **When cloning/adapting code**: Copy the structure and pattern, but DO NOT add new features
* **Default to DELETION over ADDITION** - when in doubt, remove rather than add
* **Question every line**: If you can't justify why the user explicitly needs it, delete it

### Rule of thumb:

* If you clone/transpile some code, **If it's not in the original AND not explicitly requested → DELETE IT**
* **If it's not explicitly requested → DELETE IT**

### Examples of FORBIDDEN additions:

* Adding "trial" or "demo" features not in the original
* Adding "helper" methods or classes not in the original
* Adding "convenience" features
* Adding logging beyond what exists in the original
* Adding validation beyond what exists in the original

## Critical: Complete Implementation - No TODOs

**ABSOLUTE RULE**: When cloning/adapting code from a reference implementation, you MUST implement ALL the functionality that exists in the original, even if some parts need to be adapted.

### Forbidden Actions:

1. ❌ NEVER leave TODO comments for core functionality that exists in the reference
2. ❌ NEVER skip implementing a component that exists in the original with "will add later"
3. ❌ NEVER use "when X is configured" as an excuse to skip implementation
4. ❌ NEVER assume something is "optional" if it exists in the reference implementation

### Required Actions:

* ✅ If a dependency is missing → create it or ask the user
* ✅ Complete the full flow end-to-end, not just the "easy parts"

### When Cloning Code:

* **Identify ALL components** in the reference implementation
* **Implement ALL of them** in the target
* **If something is missing** (like config fields), ADD it
* **If you can't implement something**, ASK the user first
* **NEVER leave TODOs** for core functionality

### Rule of Thumb:

* If it's in the reference AND it's core functionality → IMPLEMENT IT FULLY
* If you can't implement it → ASK, don't leave TODO

## Critical: Ask Before Making Assumptions About Requirements

**ABSOLUTE RULE**: When facing an error or issue, NEVER assume what the correct behavior should be. ALWAYS ask the user first.

### Forbidden Actions:

1. ❌ NEVER assume that skipping/ignoring data is acceptable
2. ❌ NEVER assume that filtering/limiting scope is the solution
3. ❌ NEVER change requirements based on what seems "easier" to implement
4. ❌ NEVER assume "this is normal" without explicit confirmation
5. ❌ NEVER work around errors by reducing functionality

### Required Actions:

1. ✅ When you encounter an error, DESCRIBE the problem and ASK what the correct behavior should be
2. ✅ Present multiple solution options and let the user choose
3. ✅ If data is missing, ASK whether to: fetch more data, expand scope, or handle differently
4. ✅ Assume the user wants FULL functionality unless explicitly told otherwise
5. ✅ When in doubt about scope (e.g., "all features" vs "some features"), ASK

### Rule of Thumb:

**When you see an error → DON'T assume a fix → ASK the user what the correct behavior should be**

# Implementation details

* The project has 160 char line length configured (see pyproject.toml), so try to reuse this space to reduce the number of code lines;
* When fixing compilation errors that require implementing methods, implement them by throwing NotImplemented errors rather than providing actual implementations.
* Prefer `streamerate` idioms over list comprehensions where applicable.
* In general, before taking a decision on what class to use, take a look over the existing codebase and if there's a class doing what you need, use that instead of common Python libs.
* avoid adding redundant logs and comments; Be concise with the code, and ensure that the code is self-explanatory and doesn't require additional comments;
* put accent on the method and variable names, make them self-explanatory, so it's clear what they do and return;
* Don't over-engineer! Avoid creating redundant interfaces, that are implemented only by one class and clear that won't be extended by other classes; Prefer final classes;
* Write SOLID compatible code!
* Don't add redundant comments or redundant logging; The code should be self-explanatory; If the code requires a comment - this is a red-flag and refactor the code so it doesn't require the comment;
* The logging messages are also a red-flag; If you feel the need to log something - refactor the code so that logging is not required;
* When writing or editing code, always use normal import statements at the top of the file instead of fully-qualified class names inline — keep code readable and idiomatic.
* DO NOT generate summary document by default (unless explicitly asked in prompt); Do generate a very brief and short summary at the end, but NO SUMMARIES in separate files/documents; Just summary in your output;
* Avoid logging and commenting, and add it ONLY where it's CRITICALLY needed;
* No redundant comments, documentation or logging. Avoid comments as much as possible. If the code requires comments - it means the naming is unclear, so review the naming of variables or function names;
* The need of logging is also a sign of issues in the code; If you feel that you need logging, review and refactor the code so it's clear, and works without need of redundant logs;
* Avoid optional parameters to the constructors, where they construct their own dependencies. The dependencies must be injected via constructor parameters. This improves testability and maintainability;

Remember:

* Tests define the CONTRACT - they specify what SHOULD happen
* Implementation must fulfill the contract
* If implementation doesn't fulfill the contract → FIX THE IMPLEMENTATION
* Changing tests to accept broken behavior is HIDING BUGS, not fixing them
* DO NOT generate summary document, unless explicitly asked in prompt!
* NEVER-EVER remove or move the existing files in the repository. You can do operations only on the files YOU have created. Be very cautious with the existing files. Change only the code, and don't run move commands in the terminal, never run dangerous commands in shell or terminal! Don't touch external files, which are not created explicitly by you! Better ask questions before performing actions!
* Remember, NEVER-EVER remove or move the existing files in the repository!
* Remember, NEVER skip/disable the tests !
* use Context7 for documentation; use Sequential Thinking to plan the tasks you do;
* when in doubt, or the requirements are ambiguous, better ask additional questions instead of assuming;
