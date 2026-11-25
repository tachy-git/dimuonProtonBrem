# Auto generated with CMSSW_16_1_3 from:
# cmsDriver.py dimuonExoNanoMC --mc --eventcontent NANOAODSIM \
#   --datatier NANOAODSIM --conditions 140X_mcRun3_2024_design_v11 \
#   --step PAT,NANO:@PHYS --era Run3_2024 --no_exec
import FWCore.ParameterSet.Config as cms

from Configuration.Eras.Era_Run3_2024_cff import Run3_2024

process = cms.Process("NANO", Run3_2024)

process.load("Configuration.StandardSequences.Services_cff")
process.load("SimGeneral.HepPDTESSource.pythiapdt_cfi")
process.load("FWCore.MessageService.MessageLogger_cfi")
process.load("Configuration.EventContent.EventContent_cff")
process.load("SimGeneral.MixingModule.mixNoPU_cfi")
process.load("Configuration.StandardSequences.GeometryRecoDB_cff")
process.load("Configuration.StandardSequences.MagneticField_cff")
process.load("Configuration.StandardSequences.PAT_cff")
process.load("PhysicsTools.NanoAOD.nano_cff")
process.load("Configuration.StandardSequences.EndOfProcess_cff")
process.load("Configuration.StandardSequences.FrontierConditions_GlobalTag_cff")

process.maxEvents = cms.untracked.PSet(
    input=cms.untracked.int32(-1),
    output=cms.optional.untracked.allowed(cms.int32, cms.PSet),
)

process.source = cms.Source(
    "PoolSource",
    fileNames=cms.untracked.vstring("file:test.root"),
    secondaryFileNames=cms.untracked.vstring(),
)

process.options = cms.untracked.PSet(
    IgnoreCompletely=cms.untracked.vstring(),
    Rethrow=cms.untracked.vstring(),
    TryToContinue=cms.untracked.vstring(),
    accelerators=cms.untracked.vstring("*"),
    allowUnscheduled=cms.obsolete.untracked.bool,
    canDeleteEarly=cms.untracked.vstring(),
    deleteNonConsumedUnscheduledModules=cms.untracked.bool(True),
    dumpOptions=cms.untracked.bool(False),
    emptyRunLumiMode=cms.obsolete.untracked.string,
    eventSetup=cms.untracked.PSet(
        forceNumberOfConcurrentIOVs=cms.untracked.PSet(
            allowAnyLabel_=cms.required.untracked.uint32,
        ),
        numberOfConcurrentIOVs=cms.untracked.uint32(0),
    ),
    fileMode=cms.untracked.string("FULLMERGE"),
    forceEventSetupCacheClearOnNewRun=cms.untracked.bool(False),
    holdsReferencesToDeleteEarly=cms.untracked.VPSet(),
    makeTriggerResults=cms.obsolete.untracked.bool,
    modulesToCallForTryToContinue=cms.untracked.vstring(),
    modulesToIgnoreForDeleteEarly=cms.untracked.vstring(),
    numberOfConcurrentLuminosityBlocks=cms.untracked.uint32(0),
    numberOfConcurrentRuns=cms.untracked.uint32(1),
    numberOfStreams=cms.untracked.uint32(0),
    numberOfThreads=cms.untracked.uint32(1),
    printDependencies=cms.untracked.bool(False),
    sizeOfStackForThreadsInKB=cms.optional.untracked.uint32,
    throwIfIllegalParameter=cms.untracked.bool(True),
    wantSummary=cms.untracked.bool(False),
)

process.configurationMetadata = cms.untracked.PSet(
    annotation=cms.untracked.string("dimuon EXO NanoAOD"),
    name=cms.untracked.string("Applications"),
    version=cms.untracked.string("CMSSW_16_1_3"),
)

process.NANOAODSIMoutput = cms.OutputModule(
    "NanoAODOutputModule",
    compressionAlgorithm=cms.untracked.string("LZMA"),
    compressionLevel=cms.untracked.int32(9),
    dataset=cms.untracked.PSet(
        dataTier=cms.untracked.string("NANOAODSIM"),
        filterName=cms.untracked.string(""),
    ),
    fileName=cms.untracked.string("file:output.root"),
    outputCommands=process.NANOAODSIMEventContent.outputCommands,
)

from Configuration.AlCa.GlobalTag import GlobalTag

process.GlobalTag = GlobalTag(process.GlobalTag, "140X_mcRun3_2024_design_v11", "")

process.Flag_BadChargedCandidateFilter = cms.Path(process.BadChargedCandidateFilter)
process.Flag_BadChargedCandidateSummer16Filter = cms.Path(process.BadChargedCandidateSummer16Filter)
process.Flag_BadPFMuonDzFilter = cms.Path(process.BadPFMuonDzFilter)
process.Flag_BadPFMuonFilter = cms.Path(process.BadPFMuonFilter)
process.Flag_BadPFMuonSummer16Filter = cms.Path(process.BadPFMuonSummer16Filter)
process.Flag_CSCTightHalo2015Filter = cms.Path(process.CSCTightHalo2015Filter)
process.Flag_CSCTightHaloFilter = cms.Path(process.CSCTightHaloFilter)
process.Flag_CSCTightHaloTrkMuUnvetoFilter = cms.Path(process.CSCTightHaloTrkMuUnvetoFilter)
process.Flag_EcalDeadCellBoundaryEnergyFilter = cms.Path(process.EcalDeadCellBoundaryEnergyFilter)
process.Flag_EcalDeadCellTriggerPrimitiveFilter = cms.Path(process.EcalDeadCellTriggerPrimitiveFilter)
process.Flag_HBHENoiseFilter = cms.Path(process.HBHENoiseFilterResultProducer + process.HBHENoiseFilter)
process.Flag_HBHENoiseIsoFilter = cms.Path(process.HBHENoiseFilterResultProducer + process.HBHENoiseIsoFilter)
process.Flag_HcalStripHaloFilter = cms.Path(process.HcalStripHaloFilter)
process.Flag_chargedHadronTrackResolutionFilter = cms.Path(process.chargedHadronTrackResolutionFilter)
process.Flag_ecalBadCalibFilter = cms.Path(process.ecalBadCalibFilter)
process.Flag_ecalLaserCorrFilter = cms.Path(process.ecalLaserCorrFilter)
process.Flag_eeBadScFilter = cms.Path(process.eeBadScFilter)
process.Flag_globalSuperTightHalo2016Filter = cms.Path(process.globalSuperTightHalo2016Filter)
process.Flag_globalTightHalo2016Filter = cms.Path(process.globalTightHalo2016Filter)
process.Flag_goodVertices = cms.Path(process.primaryVertexFilter)
process.Flag_hcalLaserEventFilter = cms.Path(process.hcalLaserEventFilter)
process.Flag_hfNoisyHitsFilter = cms.Path(process.hfNoisyHitsFilter)
process.Flag_muonBadTrackFilter = cms.Path(process.muonBadTrackFilter)
process.Flag_trackingFailureFilter = cms.Path(process.goodVertices + process.trackingFailureFilter)
process.Flag_trkPOGFilters = cms.Path(process.trkPOGFilters)
process.Flag_trkPOG_logErrorTooManyClusters = cms.Path(~process.logErrorTooManyClusters)
process.Flag_trkPOG_manystripclus53X = cms.Path(~process.manystripclus53X)
process.Flag_trkPOG_toomanystripclus53X = cms.Path(~process.toomanystripclus53X)
process.nanoAOD_step = cms.Path(process.nanoSequenceMC)
process.endjob_step = cms.EndPath(process.endOfProcess)
process.NANOAODSIMoutput_step = cms.EndPath(process.NANOAODSIMoutput)

process.schedule = cms.Schedule(
    process.Flag_BadChargedCandidateFilter,
    process.Flag_BadChargedCandidateSummer16Filter,
    process.Flag_BadPFMuonDzFilter,
    process.Flag_BadPFMuonFilter,
    process.Flag_BadPFMuonSummer16Filter,
    process.Flag_CSCTightHalo2015Filter,
    process.Flag_CSCTightHaloFilter,
    process.Flag_CSCTightHaloTrkMuUnvetoFilter,
    process.Flag_EcalDeadCellBoundaryEnergyFilter,
    process.Flag_EcalDeadCellTriggerPrimitiveFilter,
    process.Flag_HBHENoiseFilter,
    process.Flag_HBHENoiseIsoFilter,
    process.Flag_HcalStripHaloFilter,
    process.Flag_chargedHadronTrackResolutionFilter,
    process.Flag_ecalBadCalibFilter,
    process.Flag_ecalLaserCorrFilter,
    process.Flag_eeBadScFilter,
    process.Flag_globalSuperTightHalo2016Filter,
    process.Flag_globalTightHalo2016Filter,
    process.Flag_goodVertices,
    process.Flag_hcalLaserEventFilter,
    process.Flag_hfNoisyHitsFilter,
    process.Flag_muonBadTrackFilter,
    process.Flag_trackingFailureFilter,
    process.Flag_trkPOGFilters,
    process.Flag_trkPOG_logErrorTooManyClusters,
    process.Flag_trkPOG_manystripclus53X,
    process.Flag_trkPOG_toomanystripclus53X,
    process.nanoAOD_step,
    process.endjob_step,
    process.NANOAODSIMoutput_step,
)
process.schedule.associate(process.patTask)

from PhysicsTools.PatAlgos.tools.helpers import associatePatAlgosToolsTask

associatePatAlgosToolsTask(process)

from PhysicsTools.NanoAOD.nano_cff import nanoAOD_customizeCommon

process = nanoAOD_customizeCommon(process)

from Configuration.StandardSequences.PAT_cff import miniAOD_customizeAllMC

process = miniAOD_customizeAllMC(process)

# Use only the dimuon pieces of EXOnanoAODv1.  The full add_exonanoTables
# customisation also adds electron, MDS, displaced-jet and displaced-tau tables.
from PhysicsTools.NanoAOD.custom_exo_cff import add_dsamuonTables, update_genParticleTable

process = add_dsamuonTables(process)
process = update_genParticleTable(process)

process.source.delayReadingEventProducts = cms.untracked.bool(False)

from Configuration.StandardSequences.earlyDeleteSettings_cff import customiseEarlyDelete

process = customiseEarlyDelete(process)

# Runtime interface used by run_condor_job.sh.
from FWCore.ParameterSet.VarParsing import VarParsing

_runtime_options = VarParsing()
_runtime_options.register(
    "maxEvents",
    -1,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.int,
    "maximum number of AODSIM events to process",
)
_runtime_options.register(
    "inputFile",
    "",
    VarParsing.multiplicity.singleton,
    VarParsing.varType.string,
    "input AODSIM ROOT file",
)
_runtime_options.register(
    "outputFile",
    "output.root",
    VarParsing.multiplicity.singleton,
    VarParsing.varType.string,
    "output NANOAODSIM ROOT file",
)
_runtime_options.parseArguments()
if not _runtime_options.inputFile:
    raise RuntimeError("inputFile=... is required")

process.maxEvents.input = cms.untracked.int32(_runtime_options.maxEvents)
process.source.fileNames = cms.untracked.vstring("file:" + _runtime_options.inputFile)
process.NANOAODSIMoutput.fileName = cms.untracked.string("file:" + _runtime_options.outputFile)
