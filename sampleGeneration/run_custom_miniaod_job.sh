#!/usr/bin/env bash
set -euo pipefail

INPUT_NPY="${1:?input NPY missing}"
LXY="${2:?Lxy missing}"
LABEL="${3:?label missing}"
EVENTS="${4:?event count missing}"
SEED="${5:?seed missing}"
OUTDIR="${6:?output directory missing}"
MOTHER_PDG="${7:?mother PDG ID missing}"
MU_MINUS_PDG="${8:?negative-muon PDG ID missing}"
MU_PLUS_PDG="${9:?positive-muon PDG ID missing}"
CMSSW14="${10:?CMSSW 14 source directory missing}"
CMSSW15="${11:?CMSSW 15 source directory missing}"
CMSSW16="${12:?CMSSW 16 source directory missing}"
SEED_STRIDE="${13:?RNG seed stride missing}"
SAMPLE_TYPE="${14:-signal}"
case "$SAMPLE_TYPE" in signal|background) ;; *) echo "Invalid sample type: $SAMPLE_TYPE" >&2; exit 1 ;; esac

WORKFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
CFG_DIR="${WORKFLOW_DIR}/cfg"
# Keep the existing Condor argument/label format without a Python path helper.
if [[ "$LABEL" =~ ^([A-Za-z0-9_.+/-]+)__chunk[0-9]+_lxy([0-9]+(p[0-9]+)?)$ ]] && [[ "$LABEL" != *".."* ]]; then
  SETTING="${BASH_REMATCH[1]}_lxy${BASH_REMATCH[2]}"
else
  echo "[ERROR] invalid mass/Lxy job label: ${LABEL}" >&2
  exit 1
fi
INPUT_NAME="${INPUT_NPY##*/}"
if [[ ! "$INPUT_NAME" =~ ^Events_[0-9]+\.npy$ ]]; then
  echo "[ERROR] expected Events_<n>.npy input: ${INPUT_NPY}" >&2
  exit 1
fi
ROOT_NAME="${INPUT_NAME%.npy}.root"
GEN_SIM_RAW="${OUTDIR}/gen_sim_raw/${SETTING}/${ROOT_NAME}"
AODSIM="${OUTDIR}/aod_custom/${SETTING}/${ROOT_NAME}"
MINIAODSIM="${OUTDIR}/miniaod_custom/${SETTING}/${ROOT_NAME}"
STAGE_LOG="${OUTDIR}/stage_logs_custom"
CUSTOM_CFG_DIR="${CFG_DIR}"
mkdir -p "${OUTDIR}/aod_custom/${SETTING}" "${OUTDIR}/miniaod_custom/${SETTING}" "$STAGE_LOG"

source /cvmfs/cms.cern.ch/cmsset_default.sh

activate_release() {
  local release_src="$1"
  cd "$release_src"
  eval "$(scram runtime -sh)"
}

valid_root_file() {
  local path="$1"
  [ -s "$path" ] || return 1
  python3 - "$path" >/dev/null 2>&1 <<'PY'
import sys
import ROOT

ROOT.gROOT.SetBatch(True)
root_file = ROOT.TFile.Open(sys.argv[1])
valid = bool(
    root_file
    and not root_file.IsZombie()
    and not root_file.TestBit(ROOT.TFile.kRecovered)
    and root_file.Get("Events")
)
if root_file:
    root_file.Close()
raise SystemExit(0 if valid else 1)
PY
}

valid_edm_file() {
  local path="$1"
  valid_root_file "$path" && edmFileUtil "$path" >/dev/null 2>&1
}

valid_custom_file() {
  local path="$1"
  valid_edm_file "$path" || return 1
  python3 - "$path" >/dev/null 2>&1 <<'CHECK'
import sys
from DataFormats.FWLite import Events, Handle
required = [
    ("displacedStandAloneMuons", "", "RECO", "std::vector<reco::Track>"),
    ("displacedStandAloneMuonsVertexConstrained", "", "RECO", "std::vector<reco::Track>"),
    ("displacedStandAloneMuonsVertexConstrained", "UpdatedAtVtx", "RECO", "std::vector<reco::Track>"),
    ("displacedMuonSeeds", "", "RECO", "std::vector<TrajectorySeed>"),
]
if "/miniaod_custom/" in sys.argv[1]:
    required += [(name, "", "PAT", "std::vector<pat::Muon>") for name in
                 ("slimmedDisplacedMuons", "slimmedDisplacedMuonsVertexConstrained")]
else:
    required += [(name, "", "RECO", "std::vector<reco::Muon>") for name in
                 ("displacedMuons", "displacedMuonsVertexConstrained")]
for event in Events(sys.argv[1]):
    for module, instance, process, typename in required:
        handle = Handle(typename)
        event.getByLabel((module, instance, process), handle)
        if not handle.isValid():
            raise RuntimeError("Missing product: " + module)
    break
else:
    raise RuntimeError("No events in custom output")
CHECK
}

preserve_invalid() {
  local path="$1"
  local reason="$2"
  if [ -e "$path" ]; then
    local saved="${path}.invalid.$(date +%Y%m%d_%H%M%S).$$"
    mv "$path" "$saved"
    echo "[INVALID] ${reason}; preserved as ${saved}"
  fi
}

run_stage() {
  local name="$1"
  local final_output="$2"
  local required_input="$3"
  local cfg="$4"
  shift 4

  if valid_custom_file "$final_output"; then
    echo "[SKIP] ${name}: valid output already exists: ${final_output}"
    return 0
  fi
  preserve_invalid "$final_output" "${name} output is not a valid EDM ROOT file"
  if [ -n "$required_input" ] && ! valid_edm_file "$required_input"; then
    echo "[ERROR] ${name}: invalid required input: ${required_input}" >&2
    return 4
  fi

  local run_stamp temporary_output log status
  run_stamp="$(date +%Y%m%d_%H%M%S)"
  temporary_output="${final_output}.part.$$"
  log="${STAGE_LOG}/${LABEL//\//__}_${name}_${run_stamp}.log"
  preserve_invalid "$temporary_output" "stale ${name} temporary output"
  echo "[RUN] ${name} start: $(date) on $(hostname)"
  if cmsRun "$cfg" "$@" outputFile="$temporary_output" 2>&1 | tee "$log"; then
    :
  else
    status=$?
    preserve_invalid "$temporary_output" "${name} cmsRun failed"
    echo "[ERROR] ${name} failed with status ${status}" >&2
    return "$status"
  fi
  if ! valid_custom_file "$temporary_output"; then
    preserve_invalid "$temporary_output" "${name} produced an invalid EDM ROOT file"
    return 5
  fi
  if valid_custom_file "$final_output"; then
    mv "$temporary_output" "${temporary_output}.duplicate.${run_stamp}"
    echo "[SKIP] ${name}: another process created ${final_output}"
    return 0
  fi
  preserve_invalid "$final_output" "${name} final path appeared but is invalid"
  mv "$temporary_output" "$final_output"
  echo "[DONE] ${name}: ${final_output}"
}

echo "[INFO] label=${LABEL} input=${GEN_SIM_RAW} lxy=${LXY} events=${EVENTS} seed=${SEED}"
activate_release "$CMSSW15"
if valid_custom_file "$MINIAODSIM"; then
  echo "[SKIP] miniaod: valid custom output already exists: ${MINIAODSIM}"
  exit 0
fi
activate_release "$CMSSW14"
run_stage reco "$AODSIM" "$GEN_SIM_RAW" "${CUSTOM_CFG_DIR}/reco_dsa_vertex_constraint_cfg.py" \
  maxEvents="$EVENTS" inputFile="$GEN_SIM_RAW" seed="$((SEED + 2 * SEED_STRIDE))"
activate_release "$CMSSW15"
run_stage miniaod "$MINIAODSIM" "$AODSIM" "${CUSTOM_CFG_DIR}/miniaod_dsa_vertex_constraint_cfg.py" \
  maxEvents="$EVENTS" inputFile="$AODSIM" seed="$((SEED + 3 * SEED_STRIDE))"
echo "[DONE] MINIAODSIM: ${MINIAODSIM}"
