/* SPDX-License-Identifier: Apache-2.0 */

#include "astra-sim/system/BusBwYaml.hh"

#include <algorithm>
#include <cctype>
#include <fstream>

static std::string trim(const std::string& s) {
  size_t a = 0;
  size_t b = s.size();
  while (a < b && std::isspace(static_cast<unsigned char>(s[a]))) {
    a++;
  }
  while (b > a && std::isspace(static_cast<unsigned char>(s[b - 1]))) {
    b--;
  }
  return s.substr(a, b - a);
}

static std::string to_lower(std::string s) {
  for (auto& c : s) {
    c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  }
  return s;
}

static bool parse_section_header(const std::string& line, std::string* sec) {
  if (line.empty() || line.back() != ':') {
    return false;
  }
  std::string name = trim(line.substr(0, line.size() - 1));
  if (name == "TP" || name == "DP" || name == "EP" || name == "PP" ||
      name == "DP_EP") {
    *sec = name;
    return true;
  }
  return false;
}

bool load_bus_bw_yaml_file(const std::string& path, BusBwYamlConfig& out) {
  std::ifstream in(path);
  if (!in) {
    return false;
  }
  out = BusBwYamlConfig{};
  out.loaded = true;

  std::string line;
  std::string current_section;

  while (std::getline(in, line)) {
    line = trim(line);
    if (line.empty() || line[0] == '#') {
      continue;
    }
    std::string sec_tmp;
    if (parse_section_header(line, &sec_tmp)) {
      current_section = sec_tmp;
      continue;
    }

    size_t colon = line.find(':');
    if (colon == std::string::npos) {
      continue;
    }

    std::string key = trim(line.substr(0, colon));
    std::string val = trim(line.substr(colon + 1));

    while (!key.empty() && key.back() == ',') {
      key.pop_back();
      key = trim(key);
    }

    key = to_lower(key);

    if (current_section.empty()) {
      continue;
    }

    if (current_section == "PP" && key == "busbw") {
      try {
        out.pp_flat_busbw = std::stod(val);
      } catch (...) {
      }
      continue;
    }

    if (val == "null") {
      out.explicit_null.insert({current_section, key});
      continue;
    }

    try {
      double v = std::stod(val);
      out.section_coll_gbps[current_section][key] = v;
    } catch (...) {
    }
  }

  return true;
}

static bool lookup_in_section(
    const BusBwYamlConfig& cfg,
    const std::string& section,
    const std::string& coll_lower,
    double* out_gbps) {
  if (cfg.explicit_null.count({section, coll_lower})) {
    return false;
  }
  auto sit = cfg.section_coll_gbps.find(section);
  if (sit == cfg.section_coll_gbps.end()) {
    return false;
  }
  auto cit = sit->second.find(coll_lower);
  if (cit == sit->second.end()) {
    return false;
  }
  *out_gbps = cit->second;
  return true;
}

bool busbw_yaml_lookup(
    const BusBwYamlConfig& cfg,
    const std::string& section_tag,
    const char* coll_type,
    double* out_gbps) {
  if (!cfg.loaded || coll_type == nullptr || out_gbps == nullptr) {
    return false;
  }

  std::string coll = to_lower(std::string(coll_type));

  if (section_tag == "PP") {
    if (cfg.pp_flat_busbw > 0.0) {
      *out_gbps = cfg.pp_flat_busbw;
      return true;
    }
    return false;
  }

  if (section_tag == "DP_EP") {
    if (lookup_in_section(cfg, "DP_EP", coll, out_gbps)) {
      return true;
    }
    return lookup_in_section(cfg, "EP", coll, out_gbps);
  }

  return lookup_in_section(cfg, section_tag, coll, out_gbps);
}
