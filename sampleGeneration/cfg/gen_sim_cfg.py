"""NPY-backed displaced dimuon GEN-SIM configuration (CMSSW_14_0_18)."""

import ast
import struct

import FWCore.ParameterSet.Config as cms
from FWCore.ParameterSet.VarParsing import VarParsing
from Configuration.Eras.Era_Run3_2024_cff import Run3_2024


def npy_rows(path):
    with open(path, "rb") as handle:
        if handle.read(6) != b"\x93NUMPY":
            raise RuntimeError("%s is not an NPY file" % path)
        version = handle.read(2)
        if len(version) != 2:
            raise RuntimeError("Truncated NPY version")
        if version[0] == 1:
            length = struct.unpack("<H", handle.read(2))[0]
        elif version[0] in (2, 3):
            length = struct.unpack("<I", handle.read(4))[0]
        else:
            raise RuntimeError("Unsupported NPY version %d" % version[0])
        header = ast.literal_eval(handle.read(length).decode("latin1"))
    shape = header.get("shape")
    if len(shape) != 2 or shape[0] < 1 or shape[1] < 17:
        raise RuntimeError("Expected a nonempty 2D NPY array with at least 17 columns")
    return int(shape[0])


options = VarParsing()
options.register("maxEvents", -1, VarParsing.multiplicity.singleton, VarParsing.varType.int, "deprecated; NPY row count is always used")
options.register("inputNpy", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "input NPY file")
options.register("lxy", 0.0, VarParsing.multiplicity.singleton, VarParsing.varType.float, "transverse decay length in mm")
options.register("motherPdgId", 999999, VarParsing.multiplicity.singleton, VarParsing.varType.int, "mother PDG ID")
options.register("muMinusPdgId", 13, VarParsing.multiplicity.singleton, VarParsing.varType.int, "negative-muon PDG ID")
options.register("muPlusPdgId", -13, VarParsing.multiplicity.singleton, VarParsing.varType.int, "positive-muon PDG ID")
options.register("outputFile", "output.root", VarParsing.multiplicity.singleton, VarParsing.varType.string, "output ROOT file")
options.register("seed", 1, VarParsing.multiplicity.singleton, VarParsing.varType.int, "base RNG seed")
options.parseArguments()
if not options.inputNpy:
    raise RuntimeError("inputNpy=/path/to/chunk.npy is required")
rows = npy_rows(options.inputNpy)
events = rows

process = cms.Process("SIM", Run3_2024)
process.load("Configuration.StandardSequences.Services_cff")
process.load("SimGeneral.HepPDTESSource.pythiapdt_cfi")
process.load("FWCore.MessageService.MessageLogger_cfi")
process.load("Configuration.EventContent.EventContent_cff")
process.load("SimGeneral.MixingModule.mixNoPU_cfi")
process.load("Configuration.StandardSequences.GeometryRecoDB_cff")
process.load("Configuration.StandardSequences.GeometrySimDB_cff")
process.load("Configuration.StandardSequences.MagneticField_cff")
process.load("Configuration.StandardSequences.Generator_cff")
process.load("Configuration.StandardSequences.VtxSmearedNoSmear_cff")
process.load("GeneratorInterface.Core.genFilterSummary_cff")
process.load("Configuration.StandardSequences.SimIdeal_cff")
process.load("Configuration.StandardSequences.EndOfProcess_cff")
process.load("Configuration.StandardSequences.FrontierConditions_GlobalTag_cff")

process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(events))
process.source = cms.Source("EmptySource")
process.MessageLogger.cerr.FwkReport.reportEvery = 100

from Configuration.AlCa.GlobalTag import GlobalTag
process.GlobalTag = GlobalTag(process.GlobalTag, "140X_mcRun3_2024_design_v11", "")

process.generator = cms.EDProducer(
    "ProtonBremDimuonGunProducer",
    NpyFile=cms.string(options.inputNpy),
    MotherPdgId=cms.int32(options.motherPdgId),
    MuMinusPdgId=cms.int32(options.muMinusPdgId),
    MuPlusPdgId=cms.int32(options.muPlusPdgId),
    Lxy=cms.double(options.lxy),
    Verbosity=cms.untracked.int32(0),
)

process.RAWSIMoutput = cms.OutputModule(
    "PoolOutputModule",
    SelectEvents=cms.untracked.PSet(SelectEvents=cms.vstring("generation_step")),
    compressionAlgorithm=cms.untracked.string("LZMA"),
    compressionLevel=cms.untracked.int32(1),
    dataset=cms.untracked.PSet(dataTier=cms.untracked.string("GEN-SIM"), filterName=cms.untracked.string("")),
    eventAutoFlushCompressedSize=cms.untracked.int32(20971520),
    fileName=cms.untracked.string("file:" + options.outputFile),
    outputCommands=process.RAWSIMEventContent.outputCommands,
    splitLevel=cms.untracked.int32(0),
)

process.generation_step = cms.Path(process.pgen)
process.simulation_step = cms.Path(process.psim)
process.genfiltersummary_step = cms.EndPath(process.genFilterSummary)
process.endjob_step = cms.EndPath(process.endOfProcess)
process.RAWSIMoutput_step = cms.EndPath(process.RAWSIMoutput)
process.schedule = cms.Schedule(
    process.generation_step, process.genfiltersummary_step, process.simulation_step,
    process.endjob_step, process.RAWSIMoutput_step,
)

from PhysicsTools.PatAlgos.tools.helpers import associatePatAlgosToolsTask
associatePatAlgosToolsTask(process)
for path in process.paths:
    getattr(process, path).insert(0, process.generator)

from IOMC.RandomEngine.RandomServiceHelper import RandomNumberServiceHelper
random_helper = RandomNumberServiceHelper(process.RandomNumberGeneratorService)
seed_count = random_helper.countSeeds()
random_helper.insertSeeds(*[1 + ((options.seed - 1 + index) % 900000000) for index in range(seed_count)])

from Configuration.StandardSequences.earlyDeleteSettings_cff import customiseEarlyDelete
process = customiseEarlyDelete(process)
