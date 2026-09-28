"""Defaults for the proton-bremsstrahlung dimuon Condor workflow."""

import os
from pathlib import Path

LXY_VALUES_MM = [0.0, 1800.0]

# Limit the number of chunks selected from each category for an Lxy value.
# None means that every available chunk is selected.
MAX_CHUNKS_PER_CATEGORY_BY_LXY = {
    0.0: 100,
    1800.0: None,
}

# Site-specific paths belong in environment variables or command-line options.
DEFAULT_NPY_DIRECTORY = os.environ.get("DIMUON_NPY_DIR")
# Select only barrel chunks for this production. Change this to
# ["endcap*.npy"] for the later endcap production, or include both patterns.
NPY_FILENAME_PATTERNS = ["barrel*.npy"]

CMSSW_BASE = os.environ.get("DIMUON_CMSSW_BASE")
CMSSW14_SRC = os.environ.get("DIMUON_CMSSW14_SRC")
CMSSW15_SRC = os.environ.get("DIMUON_CMSSW15_SRC")
if CMSSW_BASE:
    CMSSW14_SRC = CMSSW14_SRC or str(Path(CMSSW_BASE) / "CMSSW_14_0_18" / "src")
    CMSSW15_SRC = CMSSW15_SRC or str(Path(CMSSW_BASE) / "CMSSW_15_0_2" / "src")

MOTHER_PDG_ID = 999999
MU_MINUS_PDG_ID = 13
MU_PLUS_PDG_ID = -13

BASE_SEED = 42
# Reserve this many consecutive RNG seeds for every stage of every job.
RNG_SEED_STRIDE = 1000

REQUEST_CPUS = 1
REQUEST_MEMORY = "4GB"
