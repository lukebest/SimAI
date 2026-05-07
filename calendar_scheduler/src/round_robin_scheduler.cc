#include "round_robin_scheduler.h"

namespace calendar {

Schedule RoundRobinScheduler::compute(const DemandMatrix& demand) {
  Schedule schedule;
  const uint32_t n = matrix_size(demand);
  if (n <= 1 || total_demand(demand) == 0.0) {
    return schedule;
  }

  const uint32_t useful_rotations = n - 1;
  const uint32_t base_slots = frame_slots() / useful_rotations;
  const uint32_t remainder = frame_slots() % useful_rotations;

  schedule.entries.reserve(useful_rotations);
  for (uint32_t rotation = 1; rotation < n; ++rotation) {
    ScheduleEntry entry;
    entry.permutation.reserve(n);
    entry.slots = base_slots + (rotation <= remainder ? 1 : 0);

    for (uint32_t input = 0; input < n; ++input) {
      entry.permutation.push_back((input + rotation) % n);
    }

    schedule.entries.push_back(entry);
  }

  return schedule;
}

}  // namespace calendar
