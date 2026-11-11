#!/usr/bin/env bash
set -Eeuo pipefail
trap 'status=$?; echo "[ERROR] line ${LINENO}: ${BASH_COMMAND} (exit ${status})" >&2; exit "${status}"' ERR

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
ANALYZER="${SCRIPT_DIR}/make_dimuon_histograms.py"

to_absolute() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    readlink -m "${PROJECT_DIR}/${path}"
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
valid = bool(
    root_file
    and not root_file.IsZombie()
    and not root_file.TestBit(ROOT.TFile.kRecovered)
    and root_file.GetListOfKeys().GetSize() > 0
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

# Always recompute. Do not remove the input if paths were accidentally reused.
if [[ "${INPUT_ABS}" -ef "${OUTPUT_ABS}" || "${INPUT_ABS}" == "${OUTPUT_ABS}" ]]; then
  echo "[ERROR] Input and output must be different files" >&2
  exit 3
fi
cleanup() {
  rm -f -- "${TMP_OUTPUT}" "${INNER_TMP}"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
rm -f -- "${OUTPUT_ABS}"
cleanup

status=0
python3 "${ANALYZER}" "${INPUT_ABS}" "${TMP_OUTPUT}" \
  --max-events "${MAX_EVENTS}" || status=$?
if [[ "${status}" -ne 0 ]]; then
  echo "[ERROR] Histogram analysis failed with status ${status}" >&2
  exit "${status}"
fi
if ! valid_histo_file "${TMP_OUTPUT}"; then
  echo "[ERROR] Histogram output is not a readable, nonempty ROOT file" >&2
  exit 5
fi
mv -f -- "${TMP_OUTPUT}" "${OUTPUT_ABS}"
echo "[DONE] ${OUTPUT_ABS}"
