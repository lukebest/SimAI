#ifndef CALENDAR_SCHEDULER_CALENDAR_SCHEDULER_H_
#define CALENDAR_SCHEDULER_CALENDAR_SCHEDULER_H_

#include <cstddef>
#include <cstdint>
#include <numeric>
#include <vector>

namespace calendar {

using DemandMatrix = std::vector<std::vector<double>>;

struct ScheduleEntry {
  std::vector<uint32_t> permutation;
  uint32_t slots = 0;
};

struct Schedule {
  std::vector<ScheduleEntry> entries;

  uint32_t total_slots() const {
    uint32_t total = 0;
    for (const auto& entry : entries) {
      total += entry.slots;
    }
    return total;
  }
};

class SchedulerBase {
 public:
  explicit SchedulerBase(uint32_t frame_slots) : frame_slots_(frame_slots) {}
  virtual ~SchedulerBase() = default;

  virtual Schedule compute(const DemandMatrix& demand) = 0;

 protected:
  uint32_t frame_slots() const { return frame_slots_; }

  static bool is_square_matrix(const DemandMatrix& demand) {
    const std::size_t n = demand.size();
    for (const auto& row : demand) {
      if (row.size() != n) {
        return false;
      }
    }
    return true;
  }

  static uint32_t matrix_size(const DemandMatrix& demand) {
    if (!is_square_matrix(demand)) {
      return 0;
    }
    return static_cast<uint32_t>(demand.size());
  }

  static double total_demand(const DemandMatrix& demand) {
    if (!is_square_matrix(demand)) {
      return 0.0;
    }
    double total = 0.0;
    for (const auto& row : demand) {
      total = std::accumulate(row.begin(), row.end(), total);
    }
    return total;
  }

 private:
  uint32_t frame_slots_;
};

}  // namespace calendar

#endif  // CALENDAR_SCHEDULER_CALENDAR_SCHEDULER_H_
