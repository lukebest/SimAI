#ifndef CALENDAR_SCHEDULER_SOLSTICE_SCHEDULER_H_
#define CALENDAR_SCHEDULER_SOLSTICE_SCHEDULER_H_

#include <cstdint>
#include <vector>

#include "calendar_scheduler.h"

namespace calendar {

class SolsticeScheduler : public SchedulerBase {
 public:
  explicit SolsticeScheduler(uint32_t frame_slots = 1024,
                             uint32_t max_iterations = 64)
      : SchedulerBase(frame_slots), max_iterations_(max_iterations) {}

  Schedule compute(const DemandMatrix& demand) override;

 private:
  static std::vector<uint32_t> max_weight_matching(const DemandMatrix& residual,
                                                   uint32_t n);

  uint32_t max_iterations_;
};

}  // namespace calendar

#endif  // CALENDAR_SCHEDULER_SOLSTICE_SCHEDULER_H_
