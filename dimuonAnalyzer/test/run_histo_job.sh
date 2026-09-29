#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: $0 INPUT_ROOT OUTPUT_ROOT MAX_EVENTS" >&2
  exit 2
fi

INPUT_ROOT="$1"
OUTPUT_ROOT="$2"
MAX_EVENTS="$3"

SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
CMSSW_SRC="${DIMUON_CMSSW_SRC:-$(readlink -f "${SCRIPT_DIR}/../../../../CMSSW_15_1_0/src")}"
ANALYZER="${SCRIPT_DIR}/make_dimuonAnalyzer_res_test.py"

to_absolute() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    readlink -f "${SCRIPT_DIR}/${path}"
  fi
}

preserve_invalid() {
  local path="$1"
  local reason="$2"
  if [[ -e "${path}" ]]; then
    local saved="${path}.invalid.$(date +%Y%m%d_%H%M%S).$$"
    mv "${path}" "${saved}"
    echo "[INVALID] ${reason}; preserved as ${saved}" >&2
  fi
}

valid_histo_file() {
  local path="$1"
  [[ -s "${path}" ]] || return 1
  python3 - "${path}" <<'PY'
import sys
import ROOT

ROOT.gROOT.SetBatch(True)
root_file = ROOT.TFile.Open(sys.argv[1])
required = (
    "slimmedMuon/h_bestTrack_pt",
    "slimmedMuon/h_standAloneTrack_pt",
    "disMuon/h_pt",
    "disMuon/h_standAloneTrack_pt",
    "disMuon/h_vertexFit_mass",
    "disMuon/h_standAloneTrackFit_mass",
)
valid = bool(
    root_file
    and not root_file.IsZombie()
    and all(root_file.Get(name) for name in required)
)
if root_file:
    root_file.Close()
raise SystemExit(0 if valid else 1)
PY
}

INPUT_ABS="$(to_absolute "${INPUT_ROOT}")"
OUTPUT_ABS="$(to_absolute "${OUTPUT_ROOT}")"
OUTPUT_DIR="$(dirname "${OUTPUT_ABS}")"
TMP_OUTPUT="${OUTPUT_ABS%.root}.part.$$.root"
INNER_TMP="${TMP_OUTPUT}.tmp.root"

echo "[JOB] Host       : $(hostname)"
echo "[JOB] Input      : ${INPUT_ROOT}"
echo "[JOB] Output     : ${OUTPUT_ROOT}"
echo "[JOB] Max events : ${MAX_EVENTS}"

if [[ ! -s "${INPUT_ABS}" ]]; then
  echo "[ERROR] Missing or empty input: ${INPUT_ABS}" >&2
  exit 3
fi
if [[ ! -f "${ANALYZER}" ]]; then
  echo "[ERROR] Missing analysis script: ${ANALYZER}" >&2
  exit 3
fi

mkdir -p "${OUTPUT_DIR}"
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "${CMSSW_SRC}"
eval "$(scram runtime -sh)"

if valid_histo_file "${OUTPUT_ABS}"; then
  echo "[SKIP] Valid output already exists: ${OUTPUT_ABS}"
  exit 0
fi
preserve_invalid "${OUTPUT_ABS}" "existing histogram output is invalid"
preserve_invalid "${TMP_OUTPUT}" "stale temporary output"
preserve_invalid "${INNER_TMP}" "stale inner temporary output"

status=0
python3 "${ANALYZER}" "${INPUT_ABS}" "${TMP_OUTPUT}" \
  --max-events "${MAX_EVENTS}" || status=$?
if [[ "${status}" -ne 0 ]]; then
  preserve_invalid "${TMP_OUTPUT}" "histogram analysis failed with status ${status}"
  preserve_invalid "${INNER_TMP}" "histogram analysis failed with status ${status}"
  exit "${status}"
fi
if ! valid_histo_file "${TMP_OUTPUT}"; then
  preserve_invalid "${TMP_OUTPUT}" "histogram output is invalid"
  exit 5
fi
if valid_histo_file "${OUTPUT_ABS}"; then
  preserve_invalid "${TMP_OUTPUT}" "another process created the final output"
  echo "[SKIP] Another process completed: ${OUTPUT_ABS}"
  exit 0
fi
preserve_invalid "${OUTPUT_ABS}" "final path appeared but is invalid"
mv "${TMP_OUTPUT}" "${OUTPUT_ABS}"
echo "[DONE] ${OUTPUT_ABS}"
