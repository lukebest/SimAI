/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BUS_BW_YAML_HH
#define BUS_BW_YAML_HH

#include <map>
#include <set>
#include <string>

struct BusBwYamlConfig {
  bool loaded = false;
  std::map<std::string, std::map<std::string, double>> section_coll_gbps;
  std::set<std::pair<std::string, std::string>> explicit_null;
  double pp_flat_busbw = -1.0;
};

bool load_bus_bw_yaml_file(const std::string& path, BusBwYamlConfig& out);

bool busbw_yaml_lookup(
    const BusBwYamlConfig& cfg,
    const std::string& section_tag,
    const char* coll_type,
    double* out_gbps);

#endif
