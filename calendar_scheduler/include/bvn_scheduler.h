#ifndef CALENDAR_SCHEDULER_BVN_SCHEDULER_H_
#define CALENDAR_SCHEDULER_BVN_SCHEDULER_H_

#include <cstdint>
#include <vector>

#include "calendar_scheduler.h"

namespace calendar {

class BvNScheduler : public SchedulerBase {
 public:
  explicit BvNScheduler(uint32_t frame_slots = 1024,
                        uint32_t max_iterations = 64,
                        uint32_t sinkhorn_iterations = 1000,
                        double tolerance = 1e-9)
      : SchedulerBase(frame_slots),
        max_iterations_(max_iterations),
        sinkhorn_iterations_(sinkhorn_iterations),
        tolerance_(tolerance) {}

  Schedule compute(const DemandMatrix& demand) override;

 private:
  static std::vector<uint32_t> max_weight_matching(const DemandMatrix& residual,
                                                   uint32_t n);

  uint32_t max_iterations_;
  uint32_t sinkhorn_iterations_;
  double tolerance_;
};

}  // namespace calendar

#endif  // CALENDAR_SCHEDULER_BVN_SCHEDULER_H_
