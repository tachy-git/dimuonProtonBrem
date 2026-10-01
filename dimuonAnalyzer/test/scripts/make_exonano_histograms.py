#!/usr/bin/env python3
"""Create dimuon resolution histograms directly from an EXO NanoAOD Events tree."""

import argparse
import math
import os
import sys


TREE_PATH = "Events"
MATCH_DR_MAX = 0.3
MUON_MASS_GEV = 0.1056583755
PROGRESS_EVERY = 100000


def parse_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_root", help="input EXONANOAODSIM ROOT file")
    parser.add_argument("output_root", help="output histogram ROOT file")
    parser.add_argument("--max-events", type=int, default=-1, help="events to process; -1 means all")
    args = parser.parse_args()
    if args.max_events == 0 or args.max_events < -1:
        parser.error("--max-events must be -1 or a positive integer")
    return args


def get_root():
    import ROOT

    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kError
    ROOT.TH1.AddDirectory(False)
    return ROOT


def values(entry, branch, cast=float):
    return [cast(value) for value in getattr(entry, branch)]


def branch_names(tree):
    return {branch.GetName() for branch in tree.GetListOfBranches()}


def validate_tree(tree):
    if not tree or not tree.InheritsFrom("TTree"):
        raise RuntimeError(f"Could not find TTree: {TREE_PATH}")
    required = {"genWeight", "GenPart_pt", "GenPart_eta", "GenPart_phi", "GenPart_pdgId",
                "GenPart_status", "GenPart_statusFlags"}
    for prefix in ("Muon", "DSAMuon"):
        required.update(f"{prefix}_{name}" for name in
                        ("pt", "ptErr", "eta", "phi", "charge", "dxyPVTraj", "dxyPVTrajErr"))
    for prefix in ("PatMuonVertex", "PatDSAMuonVertex", "DSAMuonVertex"):
        required.update(f"{prefix}_{name}" for name in
                        ("isValid", "originalMuonIdx1", "originalMuonIdx2",
                         "isDSAMuon1", "isDSAMuon2", "refittedTrackIdx1", "refittedTrackIdx2"))
        refit = f"{prefix}RefittedTracks"
        required.update(f"{refit}_{name}" for name in
                        ("pt", "px", "py", "pz", "originalMuonIdx", "isDSAMuon"))
    missing = sorted(required - branch_names(tree))
    if missing:
        raise RuntimeError("Missing required EXONano branch(es): " + ", ".join(missing))


def delta_r(eta1, phi1, eta2, phi2):
    dphi = math.remainder(phi1 - phi2, 2.0 * math.pi)
    return math.hypot(eta1 - eta2, dphi)


def gen_muons(entry):
    pts = values(entry, "GenPart_pt")
    etas = values(entry, "GenPart_eta")
    phis = values(entry, "GenPart_phi")
    pdgids = values(entry, "GenPart_pdgId", int)
    statuses = values(entry, "GenPart_status", int)
    flags = values(entry, "GenPart_statusFlags", int)
    records = []
    for index, (pt, eta, phi, pdgid, status, flags_value) in enumerate(
        zip(pts, etas, phis, pdgids, statuses, flags)
    ):
        if abs(pdgid) != 13 or status != 1 or not (flags_value & (1 << 13)):
            continue
        if pt <= 0.0 or not all(map(math.isfinite, (pt, eta, phi))):
            continue
        records.append({"index": index, "pt": pt, "eta": eta, "phi": phi,
                        "charge": -1 if pdgid == 13 else 1})
    return records


def reco_muons(entry, prefix):
    fields = {
        name: values(entry, f"{prefix}_{name}", int if name == "charge" else float)
        for name in ("pt", "ptErr", "eta", "phi", "charge", "dxyPVTraj", "dxyPVTrajErr")
    }
    records = []
    for index, data in enumerate(zip(*(fields[name] for name in fields))):
        pt, pt_error, eta, phi, charge, dxy, dxy_error = data
        if pt <= 0.0 or charge == 0 or not all(map(math.isfinite, (pt, eta, phi))):
            continue
        records.append({"index": index, "pt": pt, "pt_error": pt_error,
                        "eta": eta, "phi": phi, "charge": charge,
                        "dxy": dxy, "dxy_error": dxy_error})
    return records


def match_gen_to_reco(gens, recos):
    candidates = []
    for gen_pos, gen in enumerate(gens):
        for reco_pos, reco in enumerate(recos):
            if gen["charge"] != reco["charge"]:
                continue
            dr = delta_r(gen["eta"], gen["phi"], reco["eta"], reco["phi"])
            if math.isfinite(dr) and dr < MATCH_DR_MAX:
                candidates.append((dr, gen_pos, reco_pos))
    matches, used_gen, used_reco = [], set(), set()
    for dr, gen_pos, reco_pos in sorted(candidates):
        if gen_pos in used_gen or reco_pos in used_reco:
            continue
        used_gen.add(gen_pos)
        used_reco.add(reco_pos)
        matches.append({"gen": gens[gen_pos], "reco": recos[reco_pos], "dr": dr})
    selected = []
    for position, match in enumerate(matches):
        if any(position != other_position and match["gen"]["charge"] * other["gen"]["charge"] < 0
               for other_position, other in enumerate(matches)):
            selected.append(match)
    return selected


def make_track_histograms(ROOT, label):
    title = label.replace("Muon", " muon")
    specs = {
        "pt": (100, 0.0, 50.0), "genPt": (100, 0.0, 50.0),
        "ptError": (60, 0.0, 3.0), "ptOverGenPt": (400, 0.0, 2.0),
        "relativePtError": (100, 0.0, 1.0), "ptPull": (500, -10.0, 10.0),
        "absDxyPVTraj": (500, 0.0, 50.0), "dxyPVTrajError": (1000, 0.0, 10.0),
        "relativeDxyPVTrajError": (500, 0.0, 50.0), "matchDR": (100, 0.0, MATCH_DR_MAX),
    }
    hist = {name: ROOT.TH1F(f"h_{name}", f"{title} {name};{name};Weighted muons", *bins)
            for name, bins in specs.items()}
    hist["pullVsGenPt"] = ROOT.TH2F("h_pullVsGenPt", f"{title} pull vs gen pT;gen pT [GeV];pull",
                                            100, 0.0, 50.0, 500, -10.0, 10.0)
    hist["pullVsAbsEta"] = ROOT.TH2F("h_pullVsAbsEta", f"{title} pull vs |eta|;|eta|;pull",
                                             60, 0.0, 3.0, 500, -10.0, 10.0)
    for item in hist.values():
        item.SetDirectory(0)
        item.Sumw2()
    return hist


def make_vertex_histograms(ROOT, label):
    hist = {
        "mass": ROOT.TH1F("h_vertexFit_mass", f"{label} refitted mass;m_{{#mu#mu}} [GeV];Weighted vertices",
                          500, 0.0, 5.0),
        "refitPt": ROOT.TH1F("h_vertexFit_refitMuon_pt", f"{label} refitted muon pT;pT [GeV];Weighted muons",
                             100, 0.0, 50.0),
        "refitGenPt": ROOT.TH1F("h_vertexFit_refitMuon_genPt", f"{label} matched gen pT;pT [GeV];Weighted muons",
                                100, 0.0, 50.0),
        "refitPtOverGenPt": ROOT.TH1F("h_vertexFit_refitMuon_ptOverGenPt",
                                      f"{label} refitted/gen pT;refitted/gen pT;Weighted muons",
                                      400, 0.0, 2.0),
    }
    for item in hist.values():
        item.SetDirectory(0)
        item.Sumw2()
    return hist


def fill_track(hist, match, weight):
    reco, gen = match["reco"], match["gen"]
    pt, gen_pt = reco["pt"], gen["pt"]
    hist["pt"].Fill(pt, weight)
    hist["genPt"].Fill(gen_pt, weight)
    hist["ptOverGenPt"].Fill(pt / gen_pt, weight)
    hist["matchDR"].Fill(match["dr"], weight)
    dxy, dxy_error = reco["dxy"], reco["dxy_error"]
    if math.isfinite(dxy):
        hist["absDxyPVTraj"].Fill(abs(dxy), weight)
        if math.isfinite(dxy_error) and dxy_error > 0.0:
            hist["dxyPVTrajError"].Fill(dxy_error, weight)
            if dxy != 0.0:
                hist["relativeDxyPVTrajError"].Fill(dxy_error / abs(dxy), weight)
    pt_error = reco["pt_error"]
    if not math.isfinite(pt_error) or pt_error <= 0.0:
        return
    pull = (pt - gen_pt) / pt_error
    hist["ptError"].Fill(pt_error, weight)
    hist["relativePtError"].Fill(pt_error / pt, weight)
    hist["ptPull"].Fill(pull, weight)
    hist["pullVsGenPt"].Fill(gen_pt, pull, weight)
    hist["pullVsAbsEta"].Fill(abs(gen["eta"]), pull, weight)


def refit_mass(px1, py1, pz1, px2, py2, pz2):
    e1 = math.sqrt(px1 * px1 + py1 * py1 + pz1 * pz1 + MUON_MASS_GEV ** 2)
    e2 = math.sqrt(px2 * px2 + py2 * py2 + pz2 * pz2 + MUON_MASS_GEV ** 2)
    mass2 = (e1 + e2) ** 2 - (px1 + px2) ** 2 - (py1 + py2) ** 2 - (pz1 + pz2) ** 2
    return math.sqrt(max(0.0, mass2))


def fill_vertices(entry, prefix, hist, pat_matches, dsa_matches, weight, counters):
    valid = values(entry, f"{prefix}_isValid", int)
    original1 = values(entry, f"{prefix}_originalMuonIdx1", int)
    original2 = values(entry, f"{prefix}_originalMuonIdx2", int)
    is_dsa1 = values(entry, f"{prefix}_isDSAMuon1", int)
    is_dsa2 = values(entry, f"{prefix}_isDSAMuon2", int)
    refit1 = values(entry, f"{prefix}_refittedTrackIdx1", int)
    refit2 = values(entry, f"{prefix}_refittedTrackIdx2", int)
    refit_prefix = f"{prefix}RefittedTracks"
    px = values(entry, f"{refit_prefix}_px")
    py = values(entry, f"{refit_prefix}_py")
    pz = values(entry, f"{refit_prefix}_pz")
    pt = values(entry, f"{refit_prefix}_pt")
    pat_by_index = {item["reco"]["index"]: item for item in pat_matches}
    dsa_by_index = {item["reco"]["index"]: item for item in dsa_matches}
    columns = zip(valid, original1, original2, is_dsa1, is_dsa2, refit1, refit2)
    for is_valid, index1, index2, dsa1, dsa2, track1, track2 in columns:
        if not is_valid:
            continue
        lookup1 = dsa_by_index if dsa1 else pat_by_index
        lookup2 = dsa_by_index if dsa2 else pat_by_index
        match1, match2 = lookup1.get(index1), lookup2.get(index2)
        if match1 is None or match2 is None:
            continue
        if match1["gen"]["index"] == match2["gen"]["index"] or match1["gen"]["charge"] * match2["gen"]["charge"] >= 0:
            continue
        if min(track1, track2) < 0 or max(track1, track2) >= min(len(px), len(py), len(pz), len(pt)):
            counters["bad_refit_index"] += 1
            continue
        mass = refit_mass(px[track1], py[track1], pz[track1], px[track2], py[track2], pz[track2])
        if math.isfinite(mass):
            hist["mass"].Fill(mass, weight)
        for track_index, match in ((track1, match1), (track2, match2)):
            refit_pt, gen_pt = pt[track_index], match["gen"]["pt"]
            if math.isfinite(refit_pt) and refit_pt > 0.0 and gen_pt > 0.0:
                hist["refitPt"].Fill(refit_pt, weight)
                hist["refitGenPt"].Fill(gen_pt, weight)
                hist["refitPtOverGenPt"].Fill(refit_pt / gen_pt, weight)
        counters["matched_vertices"] += 1


def process_file(input_path, output_path, max_events):
    ROOT = get_root()
    root_file = ROOT.TFile.Open(input_path)
    if not root_file or root_file.IsZombie() or root_file.TestBit(ROOT.TFile.kRecovered):
        raise RuntimeError(f"Invalid input ROOT file: {input_path}")
    try:
        tree = root_file.Get(TREE_PATH)
        validate_tree(tree)
        track_hist = {prefix: make_track_histograms(ROOT, prefix) for prefix in ("Muon", "DSAMuon")}
        vertex_hist = {prefix: make_vertex_histograms(ROOT, prefix) for prefix in
                       ("PatMuonVertex", "PatDSAMuonVertex", "DSAMuonVertex")}
        counters = {"events": 0, "matched_muons": 0, "matched_vertices": 0, "bad_refit_index": 0}
        event_limit = tree.GetEntries() if max_events < 0 else min(tree.GetEntries(), max_events)
        print(f"[START] file={os.path.basename(input_path)} events={event_limit}/{tree.GetEntries()}", flush=True)
        for entry in tree:
            if counters["events"] >= event_limit:
                break
            counters["events"] += 1
            weight = float(entry.genWeight)
            if not math.isfinite(weight):
                weight = 1.0
            gens = gen_muons(entry)
            pat_matches = match_gen_to_reco(gens, reco_muons(entry, "Muon"))
            dsa_matches = match_gen_to_reco(gens, reco_muons(entry, "DSAMuon"))
            for prefix, matches in (("Muon", pat_matches), ("DSAMuon", dsa_matches)):
                for match in matches:
                    fill_track(track_hist[prefix], match, weight)
                counters["matched_muons"] += len(matches)
            for prefix in vertex_hist:
                fill_vertices(entry, prefix, vertex_hist[prefix], pat_matches, dsa_matches, weight, counters)
            if PROGRESS_EVERY and counters["events"] % PROGRESS_EVERY == 0:
                print(f"[PROGRESS] events={counters['events']}/{event_limit}", flush=True)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        temporary = f"{output_path}.tmp.root"
        output = ROOT.TFile.Open(temporary, "RECREATE")
        if not output or output.IsZombie():
            raise RuntimeError(f"Could not create output ROOT file: {temporary}")
        try:
            for prefix, histograms in {**track_hist, **vertex_hist}.items():
                directory = output.mkdir(prefix)
                directory.cd()
                for histogram in histograms.values():
                    histogram.Write()
            output.Write()
        finally:
            output.Close()
        os.replace(temporary, output_path)
        print("[DONE] " + " ".join(f"{key}={value}" for key, value in counters.items()), flush=True)
    finally:
        root_file.Close()


def main():
    args = parse_cli()
    input_path, output_path = map(os.path.abspath, (args.input_root, args.output_root))
    if not os.path.isfile(input_path):
        print(f"[ERROR] Input does not exist: {input_path}", file=sys.stderr)
        return 1
    if input_path == output_path:
        print("[ERROR] Input and output paths must differ", file=sys.stderr)
        return 1
    process_file(input_path, output_path, args.max_events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
