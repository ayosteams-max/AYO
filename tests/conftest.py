import os

import pytest

# The current prototype reads the generic DEBUG variable at import time. A host may
# define an incompatible value, so tests isolate it until Milestone 4 hardens config.
os.environ["DEBUG"] = "true"

from BACKEND.repositories.registry import reset_in_memory_repositories  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_in_memory_state():
    reset_in_memory_repositories()
    yield
    reset_in_memory_repositories()
