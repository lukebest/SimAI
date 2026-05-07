#ifndef CALENDAR_SCHEDULER_ROUND_ROBIN_SCHEDULER_H_
#define CALENDAR_SCHEDULER_ROUND_ROBIN_SCHEDULER_H_

#include "calendar_scheduler.h"

namespace calendar {

class RoundRobinScheduler : public SchedulerBase {
 public:
  explicit RoundRobinScheduler(uint32_t frame_slots = 1024)
      : SchedulerBase(frame_slots) {}

  Schedule compute(const DemandMatrix& demand) override;
};

}  // namespace calendar

#endif  // CALENDAR_SCHEDULER_ROUND_ROBIN_SCHEDULER_H_
