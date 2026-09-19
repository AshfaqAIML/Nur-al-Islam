import os
import sys

_WORKER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# worker root (production modules) + eval package dir (sibling imports)
sys.path.insert(0, _WORKER_ROOT)
sys.path.insert(0, os.path.join(_WORKER_ROOT, "eval"))
