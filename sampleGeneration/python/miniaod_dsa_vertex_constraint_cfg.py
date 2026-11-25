"""Run standard PAT/slimming for both displaced-muon reconstruction chains."""
from pathlib import Path
import runpy
import sys

_config_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_config_dir))
from dsa_vertex_constraint_customise import customise_miniaod

_base_cfg = _config_dir / "miniaod_cfg.py"
_base = runpy.run_path(str(_base_cfg))
process = customise_miniaod(_base["process"])
process.maxEvents.input = _base["_runtime_options"].maxEvents
