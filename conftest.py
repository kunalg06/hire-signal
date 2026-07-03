# Root conftest — under pytest's default prepend import mode this file's
# presence puts the project root on sys.path; the explicit insert below keeps
# `from app...` imports working under --import-mode=importlib as well.
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
