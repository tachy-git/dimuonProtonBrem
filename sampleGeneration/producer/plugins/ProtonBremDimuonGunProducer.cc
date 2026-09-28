#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/EventSetup.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/Framework/interface/global/EDProducer.h"
#include "FWCore/ParameterSet/interface/ConfigurationDescriptions.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/Utilities/interface/Exception.h"

#include "SimDataFormats/GeneratorProducts/interface/GenEventInfoProduct.h"
#include "SimDataFormats/GeneratorProducts/interface/HepMCProduct.h"

#include "HepMC/GenEvent.h"
#include "HepMC/GenParticle.h"
#include "HepMC/GenVertex.h"
#include "HepMC/Units.h"

namespace {
struct NpyArray {
  std::size_t rows = 0;
  std::size_t cols = 0;
  std::vector<double> data;

  double at(std::size_t row, std::size_t col) const { return data[row * cols + col]; }
};

std::string trim(std::string value) {
  const auto first = value.find_first_not_of(" \t\n\r");
  if (first == std::string::npos) {
    return "";
  }
  const auto last = value.find_last_not_of(" \t\n\r");
  return value.substr(first, last - first + 1);
}

bool headerContainsFalseFortranOrder(const std::string& header) {
  const auto key = header.find("fortran_order");
  if (key == std::string::npos) {
    return false;
  }
  const auto falsePos = header.find("False", key);
  const auto truePos = header.find("True", key);
  return falsePos != std::string::npos && (truePos == std::string::npos || falsePos < truePos);
}

std::string parseDescr(const std::string& header) {
  const auto key = header.find("'descr'");
  const auto key2 = header.find("\"descr\"");
  const auto pos = std::min(key == std::string::npos ? header.size() : key,
                            key2 == std::string::npos ? header.size() : key2);
  if (pos == header.size()) {
    throw std::runtime_error("NPY header has no descr field");
  }

  const auto colon = header.find(':', pos);
  if (colon == std::string::npos) {
    throw std::runtime_error("Could not parse NPY descr field");
  }
  const auto quote = header.find_first_of("'\"", colon);
  if (quote == std::string::npos) {
    throw std::runtime_error("Could not parse NPY descr field");
  }
  const auto endQuote = header.find(header[quote], quote + 1);
  if (endQuote == std::string::npos) {
    throw std::runtime_error("Could not parse NPY descr field");
  }
  return header.substr(quote + 1, endQuote - quote - 1);
}

std::vector<std::size_t> parseShape(const std::string& header) {
  const auto key = header.find("'shape'");
  const auto key2 = header.find("\"shape\"");
  const auto pos = std::min(key == std::string::npos ? header.size() : key,
                            key2 == std::string::npos ? header.size() : key2);
  if (pos == header.size()) {
    throw std::runtime_error("NPY header has no shape field");
  }

  const auto open = header.find('(', pos);
  const auto close = header.find(')', open);
  if (open == std::string::npos || close == std::string::npos) {
    throw std::runtime_error("Could not parse NPY shape field");
  }

  std::vector<std::size_t> shape;
  std::stringstream values(header.substr(open + 1, close - open - 1));
  std::string token;
  while (std::getline(values, token, ',')) {
    token = trim(token);
    if (!token.empty()) {
      shape.push_back(static_cast<std::size_t>(std::stoull(token)));
    }
  }
  return shape;
}

template <typename T>
std::vector<double> readPayload(std::ifstream& input, std::size_t count) {
  std::vector<T> raw(count);
  input.read(reinterpret_cast<char*>(raw.data()), static_cast<std::streamsize>(count * sizeof(T)));
  if (!input) {
    throw std::runtime_error("NPY payload is shorter than expected");
  }

  std::vector<double> data;
  data.reserve(count);
  for (const auto value : raw) {
    data.push_back(static_cast<double>(value));
  }
  return data;
}

NpyArray readNpyArray(const std::string& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error("Could not open " + path);
  }

  char magic[6];
  input.read(magic, sizeof(magic));
  if (!input || std::memcmp(magic, "\x93NUMPY", sizeof(magic)) != 0) {
    throw std::runtime_error(path + " is not an NPY file");
  }

  uint8_t major = 0;
  uint8_t minor = 0;
  input.read(reinterpret_cast<char*>(&major), 1);
  input.read(reinterpret_cast<char*>(&minor), 1);

  std::uint32_t headerLen = 0;
  if (major == 1) {
    std::uint16_t len16 = 0;
    input.read(reinterpret_cast<char*>(&len16), sizeof(len16));
    headerLen = len16;
  } else if (major == 2 || major == 3) {
    input.read(reinterpret_cast<char*>(&headerLen), sizeof(headerLen));
  } else {
    throw std::runtime_error("Unsupported NPY version " + std::to_string(major) + "." + std::to_string(minor));
  }

  std::string header(headerLen, '\0');
  input.read(header.data(), static_cast<std::streamsize>(header.size()));
  if (!input) {
    throw std::runtime_error("Could not read NPY header");
  }

  if (!headerContainsFalseFortranOrder(header)) {
    throw std::runtime_error("Only C-contiguous NPY arrays are supported");
  }

  const auto descr = parseDescr(header);
  const auto shape = parseShape(header);
  if (shape.size() != 2) {
    throw std::runtime_error("Expected a 2D NPY array");
  }
  if (shape[1] < 17) {
    throw std::runtime_error("Expected at least 17 columns in the NPY array");
  }

  const auto count = shape[0] * shape[1];
  NpyArray array;
  array.rows = shape[0];
  array.cols = shape[1];

  if (descr == "<f8" || descr == "|f8" || descr == "=f8") {
    array.data = readPayload<double>(input, count);
  } else if (descr == "<f4" || descr == "|f4" || descr == "=f4") {
    array.data = readPayload<float>(input, count);
  } else {
    throw std::runtime_error("Unsupported NPY dtype '" + descr + "'. Use float32 or float64.");
  }

  return array;
}
}  // namespace

class ProtonBremDimuonGunProducer : public edm::global::EDProducer<> {
public:
  explicit ProtonBremDimuonGunProducer(const edm::ParameterSet&);
  ~ProtonBremDimuonGunProducer() override = default;

  void produce(edm::StreamID, edm::Event&, const edm::EventSetup&) const override;
  static void fillDescriptions(edm::ConfigurationDescriptions& descriptions);

private:
  std::string npyFile_;
  NpyArray events_;

  int motherId_;
  int muMinusId_;
  int muPlusId_;
  double lxy_;
  int verbosity_;
};

ProtonBremDimuonGunProducer::ProtonBremDimuonGunProducer(const edm::ParameterSet& pset)
    : npyFile_(pset.getParameter<std::string>("NpyFile")),
      motherId_(pset.getParameter<int>("MotherPdgId")),
      muMinusId_(pset.getParameter<int>("MuMinusPdgId")),
      muPlusId_(pset.getParameter<int>("MuPlusPdgId")),
      lxy_(pset.getParameter<double>("Lxy")),
      verbosity_(pset.getUntrackedParameter<int>("Verbosity", 0)) {
  try {
    events_ = readNpyArray(npyFile_);
  } catch (const std::exception& err) {
    throw cms::Exception("ProtonBremDimuonGunProducer") << "Failed to read " << npyFile_ << ": " << err.what();
  }

  produces<edm::HepMCProduct>("unsmeared");
  produces<GenEventInfoProduct>();
}

void ProtonBremDimuonGunProducer::produce(edm::StreamID, edm::Event& event, const edm::EventSetup&) const {
  const std::size_t row = static_cast<std::size_t>(event.id().event() - 1);
  if (row >= events_.rows) {
    throw cms::Exception("ProtonBremDimuonGunProducer")
        << "Requested event row " << row << " but " << npyFile_ << " has only " << events_.rows << " rows";
  }

  const double motherE = events_.at(row, 4);
  const double motherPx = events_.at(row, 5);
  const double motherPy = events_.at(row, 6);
  const double motherPz = events_.at(row, 7);

  const double mu1E = events_.at(row, 8);
  const double mu1Px = events_.at(row, 9);
  const double mu1Py = events_.at(row, 10);
  const double mu1Pz = events_.at(row, 11);

  const double mu2E = events_.at(row, 12);
  const double mu2Px = events_.at(row, 13);
  const double mu2Py = events_.at(row, 14);
  const double mu2Pz = events_.at(row, 15);
  const double weight = events_.at(row, 16);

  const double lxy = lxy_;
  const double phi = std::atan2(motherPy, motherPx);
  const double vx = lxy * std::cos(phi);
  const double vy = lxy * std::sin(phi);
  const double vz = 0.0;
  const double time = 0.0;

  auto genEvent = std::make_unique<HepMC::GenEvent>(HepMC::Units::GEV, HepMC::Units::MM);
  genEvent->set_event_number(event.id().event());
  genEvent->set_signal_process_id(20);
  genEvent->weights().push_back(weight);

  auto* vProd = new HepMC::GenVertex(HepMC::FourVector(vx, vy, vz, time));
  auto* mother = new HepMC::GenParticle(HepMC::FourVector(motherPx, motherPy, motherPz, motherE), motherId_, 2);
  vProd->add_particle_out(mother);
  genEvent->add_vertex(vProd);

  auto* vDec = new HepMC::GenVertex(HepMC::FourVector(vx, vy, vz, time));
  vDec->add_particle_in(mother);

  auto* muPlus = new HepMC::GenParticle(HepMC::FourVector(mu1Px, mu1Py, mu1Pz, mu1E), muPlusId_, 1);
  auto* muMinus = new HepMC::GenParticle(HepMC::FourVector(mu2Px, mu2Py, mu2Pz, mu2E), muMinusId_, 1);

  vDec->add_particle_out(muPlus);
  vDec->add_particle_out(muMinus);
  genEvent->add_vertex(vDec);

  if (verbosity_ > 0) {
    genEvent->print();
  }

  auto genInfo = std::make_unique<GenEventInfoProduct>(genEvent.get());
  event.put(std::move(genInfo));

  auto out = std::make_unique<edm::HepMCProduct>();
  out->addHepMCData(genEvent.release());
  event.put(std::move(out), "unsmeared");
}

void ProtonBremDimuonGunProducer::fillDescriptions(edm::ConfigurationDescriptions& descriptions) {
  edm::ParameterSetDescription desc;
  desc.add<std::string>("NpyFile", "");
  desc.add<int>("MotherPdgId", 999999);
  desc.add<int>("MuMinusPdgId", 13);
  desc.add<int>("MuPlusPdgId", -13);
  desc.add<double>("Lxy", 0.0);
  desc.addUntracked<int>("Verbosity", 0);
  descriptions.add("protonBremDimuonGunProducer", desc);
}

DEFINE_FWK_MODULE(ProtonBremDimuonGunProducer);
