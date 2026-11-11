#!/usr/bin/env python3
import argparse
from itertools import combinations
import math
import os
import sys

TREE_PATH = "dimuonAnalyzer/tree"
PROGRESS_EVERY = 100000
MUON_PREFIX = "muon"
BEST_VERTEX_PREFIX = "muonVertex"
STA_VERTEX_PREFIX = "muonStaVertex"
DISPLACED_MUON_PREFIX = "disMuon"
DISPLACED_STA_VERTEX_PREFIX = "disMuonStaVertex"
DISPLACED_TRACK_PREFIX = "disStaTrack"
DISPLACED_TRACK_VERTEX_PREFIX = "disStaTrackVertex"
KINVALID = -900.0
MUON_MASS_GEV = 0.1056583745
MASS_BINNING = (500, 0.0, 5.0)
GEN_RECO_MASS_BINNING = (30, 0.2, 0.5, 500, 0.0, 5.0)
LXY_BINNING = (300, 0.0, 300.0)
LXY_ERROR_BINNING = (101, 0.0, 101.0)
PT_BINNING = (100, 0.0, 50.0)
PT_ERROR_BINNING = (60, 0.0, 3.0)
PT_RATIO_BINNING = (400, 0.0, 2.0)
DR_BINNING = (100, 0.0, 0.5)
MATCHED_GEN_DR_BINNING = (30, 0.0, 0.3)
GEN_MATCH_DR_MAX = 0.1
GEN_MATCH_REL_PT_MAX = 0.10
DPHI_BINNING = (128, 0.0, math.pi)
NORM_CHI2_BINNING = (200, 0.0, 100.0)
VERTEX_PROB_BINNING = (100, 0.0, 1.0)
COUNT_BINNING = (101, -0.5, 100.5)
VERTEX_PROB_CUT = 0.001
MASS_REGIONS = ("massLt0p23", "massGt0p27")
LXY_MM_TO_CM = 0.1
LXY_REL_ERROR_BINNING = (200, 0.0, 10.0)
LXY_RATIO_2D_BINNING = (300, 0.0, 300.0, 200, 0.0, 2.0)
HISTOGRAM_DIRECTORIES = {
    "gen": "GEN",
    "best": "slimmedMuon",
    "standalone": "slimmedMuon",
    "disStandalone": "displacedSlimmedMuon",
    "disTrack": "displacedStandaloneMuon",
}


def parse_cli():
    parser = argparse.ArgumentParser(
        description="Create resolution histograms from one dimuonAnalyzer ROOT file."
    )
    parser.add_argument("input_root", help="input dimuonAnalyzer ROOT file")
    parser.add_argument("output_root", help="output histogram ROOT file")
    parser.add_argument("--max-events", type=int, default=-1,
                        help="maximum entries to process; -1 means all")
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


def vector_to_floats(values):
    return [float(value) for value in values]


def vector_to_ints(values):
    return [int(value) for value in values]


def is_valid_number(value):
    return math.isfinite(value) and value > KINVALID


def valid_track(pt, eta, phi, charge):
    return (is_valid_number(pt) and pt > 0.0 and is_valid_number(eta)
            and is_valid_number(phi) and charge != 0)


def delta_r(eta1, phi1, eta2, phi2):
    delta_phi = math.remainder(phi1 - phi2, 2.0 * math.pi)
    return math.hypot(eta1 - eta2, delta_phi)


def dimuon_pt(pt1, phi1, pt2, phi2):
    if not (is_valid_number(pt1) and pt1 > 0.0
            and is_valid_number(pt2) and pt2 > 0.0
            and is_valid_number(phi1) and is_valid_number(phi2)):
        return
    pt = math.hypot(pt1 * math.cos(phi1) + pt2 * math.cos(phi2),
                    pt1 * math.sin(phi1) + pt2 * math.sin(phi2))
    if math.isfinite(pt):
        return pt


def fill_dimuon_pt(histogram, pt1, phi1, pt2, phi2, weight):
    pt = dimuon_pt(pt1, phi1, pt2, phi2)
    if pt is not None:
        histogram.Fill(pt, weight)


def fill_dimuon_dr_vs_pt(histogram, pt1, eta1, phi1, pt2, eta2, phi2, weight):
    pt = dimuon_pt(pt1, phi1, pt2, phi2)
    if pt is None or not (is_valid_number(eta1) and is_valid_number(eta2)):
        return
    dr = delta_r(eta1, phi1, eta2, phi2)
    if math.isfinite(dr):
        histogram.Fill(pt, dr, weight)


def fill_pair_pt(histogram, tracks, weight, dr_vs_pt=None):
    for first, second in combinations(tracks, 2):
        if first["charge"] * second["charge"] < 0:
            fill_dimuon_pt(histogram, first["pt"], first["phi"],
                           second["pt"], second["phi"], weight)
            if dr_vs_pt is not None:
                fill_dimuon_dr_vs_pt(
                    dr_vs_pt, first["pt"], first["eta"], first["phi"],
                    second["pt"], second["eta"], second["phi"], weight)


def fill_pair_delta_r(histogram, tracks, weight):
    for first, second in combinations(tracks, 2):
        if first["charge"] * second["charge"] < 0:
            histogram.Fill(delta_r(first["eta"], first["phi"],
                                   second["eta"], second["phi"]), weight)


def fill_gen_dimuon_mass(ROOT, histogram, gen_muons, weight):
    vectors = [ROOT.Math.PtEtaPhiMVector(muon["pt"], muon["eta"],
                                       muon["phi"], MUON_MASS_GEV)
               for muon in gen_muons]
    for first, second in combinations(range(len(gen_muons)), 2):
        if gen_muons[first]["charge"] * gen_muons[second]["charge"] < 0:
            mass = (vectors[first] + vectors[second]).M()
            if math.isfinite(mass) and mass >= 0.0:
                histogram.Fill(mass, weight)


def fill_gen_vs_displaced_mass(ROOT, histogram, entry, gen_muons, weight):
    """One fill per valid OS displaced slimmed-muon standalone vertex when the event has one gen OS pair."""
    if len(gen_muons) != 2 or gen_muons[0]["charge"] * gen_muons[1]["charge"] >= 0:
        return
    vectors = [ROOT.Math.PtEtaPhiMVector(muon["pt"], muon["eta"],
                                       muon["phi"], MUON_MASS_GEV)
               for muon in gen_muons]
    gen_mass = (vectors[0] + vectors[1]).M()
    if not math.isfinite(gen_mass) or gen_mass < 0.0:
        return
    charges = vector_to_ints(entry.disMuon_standAloneMuon_charge)
    for index, arrays in valid_vertices(entry, DISPLACED_STA_VERTEX_PREFIX):
        first, second = arrays["mu1Index"][index], arrays["mu2Index"][index]
        if not (0 <= first < len(charges) and 0 <= second < len(charges)):
            continue
        if charges[first] * charges[second] >= 0:
            continue
        reco_mass = arrays["mass"][index]
        if math.isfinite(reco_mass) and reco_mass >= 0.0:
            histogram.Fill(gen_mass, reco_mass, weight)


def make_records(entry, prefix, has_flag=None):
    pts = vector_to_floats(getattr(entry, f"{prefix}_pt"))
    errors = vector_to_floats(getattr(entry, f"{prefix}_ptError"))
    etas = vector_to_floats(getattr(entry, f"{prefix}_eta"))
    phis = vector_to_floats(getattr(entry, f"{prefix}_phi"))
    charges = vector_to_ints(getattr(entry, f"{prefix}_charge"))
    flags = vector_to_ints(getattr(entry, has_flag)) if has_flag else None
    size = min(len(pts), len(errors), len(etas), len(phis), len(charges))
    if flags is not None:
        size = min(size, len(flags))
    records = []
    for index in range(size):
        if flags is not None and flags[index] != 1:
            continue
        if not valid_track(pts[index], etas[index], phis[index], charges[index]):
            continue
        records.append({"index": index, "pt": pts[index], "pt_error": errors[index],
                        "eta": etas[index], "phi": phis[index],
                        "charge": charges[index]})
    return records


def make_gen_records(entry):
    pts = vector_to_floats(entry.genMuon_pt)
    etas = vector_to_floats(entry.genMuon_eta)
    phis = vector_to_floats(entry.genMuon_phi)
    charges = vector_to_ints(entry.genMuon_charge)
    records = []
    for index in range(min(len(pts), len(etas), len(phis), len(charges))):
        if valid_track(pts[index], etas[index], phis[index], charges[index]):
            records.append({"index": index, "pt": pts[index], "eta": etas[index],
                            "phi": phis[index], "charge": charges[index]})
    return records


def make_best_track_records(entry, prefix=MUON_PREFIX):
    return make_records(entry, prefix)


def make_standalone_track_records(entry, prefix=MUON_PREFIX):
    return make_records(entry, f"{prefix}_standAloneMuon",
                        f"{prefix}_hasStandAloneMuon")


def unique_gen_by_charge(gen_muons):
    candidates = {}
    for gen_muon in gen_muons:
        candidates.setdefault(gen_muon["charge"], []).append(gen_muon)
    return {charge: muons[0] for charge, muons in candidates.items()
            if len(muons) == 1}


def fill_matched_gen_count_vs_dr(histogram, gen_muons, tracks, weight,
                                 require_pt_match=True, require_dr_match=True,
                                 dr_max=GEN_MATCH_DR_MAX,
                                 rel_pt_max=GEN_MATCH_REL_PT_MAX):
    """Count each gen muon once, independently of duplicate reco tracks."""
    if len(gen_muons) != 2 or gen_muons[0]["charge"] * gen_muons[1]["charge"] >= 0:
        return
    matched = sum(
        any(track["charge"] == gen["charge"]
            and (not require_dr_match
                 or delta_r(track["eta"], track["phi"], gen["eta"], gen["phi"])
                 < dr_max)
            and (not require_pt_match
                 or abs(track["pt"] - gen["pt"]) / gen["pt"] < rel_pt_max)
            for track in tracks)
        for gen in gen_muons)
    first, second = gen_muons
    histogram.Fill(delta_r(first["eta"], first["phi"],
                           second["eta"], second["phi"]), matched, weight)


def book(ROOT, name, title, binning):
    return ROOT.TH1F(name, title, *binning)


def book_track_histograms(ROOT, histograms, key, obj, title):
    histograms[f"{key}DR"] = book(
        ROOT, f"h_dR_{obj}",
        f"{title} opposite-charge pair #DeltaR;#DeltaR;Weighted pairs", DR_BINNING)
    definitions = (
        ("Pt", "pt", f"{title} p_{{T}};p_{{T}} [GeV];Weighted tracks", PT_BINNING),
        ("PtError", "ptError", f"{title} #sigma(p_{{T}});#sigma(p_{{T}}) [GeV];Weighted tracks", PT_ERROR_BINNING),
        ("PtOverGenPt", "ptOverGenPt", f"{title} p_{{T}}/gen p_{{T}} (charge matched);p_{{T}}/p_{{T}}^{{gen}};Weighted tracks", PT_RATIO_BINNING),
    )
    for suffix, variable, hist_title, binning in definitions:
        histograms[f"{key}{suffix}"] = book(
            ROOT, f"h_{variable}_{obj}", hist_title, binning)


def book_fit_histograms(ROOT, histograms, key, obj, title):
    histograms[f"{key}FitDR"] = book(
        ROOT, f"h_dR_refit_{obj}",
        f"{title} refitted dimuon #DeltaR;#DeltaR;Weighted vertices", DR_BINNING)
    histograms[f"{key}FitMass"] = book(
        ROOT, f"h_mass_{obj}",
        f"{title} mass after vertex refit;m_{{#mu#mu}}^{{refit}} [GeV];Weighted vertices",
        MASS_BINNING)
    histograms[f"{key}FitLxy"] = book(
        ROOT, f"h_lxy_{obj}",
        f"{title} transverse decay length;L_{{xy}} [cm];Weighted vertices",
        LXY_BINNING)
    histograms[f"{key}FitLxyError"] = book(
        ROOT, f"h_lxyError_{obj}",
        f"{title} transverse decay-length uncertainty;#sigma(L_{{xy}}) [cm];Weighted vertices",
        LXY_ERROR_BINNING)
    histograms[f"{key}FitLxyRelError"] = book(
        ROOT, f"h_lxyErrorOverLxy_{obj}",
        f"{title} relative transverse decay-length uncertainty;#sigma(L_{{xy}})/L_{{xy}};Weighted vertices",
        LXY_REL_ERROR_BINNING)
    if key != "disStandalone":
        histograms[f"{key}FitMassLxyRelErrorLt6"] = book(
            ROOT, f"h_mass_lxyErrorOverLxyLt6_{obj}",
            f"{title} mass for #sigma(L_{{xy}})/L_{{xy}} < 6;m_{{#mu#mu}}^{{refit}} [GeV];Weighted vertices",
            MASS_BINNING)
        histograms[f"{key}FitMassLxyWindow"] = book(
            ROOT, f"h_mass_sampleLxyWindow_{obj}",
            f"{title} mass in sample L_{{xy}} window;m_{{#mu#mu}}^{{refit}} [GeV];Weighted vertices",
            MASS_BINNING)
        histograms[f"{key}FitLxyVsRefitPtOverGenPt"] = ROOT.TH2F(
            f"h_lxyVsRefitPtOverGenPt_{obj}",
            f"{title} L_{{xy}} vs refitted/gen p_{{T}};L_{{xy}} [cm];p_{{T}}^{{refit}}/p_{{T}}^{{gen}}",
            *LXY_RATIO_2D_BINNING)
    refit_obj = f"refitMuon_{obj}"
    definitions = (
        ("RefitPt", "pt", f"{title} refitted-track p_{{T}};p_{{T}}^{{refit}} [GeV];Weighted tracks", PT_BINNING),
        ("RefitPtError", "ptError", f"{title} refitted-track #sigma(p_{{T}});#sigma(p_{{T}}^{{refit}}) [GeV];Weighted tracks", PT_ERROR_BINNING),
        ("RefitPtOverGenPt", "ptOverGenPt", f"{title} refitted-track p_{{T}}/gen p_{{T}} (charge matched);p_{{T}}^{{refit}}/p_{{T}}^{{gen}};Weighted tracks", PT_RATIO_BINNING),
    )
    for suffix, variable, hist_title, binning in definitions:
        histograms[f"{key}{suffix}"] = book(
            ROOT, f"h_{variable}_{refit_obj}", hist_title, binning)


def book_mass_region_histograms(ROOT, histograms):
    obj = "displacedMuonStandAloneTrackFit"
    for region in MASS_REGIONS:
        key = f"disStandalone_{region}_"
        label = "m < 0.23 GeV" if region == "massLt0p23" else "m > 0.27 GeV"
        definitions = (
            ("dPhi", "Before refit;|#Delta#phi|;Weighted vertices", DPHI_BINNING),
            ("dPhi_refit", "After refit;|#Delta#phi^{refit}|;Weighted vertices", DPHI_BINNING),
            ("dPhi_beforeVsRefit", "Before vs after refit;|#Delta#phi|;|#Delta#phi^{refit}|", DPHI_BINNING * 2),
            ("dPhi_genVsRefit", "Gen vs refit;|#Delta#phi^{gen}|;|#Delta#phi^{refit}|", DPHI_BINNING * 2),
            ("dR_genVsRefit", "Gen vs refit;#DeltaR^{gen};#DeltaR^{refit}", DR_BINNING * 2),
            ("lxy", "Decay length;L_{xy} [cm];Weighted vertices", LXY_BINNING),
            ("lxyError", "Decay-length uncertainty;#sigma(L_{xy}) [cm];Weighted vertices", LXY_ERROR_BINNING),
            ("normChi2", "Vertex normalized chi2;#chi^{2}/ndof;Weighted vertices", NORM_CHI2_BINNING),
            ("vtxProb", "Vertex probability;Vertex probability;Weighted vertices", VERTEX_PROB_BINNING),
        )
        for variable, title, binning in definitions:
            hist_type = ROOT.TH2F if len(binning) == 6 else ROOT.TH1F
            histograms[key + variable] = hist_type(
                f"h_{variable}_{obj}_{region}", f"{label}: {title}", *binning)


def valid_vertex_probability(value):
    return math.isfinite(value) and 0.0 <= value <= 1.0


def passes_vertex_probability_cut(value):
    return valid_vertex_probability(value) and value > VERTEX_PROB_CUT


def fill_mass_region_histograms(histograms, values, tracks_by_index, gen_by_charge, weight):
    index, arrays = values
    mass = arrays["mass"][index]
    if not is_valid_number(mass) or mass < 0.0:
        return
    region = "massLt0p23" if mass < 0.23 else "massGt0p27" if mass > 0.27 else None
    if region is None:
        return
    tracks = [tracks_by_index.get(arrays[field][index])
              for field in ("mu1Index", "mu2Index")]
    if any(track is None for track in tracks) or tracks[0]["charge"] * tracks[1]["charge"] >= 0:
        return
    key = f"disStandalone_{region}_"
    probability = arrays["vtxProb"][index]
    if valid_vertex_probability(probability):
        # ROOT puts the upper edge in overflow; keep probability=1 in the last bin.
        histograms[key + "vtxProb"].Fill(min(probability, math.nextafter(1.0, 0.0)), weight)
    before = abs(math.remainder(tracks[0]["phi"] - tracks[1]["phi"], 2.0 * math.pi))
    histograms[key + "dPhi"].Fill(before, weight)
    for field, variable in (("lxy", "lxy"), ("lxyErr", "lxyError"), ("normChi2", "normChi2")):
        value = arrays[field][index]
        if is_valid_number(value) and value >= 0.0:
            histograms[key + variable].Fill(value, weight)
    phis = [arrays[f"refit_mu{muon}_phi"][index] for muon in (1, 2)]
    if not all(is_valid_number(phi) for phi in phis):
        return
    after = abs(math.remainder(phis[0] - phis[1], 2.0 * math.pi))
    histograms[key + "dPhi_refit"].Fill(after, weight)
    histograms[key + "dPhi_beforeVsRefit"].Fill(before, after, weight)
    gen = [gen_by_charge.get(track["charge"]) for track in tracks]
    if any(muon is None for muon in gen):
        return
    gen_dphi = abs(math.remainder(gen[0]["phi"] - gen[1]["phi"], 2.0 * math.pi))
    histograms[key + "dPhi_genVsRefit"].Fill(gen_dphi, after, weight)
    etas = [arrays[f"refit_mu{muon}_eta"][index] for muon in (1, 2)]
    if all(is_valid_number(eta) for eta in etas):
        histograms[key + "dR_genVsRefit"].Fill(
            delta_r(gen[0]["eta"], gen[0]["phi"], gen[1]["eta"], gen[1]["phi"]),
            delta_r(etas[0], phis[0], etas[1], phis[1]), weight)


def make_histograms(ROOT):
    histograms = {
        "disStandaloneGenVsRecoMass": ROOT.TH2D(
            "h_mass_genVsReco_displacedMuonStandAloneTrackFit",
            "Gen dimuon vs displaced slimmed-muon standalone dimuon mass;"
            "m_{#mu#mu}^{gen} [GeV];m_{#mu#mu}^{refit} [GeV];Weighted vertices",
            *GEN_RECO_MASS_BINNING),
        "genMass": book(ROOT, "h_mass_genDimuon",
                        "generator-level opposite-charge dimuon invariant mass;"
                        "m_{#mu#mu}^{gen} [GeV];Weighted pairs",
                        MASS_BINNING),
        "genPt": book(ROOT, "h_pt_genMuon",
                      "generator-level muon p_{T};p_{T}^{gen} [GeV];Weighted muons",
                      PT_BINNING),
        "genDimuonPt": book(ROOT, "h_pt_genDimuon",
                            "Generator-level opposite-charge dimuon p_{T};"
                            "p_{T}^{#mu#mu} [GeV];Weighted pairs", PT_BINNING),
        "genDimuonDRVsPt": ROOT.TH2F(
            "h_dR_vs_pt_genDimuon",
            "Generator-level opposite-charge dimuon #DeltaR vs p_{T};"
            "p_{T}^{#mu#mu} [GeV];#DeltaR_{#mu#mu};Weighted pairs",
            *PT_BINNING, *DR_BINNING),
        "genDR": book(ROOT, "h_dR_genMuon",
                      "generator-level dimuon #DeltaR;#DeltaR;Weighted events",
                      DR_BINNING)
    }
    categories = (
        ("best", "bestTrack", "slimmed-muon best track", "bestTrackFit", "best-track fit"),
        ("standalone", "standAloneTrack", "slimmed-muon standalone track", "standAloneTrackFit", "standalone-track fit"),
        ("disStandalone", "displacedMuonStandAloneTrack", "displaced-muon standalone track", "displacedMuonStandAloneTrackFit", "displaced-muon standalone-track fit"),
        ("disTrack", "displacedStandAloneTrack", "raw displaced standalone track", "displacedStandAloneTrackFit", "raw displaced standalone-track fit"),
    )
    for key, track_obj, track_title, fit_obj, fit_title in categories:
        book_track_histograms(ROOT, histograms, key, track_obj, track_title)
        book_fit_histograms(ROOT, histograms, key, fit_obj, fit_title)
    obj = "displacedMuonStandAloneTrackFit"
    histograms["disStandaloneDimuonPt"] = book(
        ROOT, "h_pt_dimuon_displacedMuonStandAloneTrack",
        "Displaced standalone opposite-charge dimuon p_{T} before refit;"
        "p_{T}^{#mu#mu} [GeV];Weighted pairs", PT_BINNING)
    histograms["disStandaloneNMatchedGenMuonVsGenDimuonDRChargeOnly"] = ROOT.TH2D(
        "h_nMatchedGenMuon_vs_genDimuonDR_chargeOnly",
        "Displaced slimmed-muon standalone gen matching (same charge only);"
        "#DeltaR_{#mu#mu}^{gen};Number of matched gen muons;Weighted events",
        *MATCHED_GEN_DR_BINNING, 3, -0.5, 2.5)
    histograms["disStandaloneNMatchedGenMuonVsGenDimuonDRPt30Percent"] = ROOT.TH2D(
        "h_nMatchedGenMuon_vs_genDimuonDR_dR0p3_pt30Percent",
        "Displaced slimmed-muon standalone gen matching "
        "(same charge, #DeltaR < 0.3, relative p_{T} difference < 0.30);"
        "#DeltaR_{#mu#mu}^{gen};Number of matched gen muons;Weighted events",
        *MATCHED_GEN_DR_BINNING, 3, -0.5, 2.5)
    histograms["disStandaloneGenRecoDRChargeOnly"] = book(
        ROOT, "h_dR_genReco_displacedMuonStandAloneTrack_chargeOnly",
        "Standalone gen-reco separation (same charge only);"
        "#DeltaR(gen #mu, reco track);Weighted tracks", (500, 0.0, 5.0))
    histograms["disStandalonePtRatioChargeOnly"] = book(
        ROOT, "h_ptRatio_genReco_displacedMuonStandAloneTrack_chargeOnly",
        "Standalone reco/gen transverse momentum (same charge only);"
        "p_{T}^{reco}/p_{T}^{gen};Weighted tracks", (500, 0.0, 5.0))
    histograms["disStandaloneFitDimuonPt"] = book(
        ROOT, f"h_pt_dimuon_{obj}",
        "Displaced standalone opposite-charge dimuon p_{T} after refit;"
        "p_{T}^{#mu#mu,refit} [GeV];Weighted vertices", PT_BINNING)
    histograms["disStandaloneFitDimuonDRVsPt"] = ROOT.TH2F(
        f"h_dR_vs_pt_{obj}",
        "Displaced standalone opposite-charge dimuon #DeltaR vs p_{T} after refit;"
        "p_{T}^{#mu#mu,refit} [GeV];#DeltaR_{#mu#mu}^{refit};Weighted vertices",
        *PT_BINNING, *DR_BINNING)
    histograms["disStandaloneFitMassVtxProbGt0p001"] = book(
        ROOT, f"h_mass_vtxProbGt0p001_{obj}",
        "Displaced standalone mass for vertex probability > 0.001;"
        "m_{#mu#mu}^{refit} [GeV];Weighted vertices", MASS_BINNING)
    for key, name, label in (
        ("NVertex", f"h_nVertex_{obj}", "Valid vertices"),
        ("NVertexVtxProbGt0p001", f"h_nVertex_vtxProbGt0p001_{obj}",
         "Valid vertices with probability > 0.001"),
        ("NRecoMuon", "h_nRecoMuon_displacedMuonStandAloneTrack", "Valid standalone tracks"),
    ):
        histograms[f"disStandalone{key}"] = book(
            ROOT, name, f"{label} per event;Count;Weighted events", COUNT_BINNING)
    book_mass_region_histograms(ROOT, histograms)
    names = [hist.GetName() for hist in histograms.values()]
    if len(names) != len(set(names)):
        raise RuntimeError("Histogram names must be unique")
    for hist in histograms.values():
        hist.SetDirectory(0)
        hist.Sumw2()
    return histograms


def histogram_directory(key):
    matches = [directory for prefix, directory in HISTOGRAM_DIRECTORIES.items()
               if key.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(f"Histogram key has no unique output directory: {key}")
    return matches[0]


def sample_lxy_window(input_path):
    """Return the nominal sample Lxy window in the tree's cm units."""
    basename = os.path.basename(input_path)
    if "Lxy0" in basename:
        return 0.0, 100.0 * LXY_MM_TO_CM
    if "Lxy1800" in basename:
        return 1700.0 * LXY_MM_TO_CM, 1900.0 * LXY_MM_TO_CM
    return None


def validate_tree(tree):
    if not tree or not tree.InheritsFrom("TTree"):
        raise RuntimeError(f"Could not find TTree: {TREE_PATH}")
    required = ["eventWeight", "genMuon_pt", "genMuon_eta", "genMuon_phi",
                "genMuon_charge"]
    required += [f"{MUON_PREFIX}_{field}" for field in
                 ("pt", "ptError", "eta", "phi", "charge")]
    for prefix in (MUON_PREFIX, DISPLACED_MUON_PREFIX):
        required.append(f"{prefix}_hasStandAloneMuon")
        required += [f"{prefix}_standAloneMuon_{field}" for field in
                     ("pt", "ptError", "eta", "phi", "charge")]
    required += [f"{DISPLACED_TRACK_PREFIX}_{field}" for field in
                 ("pt", "ptError", "eta", "phi", "charge")]
    for prefix in (BEST_VERTEX_PREFIX, STA_VERTEX_PREFIX,
                   DISPLACED_STA_VERTEX_PREFIX, DISPLACED_TRACK_VERTEX_PREFIX):
        required += [f"{prefix}_{field}" for field in
                     ("mu1Index", "mu2Index", "isValid", "mass", "lxy", "lxyErr",
                      "refit_mu1_pt", "refit_mu1_ptError",
                      "refit_mu1_eta", "refit_mu1_phi",
                      "refit_mu2_pt", "refit_mu2_ptError",
                      "refit_mu2_eta", "refit_mu2_phi")]
    required += [f"{DISPLACED_STA_VERTEX_PREFIX}_{field}"
                 for field in ("normChi2", "vtxProb")]
    missing = [branch for branch in required if not tree.GetBranch(branch)]
    if missing:
        raise RuntimeError("Missing required branch(es): " + ", ".join(missing)
                           + ". Regenerate the ntuples with the current dimuonAnalyzer.cc.")


def fill_track_histograms(histograms, prefix, track, gen_by_charge, weight, counters):
    pt, error = track["pt"], track["pt_error"]
    histograms[f"{prefix}Pt"].Fill(pt, weight)
    if math.isfinite(error) and error > 0.0:
        histograms[f"{prefix}PtError"].Fill(error, weight)
    gen_muon = gen_by_charge.get(track["charge"])
    if gen_muon is None:
        counters["unmatched_track_ratios"] += 1
    else:
        histograms[f"{prefix}PtOverGenPt"].Fill(pt / gen_muon["pt"], weight)
        if prefix == "disStandalone":
            histograms["disStandaloneGenRecoDRChargeOnly"].Fill(
                delta_r(track["eta"], track["phi"],
                        gen_muon["eta"], gen_muon["phi"]), weight)
            histograms["disStandalonePtRatioChargeOnly"].Fill(
                pt / gen_muon["pt"], weight)
        counters["matched_track_ratios"] += 1


def vertex_arrays(entry, prefix):
    fields = ("mu1Index", "mu2Index", "isValid", "mass", "lxy", "lxyErr",
              "refit_mu1_pt", "refit_mu1_ptError", "refit_mu1_eta", "refit_mu1_phi",
              "refit_mu2_pt", "refit_mu2_ptError", "refit_mu2_eta", "refit_mu2_phi")
    if prefix == DISPLACED_STA_VERTEX_PREFIX:
        fields += ("normChi2", "vtxProb")
    arrays = {}
    for field in fields:
        values = getattr(entry, f"{prefix}_{field}")
        arrays[field] = (vector_to_ints(values) if field in
                         ("mu1Index", "mu2Index", "isValid")
                         else vector_to_floats(values))
    return arrays


def valid_vertices(entry, vertex_prefix):
    arrays = vertex_arrays(entry, vertex_prefix)
    for index in range(min(len(values) for values in arrays.values())):
        if arrays["isValid"][index] == 1:
            yield index, arrays


def fill_one_vertex(histograms, prefix, values, tracks_by_index, gen_by_charge,
                    weight, counters, sample_lxy_window):
    if prefix == "disStandalone":
        fill_mass_region_histograms(histograms, values, tracks_by_index, gen_by_charge, weight)
    index, arrays = values
    if prefix == "disStandalone":
        first = tracks_by_index.get(arrays["mu1Index"][index])
        second = tracks_by_index.get(arrays["mu2Index"][index])
        if first is not None and second is not None and first["charge"] * second["charge"] < 0:
            fill_dimuon_pt(
                histograms["disStandaloneFitDimuonPt"],
                arrays["refit_mu1_pt"][index], arrays["refit_mu1_phi"][index],
                arrays["refit_mu2_pt"][index], arrays["refit_mu2_phi"][index], weight)
            fill_dimuon_dr_vs_pt(
                histograms["disStandaloneFitDimuonDRVsPt"],
                arrays["refit_mu1_pt"][index], arrays["refit_mu1_eta"][index],
                arrays["refit_mu1_phi"][index], arrays["refit_mu2_pt"][index],
                arrays["refit_mu2_eta"][index], arrays["refit_mu2_phi"][index], weight)
    coordinates = [arrays[field][index] for field in
                   ("refit_mu1_eta", "refit_mu1_phi", "refit_mu2_eta", "refit_mu2_phi")]
    if all(is_valid_number(value) for value in coordinates):
        histograms[f"{prefix}FitDR"].Fill(delta_r(*coordinates), weight)
    mass = arrays["mass"][index]
    if is_valid_number(mass):
        histograms[f"{prefix}FitMass"].Fill(mass, weight)
        if prefix == "disStandalone" and passes_vertex_probability_cut(arrays["vtxProb"][index]):
            histograms["disStandaloneFitMassVtxProbGt0p001"].Fill(mass, weight)
    lxy = arrays["lxy"][index]
    valid_lxy = is_valid_number(lxy) and lxy > 0.0
    if is_valid_number(lxy):
        histograms[f"{prefix}FitLxy"].Fill(lxy, weight)
    lxy_error = arrays["lxyErr"][index]
    if is_valid_number(lxy_error):
        histograms[f"{prefix}FitLxyError"].Fill(lxy_error, weight)
    relative_lxy_error = None
    if valid_lxy and is_valid_number(lxy_error) and lxy_error >= 0.0:
        relative_lxy_error = lxy_error / lxy
        histograms[f"{prefix}FitLxyRelError"].Fill(relative_lxy_error, weight)
        if prefix != "disStandalone" and is_valid_number(mass) and relative_lxy_error < 6.0:
            histograms[f"{prefix}FitMassLxyRelErrorLt6"].Fill(mass, weight)
    if (prefix != "disStandalone" and sample_lxy_window is not None and is_valid_number(lxy) and
            sample_lxy_window[0] <= lxy <= sample_lxy_window[1] and
            is_valid_number(mass)):
        histograms[f"{prefix}FitMassLxyWindow"].Fill(mass, weight)
    refit_count = 0
    for muon_index_field, pt_field, error_field in (
        ("mu1Index", "refit_mu1_pt", "refit_mu1_ptError"),
        ("mu2Index", "refit_mu2_pt", "refit_mu2_ptError"),
    ):
        pt, error = arrays[pt_field][index], arrays[error_field][index]
        if not is_valid_number(pt) or pt <= 0.0:
            continue
        histograms[f"{prefix}RefitPt"].Fill(pt, weight)
        if math.isfinite(error) and error > 0.0:
            histograms[f"{prefix}RefitPtError"].Fill(error, weight)
        track = tracks_by_index.get(arrays[muon_index_field][index])
        gen_muon = gen_by_charge.get(track["charge"]) if track else None
        if gen_muon is None:
            counters["unmatched_refit_ratios"] += 1
        else:
            histograms[f"{prefix}RefitPtOverGenPt"].Fill(
                pt / gen_muon["pt"], weight)
            if prefix != "disStandalone" and valid_lxy:
                histograms[f"{prefix}FitLxyVsRefitPtOverGenPt"].Fill(
                    lxy, pt / gen_muon["pt"], weight)
            counters["matched_refit_ratios"] += 1
        refit_count += 1
    return refit_count


def fill_vertices(entry, histograms, prefix, vertex_prefix, tracks_by_index,
                  gen_by_charge, weight, counters, sample_lxy_window):
    vertices = list(valid_vertices(entry, vertex_prefix))
    if prefix == "disStandalone":
        histograms["disStandaloneNVertex"].Fill(len(vertices), weight)
        passed = sum(passes_vertex_probability_cut(arrays["vtxProb"][index])
                     for index, arrays in vertices)
        histograms["disStandaloneNVertexVtxProbGt0p001"].Fill(passed, weight)
    refit_count = sum(
        fill_one_vertex(histograms, prefix, vertex, tracks_by_index,
                        gen_by_charge, weight, counters, sample_lxy_window)
        for vertex in vertices
    )
    return len(vertices), refit_count


def fill_category(entry, histograms, prefix, tracks, vertex_prefix,
                  gen_by_charge, weight, counters, sample_lxy_window):
    if prefix == "disStandalone":
        histograms["disStandaloneNRecoMuon"].Fill(len(tracks), weight)
        fill_pair_pt(histograms["disStandaloneDimuonPt"], tracks, weight)
    fill_pair_delta_r(histograms[f"{prefix}DR"], tracks, weight)
    for track in tracks:
        fill_track_histograms(histograms, prefix, track, gen_by_charge,
                              weight, counters)
    vertex_count, refit_count = fill_vertices(
        entry, histograms, prefix, vertex_prefix,
        {track["index"]: track for track in tracks}, gen_by_charge,
        weight, counters, sample_lxy_window)
    return len(tracks), vertex_count, refit_count


def process_file(input_path, output_path, max_events):
    ROOT = get_root()
    root_file = ROOT.TFile.Open(input_path)
    if not root_file or root_file.IsZombie():
        raise RuntimeError(f"Could not open input ROOT file: {input_path}")
    try:
        tree = root_file.Get(TREE_PATH)
        validate_tree(tree)
        histograms = make_histograms(ROOT)
        lxy_window = sample_lxy_window(input_path)
        events = tracks_count = refits_count = vertices_count = 0
        counters = {
            "ambiguous_gen_events": 0,
            "matched_track_ratios": 0,
            "unmatched_track_ratios": 0,
            "matched_refit_ratios": 0,
            "unmatched_refit_ratios": 0,
        }
        event_limit = tree.GetEntries() if max_events < 0 else min(tree.GetEntries(), max_events)
        print(f"[START] pid={os.getpid()} file={os.path.basename(input_path)} "
              f"events={event_limit}/{tree.GetEntries()}", flush=True)
        for entry in tree:
            if events >= event_limit:
                break
            events += 1
            weight = float(entry.eventWeight)
            gen = make_gen_records(entry)
            fill_gen_dimuon_mass(ROOT, histograms["genMass"], gen, weight)
            fill_pair_pt(histograms["genDimuonPt"], gen, weight,
                         dr_vs_pt=histograms["genDimuonDRVsPt"])
            fill_gen_vs_displaced_mass(
                ROOT, histograms["disStandaloneGenVsRecoMass"], entry, gen, weight)
            if len(gen) == 2:
                histograms["genDR"].Fill(
                    delta_r(gen[0]["eta"], gen[0]["phi"],
                            gen[1]["eta"], gen[1]["phi"]), weight)
            for gen_muon in gen:
                histograms["genPt"].Fill(gen_muon["pt"], weight)
            gen_by_charge = unique_gen_by_charge(gen)
            if len(gen_by_charge) != len({muon["charge"] for muon in gen}):
                counters["ambiguous_gen_events"] += 1

            categories = (
                ("best", make_best_track_records(entry), BEST_VERTEX_PREFIX),
                ("standalone", make_standalone_track_records(entry),
                 STA_VERTEX_PREFIX),
                ("disStandalone",
                 make_standalone_track_records(entry, DISPLACED_MUON_PREFIX),
                 DISPLACED_STA_VERTEX_PREFIX),
                ("disTrack", make_records(entry, DISPLACED_TRACK_PREFIX),
                 DISPLACED_TRACK_VERTEX_PREFIX),
            )
            for prefix, tracks, vertex_prefix in categories:
                if prefix == "disStandalone":
                    fill_matched_gen_count_vs_dr(
                        histograms["disStandaloneNMatchedGenMuonVsGenDimuonDRChargeOnly"],
                        gen, tracks, weight,
                        require_pt_match=False, require_dr_match=False)
                    fill_matched_gen_count_vs_dr(
                        histograms["disStandaloneNMatchedGenMuonVsGenDimuonDRPt30Percent"],
                        gen, tracks, weight, dr_max=0.3, rel_pt_max=0.30)
                counts = fill_category(
                    entry, histograms, prefix, tracks, vertex_prefix,
                    gen_by_charge, weight, counters, lxy_window)
                tracks_count += counts[0]
                vertices_count += counts[1]
                refits_count += counts[2]
            if PROGRESS_EVERY > 0 and events % PROGRESS_EVERY == 0:
                print(f"[PROGRESS] events={events}/{event_limit}", flush=True)

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        tmp_output = f"{output_path}.tmp.root"
        output_file = ROOT.TFile.Open(tmp_output, "RECREATE")
        if not output_file or output_file.IsZombie():
            raise RuntimeError(f"Could not create output ROOT file: {tmp_output}")
        try:
            output_dirs = {
                name: output_file.mkdir(name)
                for name in dict.fromkeys(HISTOGRAM_DIRECTORIES.values())
            }
            for key, hist in histograms.items():
                output_dirs[histogram_directory(key)].cd()
                hist.Write()
        finally:
            output_file.Close()
        os.replace(tmp_output, output_path)
        print(f"[DONE] Wrote {output_path} ({events} events, tracks={tracks_count}, "
              f"valid refit tracks={refits_count}, valid vertices={vertices_count}, "
              f"track ratios matched/unmatched="
              f"{counters['matched_track_ratios']}/{counters['unmatched_track_ratios']}, "
              f"refit ratios matched/unmatched="
              f"{counters['matched_refit_ratios']}/{counters['unmatched_refit_ratios']}, "
              f"ambiguous-gen events={counters['ambiguous_gen_events']})", flush=True)
        return output_path
    finally:
        root_file.Close()


def main():
    args = parse_cli()
    input_path = os.path.abspath(args.input_root)
    output_path = os.path.abspath(args.output_root)
    if not os.path.isfile(input_path):
        print(f"[ERROR] Input file does not exist: {input_path}", file=sys.stderr)
        return 1
    if input_path == output_path:
        print("[ERROR] Input and output paths must differ", file=sys.stderr)
        return 1
    print(f"[INFO] Input       : {input_path}")
    print(f"[INFO] Output      : {output_path}")
    print(f"[INFO] Tree        : {TREE_PATH}")
    print("[INFO] Gen match   : unique generator-level muon with the same charge")
    print("[INFO] Reco select : all valid tracks and all valid OS vertex fits")
    print(f"[INFO] Events      : {'all' if args.max_events < 0 else args.max_events}")
    process_file(input_path, output_path, args.max_events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
