"""Editable common, signal, and background defaults for the Condor workflow."""

import os
from pathlib import Path

# Explicit release paths override DIMUON_CMSSW_BASE, then the home directory.
_CMSSW_BASE = Path(os.environ.get("DIMUON_CMSSW_BASE") or Path.home())

COMMON = {
    "cmssw14_src": os.environ.get("DIMUON_CMSSW14_SRC") or str(_CMSSW_BASE / "CMSSW_14_0_18" / "src"),
    "cmssw15_src": os.environ.get("DIMUON_CMSSW15_SRC") or str(_CMSSW_BASE / "CMSSW_15_0_2" / "src"),
    "cmssw16_src": os.environ.get("DIMUON_CMSSW16_SRC") or str(_CMSSW_BASE / "CMSSW_16_1_3" / "src"),
    "mother_pdg_id": 999999,
    "mu_minus_pdg_id": 13,
    "mu_plus_pdg_id": -13,
    "base_seed": 42,
    # Reserve consecutive RNG seeds for each stage of every job.
    "rng_seed_stride": 1000,
    "request_cpus": 1,
    "request_memory": "4GB",
    "max_events": -1,
}

# Lxy keys are in mm; None selects every available chunk per category.
SIGNAL = {
    "npy_directory": "/xrd/store/user/taehee/dimuonProtonBremNpy",
    "output_directory": "/xrd/store/user/taehee/dimuonProtonBrem/sampleGeneration/condor",
    "category_patterns": ["barrel_m_2.0*_GeV"],
    "max_chunks_by_lxy": {3300.0: None, 3800.0: None},
    "custom_raw_directory": "/xrd/store/user/taehee/dimuonProtonBrem/sampleGeneration/condor/gen_sim_raw",
    "custom_output_directory": "/xrd/store/user/taehee/dimuonProtonBrem/sampleGeneration/condor",
    "submit_jobs": True,
}

BACKGROUND = {
    "npy_directory": "/xrd/store/user/taehee/dimuonMesonBkgNpy/chunks",
    "output_directory": "/xrd/store/user/taehee/dimuonMesonBkg/sampleGeneration/condor",
    "category_patterns": ["eta_continuum_HCal"],
    "max_chunks_by_lxy": {1800.0: None},
    "custom_raw_directory": "/xrd/store/user/taehee/dimuonMesonBkg/sampleGeneration/condor/gen_sim_raw",
    "custom_output_directory": "/xrd/store/user/taehee/dimuonMesonBkg/sampleGeneration/condor",
    "submit_jobs": False,
    "source_directory": "/xrd/store/user/taehee/dimuonMesonBkgNpy",
    "chunk_rows": 1000,
    "max_chunks_per_source": 10,
}
