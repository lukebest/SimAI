#ifndef GRANULARITY_CONTROLLER_H
#define GRANULARITY_CONTROLLER_H

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace calendar {

using DemandMatrix = std::vector<std::vector<double>>;

struct CalendarScheduleEntry {
  std::vector<uint32_t> permutation;
  uint32_t slots;
};

struct CalendarSchedule {
  std::vector<CalendarScheduleEntry> entries;
};

enum class GranularityMode { OPERATOR, PHASE, CHUNK, PACKET, SLOT };

inline std::string NormalizeGranularityMode(std::string mode) {
  std::transform(mode.begin(), mode.end(), mode.begin(),
                 [](unsigned char ch) { return std::tolower(ch); });
  return mode;
}

inline GranularityMode ParseGranularityMode(std::string mode) {
  mode = NormalizeGranularityMode(mode);
  if (mode == "operator") {
    return GranularityMode::OPERATOR;
  }
  if (mode == "phase" || mode == "stage") {
    return GranularityMode::PHASE;
  }
  if (mode == "chunk" || mode == "tile") {
    return GranularityMode::CHUNK;
  }
  if (mode == "packet") {
    return GranularityMode::PACKET;
  }
  if (mode == "slot" || mode == "cycle") {
    return GranularityMode::SLOT;
  }
  return GranularityMode::OPERATOR;
}

inline bool HasPositiveDemand(const DemandMatrix& demand) {
  for (const auto& row : demand) {
    for (double value : row) {
      if (value > 0.0) {
        return true;
      }
    }
  }
  return false;
}

inline void AppendScheduleEntry(CalendarSchedule* schedule,
                                std::vector<uint32_t> permutation) {
  if (schedule == nullptr) {
    return;
  }
  if (!schedule->entries.empty() &&
      schedule->entries.back().permutation == permutation) {
    schedule->entries.back().slots++;
    return;
  }
  schedule->entries.push_back({std::move(permutation), 1});
}

inline std::vector<uint32_t> BuildRoundRobinPermutation(uint32_t radix,
                                                        uint32_t slot) {
  std::vector<uint32_t> permutation(radix, 0);
  if (radix == 0) {
    return permutation;
  }
  const uint32_t rotation = radix == 1 ? 0 : (slot % (radix - 1)) + 1;
  for (uint32_t in = 0; in < radix; ++in) {
    permutation[in] = (in + rotation) % radix;
  }
  return permutation;
}

inline std::vector<uint32_t> BuildDemandAwarePermutation(
    std::vector<std::vector<double>>* residual, uint32_t fallback_slot) {
  const uint32_t radix = static_cast<uint32_t>(residual->size());
  std::vector<uint32_t> permutation =
      BuildRoundRobinPermutation(radix, fallback_slot);
  std::vector<bool> usedIn(radix, false);
  std::vector<bool> usedOut(radix, false);

  for (uint32_t matched = 0; matched < radix; ++matched) {
    double bestWeight = 0.0;
    uint32_t bestIn = radix;
    uint32_t bestOut = radix;
    for (uint32_t in = 0; in < radix; ++in) {
      if (usedIn[in]) {
        continue;
      }
      for (uint32_t out = 0; out < (*residual)[in].size(); ++out) {
        if (out >= radix || usedOut[out] || in == out) {
          continue;
        }
        if ((*residual)[in][out] > bestWeight) {
          bestWeight = (*residual)[in][out];
          bestIn = in;
          bestOut = out;
        }
      }
    }
    if (bestIn == radix) {
      break;
    }
    permutation[bestIn] = bestOut;
    usedIn[bestIn] = true;
    usedOut[bestOut] = true;
    (*residual)[bestIn][bestOut] =
        std::max(0.0, (*residual)[bestIn][bestOut] - 1.0);
  }

  return permutation;
}

inline CalendarSchedule BuildCalendarSchedule(const DemandMatrix& demand,
                                              std::string algorithm,
                                              uint32_t frame_slots) {
  CalendarSchedule schedule;
  if (demand.empty() || frame_slots == 0) {
    return schedule;
  }

  const uint32_t radix = static_cast<uint32_t>(demand.size());
  algorithm = NormalizeGranularityMode(std::move(algorithm));
  const bool roundRobin = algorithm == "round_robin" || algorithm == "rr";
  if (roundRobin || !HasPositiveDemand(demand)) {
    for (uint32_t slot = 0; slot < frame_slots; ++slot) {
      AppendScheduleEntry(&schedule, BuildRoundRobinPermutation(radix, slot));
    }
    return schedule;
  }

  // The ns-3 integration maps solstice and bvn to deterministic demand-aware
  // max-weight matching. The standalone scheduler library retains the full
  // algorithm-specific implementations.
  std::vector<std::vector<double>> residual = demand;
  for (uint32_t slot = 0; slot < frame_slots; ++slot) {
    AppendScheduleEntry(&schedule,
                        BuildDemandAwarePermutation(&residual, slot));
  }
  return schedule;
}

namespace detail {

template <typename T, typename = void>
struct HasTagId : std::false_type {};

template <typename T>
struct HasTagId<T, std::void_t<decltype(std::declval<const T&>().tag_id)>>
    : std::true_type {};

template <typename T, typename = void>
struct HasCurrentFlowId : std::false_type {};

template <typename T>
struct HasCurrentFlowId<
    T, std::void_t<decltype(std::declval<const T&>().current_flow_id)>>
    : std::true_type {};

template <typename T, typename = void>
struct HasChunkId : std::false_type {};

template <typename T>
struct HasChunkId<T, std::void_t<decltype(std::declval<const T&>().chunk_id)>>
    : std::true_type {};

template <typename T, typename = void>
struct HasChannelId : std::false_type {};

template <typename T>
struct HasChannelId<T, std::void_t<decltype(std::declval<const T&>().channel_id)>>
    : std::true_type {};

template <typename TagT>
int ReadTagId(const TagT& tag) {
  if constexpr (HasTagId<TagT>::value) {
    return static_cast<int>(tag.tag_id);
  }
  return -1;
}

template <typename TagT>
int ReadCurrentFlowId(const TagT& tag) {
  if constexpr (HasCurrentFlowId<TagT>::value) {
    return static_cast<int>(tag.current_flow_id);
  }
  return -1;
}

template <typename TagT>
int ReadChunkId(const TagT& tag) {
  if constexpr (HasChunkId<TagT>::value) {
    return static_cast<int>(tag.chunk_id);
  } else if constexpr (HasChannelId<TagT>::value) {
    return static_cast<int>(tag.channel_id);
  }
  return -1;
}

}  // namespace detail

class GranularityController {
 public:
  GranularityController(GranularityMode mode = GranularityMode::OPERATOR,
                        uint32_t num_nodes = 0)
      : m_mode(mode),
        m_numNodes(num_nodes),
        m_hasLast(false),
        m_lastTagId(-1),
        m_lastFlowId(-1),
        m_lastChunkId(-1) {}

  template <typename TagT>
  void OnFlowStart(int src, int dst, uint64_t size, const TagT& tag) {
    (void)tag;
    if (src < 0 || dst < 0) {
      return;
    }
    const uint32_t srcNode = static_cast<uint32_t>(src);
    const uint32_t dstNode = static_cast<uint32_t>(dst);
    if (srcNode >= m_numNodes || dstNode >= m_numNodes) {
      return;
    }

    m_pendingDemand[std::make_pair(srcNode, dstNode)] +=
        static_cast<double>(size);
  }

  DemandMatrix BuildDemandMatrix() {
    DemandMatrix demand(m_numNodes, std::vector<double>(m_numNodes, 0.0));
    for (const auto& item : m_pendingDemand) {
      demand[item.first.first][item.first.second] = item.second;
    }
    m_pendingDemand.clear();
    return demand;
  }

  template <typename TagT>
  bool ShouldReschedule(const TagT& tag) {
    return ShouldRescheduleIds(detail::ReadTagId(tag),
                               detail::ReadCurrentFlowId(tag),
                               detail::ReadChunkId(tag));
  }

  template <typename TagT>
  bool ShouldReschedule(const TagT* tag) {
    if (tag == nullptr) {
      return ShouldReschedule(nullptr);
    }
    return ShouldReschedule(*tag);
  }

  bool ShouldReschedule(std::nullptr_t) {
    return ShouldRescheduleIds(-1, -1, -1);
  }

  void Reset() {
    m_pendingDemand.clear();
    m_hasLast = false;
    m_lastTagId = -1;
    m_lastFlowId = -1;
    m_lastChunkId = -1;
  }

 private:
  bool AllTagFieldsInvalid(int tag_id, int flow_id, int chunk_id) const {
    return tag_id < 0 && flow_id < 0 && chunk_id < 0;
  }

  bool ShouldRescheduleIds(int tag_id, int flow_id, int chunk_id) {
    if (m_mode == GranularityMode::PACKET) {
      UpdateLastIds(tag_id, flow_id, chunk_id);
      return true;
    }
    if (m_mode == GranularityMode::SLOT) {
      UpdateLastIds(tag_id, flow_id, chunk_id);
      return false;
    }
    if (AllTagFieldsInvalid(tag_id, flow_id, chunk_id)) {
      return false;
    }

    bool changed = !m_hasLast;
    if (!changed) {
      switch (m_mode) {
        case GranularityMode::OPERATOR:
          changed = tag_id != m_lastTagId;
          break;
        case GranularityMode::PHASE:
          changed = tag_id != m_lastTagId || flow_id != m_lastFlowId;
          break;
        case GranularityMode::CHUNK:
          changed = tag_id != m_lastTagId || flow_id != m_lastFlowId ||
                    chunk_id != m_lastChunkId;
          break;
        case GranularityMode::PACKET:
        case GranularityMode::SLOT:
          break;
      }
    }

    UpdateLastIds(tag_id, flow_id, chunk_id);
    return changed;
  }

  void UpdateLastIds(int tag_id, int flow_id, int chunk_id) {
    m_hasLast = true;
    m_lastTagId = tag_id;
    m_lastFlowId = flow_id;
    m_lastChunkId = chunk_id;
  }

  GranularityMode m_mode;
  uint32_t m_numNodes;
  bool m_hasLast;
  int m_lastTagId;
  int m_lastFlowId;
  int m_lastChunkId;
  std::map<std::pair<uint32_t, uint32_t>, double> m_pendingDemand;
};

}  // namespace calendar

#endif  // GRANULARITY_CONTROLLER_H
