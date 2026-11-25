"""Run the existing RAW -> AODSIM configuration with a parallel constrained chain."""
from pathlib import Path
import runpy
import sys

_config_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_config_dir))
from dsa_vertex_constraint_customise import customise_reco

_base_cfg = _config_dir / "reco_cfg.py"
_base = runpy.run_path(str(_base_cfg))
process = customise_reco(_base["process"])
# The production cfg deliberately processes all events. Honour maxEvents here
# for small comparison tests, without changing the production cfg itself.
process.maxEvents.input = _base["_runtime_options"].maxEvents
