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
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CMSSW_SRC="${DIMUON_CMSSW_SRC:-$(readlink -f "${PROJECT_DIR}/../../../../CMSSW_15_1_0/src")}"
CFG="${PROJECT_DIR}/config/dimuonAnalyzer_cfg.py"

to_absolute() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    readlink -f "${PROJECT_DIR}/${path}"
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

valid_analysis_file() {
  local path="$1"
  [[ -s "${path}" ]] || return 1
  python3 - "${path}" <<'PY'
import sys
import ROOT

ROOT.gROOT.SetBatch(True)
root_file = ROOT.TFile.Open(sys.argv[1])
valid = bool(
    root_file
    and not root_file.IsZombie()
    and root_file.Get("dimuonAnalyzer/tree")
    and root_file.Get("dimuonAnalyzer/eventWeight")
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
PRODUCED_OUTPUT="${TMP_OUTPUT}"
if [[ "${MAX_EVENTS}" -gt 0 ]]; then
  PRODUCED_OUTPUT="${TMP_OUTPUT%.root}_numEvent${MAX_EVENTS}.root"
fi

echo "[JOB] Host       : $(hostname)"
echo "[JOB] Input      : ${INPUT_ROOT}"
echo "[JOB] Output     : ${OUTPUT_ROOT}"
echo "[JOB] Max events : ${MAX_EVENTS}"

if [[ ! -s "${INPUT_ABS}" ]]; then
  echo "[ERROR] Missing or empty input: ${INPUT_ABS}" >&2
  exit 3
fi
if [[ ! -f "${CFG}" ]]; then
  echo "[ERROR] Missing CMSSW configuration: ${CFG}" >&2
  exit 3
fi

mkdir -p "${OUTPUT_DIR}"
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "${CMSSW_SRC}"
eval "$(scram runtime -sh)"

if valid_analysis_file "${OUTPUT_ABS}"; then
  echo "[SKIP] Valid output already exists: ${OUTPUT_ABS}"
  exit 0
fi
preserve_invalid "${OUTPUT_ABS}" "existing output is invalid"
preserve_invalid "${TMP_OUTPUT}" "stale temporary output"
if [[ "${PRODUCED_OUTPUT}" != "${TMP_OUTPUT}" ]]; then
  preserve_invalid "${PRODUCED_OUTPUT}" "stale tagged temporary output"
fi

if ! edmFileUtil "${INPUT_ABS}" >/dev/null 2>&1; then
  echo "[ERROR] Input is not a valid EDM ROOT file: ${INPUT_ABS}" >&2
  exit 4
fi

status=0
cmsRun "${CFG}" \
  inputFiles="file:${INPUT_ABS}" \
  outputFile="${TMP_OUTPUT}" \
  maxEvents="${MAX_EVENTS}" || status=$?
if [[ "${status}" -ne 0 ]]; then
  preserve_invalid "${TMP_OUTPUT}" "cmsRun failed with status ${status}"
  if [[ "${PRODUCED_OUTPUT}" != "${TMP_OUTPUT}" ]]; then
    preserve_invalid "${PRODUCED_OUTPUT}" "cmsRun failed with status ${status}"
  fi
  exit "${status}"
fi
if ! valid_analysis_file "${PRODUCED_OUTPUT}"; then
  preserve_invalid "${PRODUCED_OUTPUT}" "analyzer output is invalid"
  exit 5
fi
if valid_analysis_file "${OUTPUT_ABS}"; then
  preserve_invalid "${PRODUCED_OUTPUT}" "another process created the final output"
  echo "[SKIP] Another process completed: ${OUTPUT_ABS}"
  exit 0
fi
preserve_invalid "${OUTPUT_ABS}" "final path appeared but is invalid"
mv "${PRODUCED_OUTPUT}" "${OUTPUT_ABS}"
echo "[DONE] ${OUTPUT_ABS}"
