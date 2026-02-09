"""Root conftest — runs before any test module imports."""

import os

# GitHub Actions sets FORCE_COLOR=1, which makes Rich inject ANSI escape
# codes into CLI output.  This breaks tests that parse stdout as JSON or
# check for plain-text substrings like "--format".  Removing it here, at
# the earliest possible point, ensures Rich's Console() initialises in
# no-color mode regardless of the CI environment.
os.environ.pop("FORCE_COLOR", None)
os.environ["NO_COLOR"] = "1"
