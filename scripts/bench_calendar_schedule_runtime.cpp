#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "../astra-sim-alibabacloud/astra-sim/network_frontend/ns3/granularity_controller.h"

namespace {

calendar::DemandMatrix MakeDenseDemand(uint32_t n, double weight) {
  calendar::DemandMatrix d(n, std::vector<double>(n, 0.0));
  for (uint32_t i = 0; i < n; ++i) {
    for (uint32_t j = 0; j < n; ++j) {
      if (i != j) {
        d[i][j] = weight;
      }
    }
  }
  return d;
}

calendar::DemandMatrix MakeRingDemand(uint32_t n, double weight) {
  calendar::DemandMatrix d(n, std::vector<double>(n, 0.0));
  for (uint32_t i = 0; i < n; ++i) {
    const uint32_t j = (i + 1) % n;
    d[i][j] = weight;
  }
  return d;
}

double BenchOne(const calendar::DemandMatrix& demand, const std::string& algo,
                uint32_t frame_slots, uint32_t iters) {
  auto start = std::chrono::steady_clock::now();
  uint64_t entries_sum = 0;
  for (uint32_t i = 0; i < iters; ++i) {
    auto schedule = calendar::BuildCalendarSchedule(demand, algo, frame_slots);
    entries_sum += schedule.entries.size();
  }
  auto end = std::chrono::steady_clock::now();
  const double total_us =
      std::chrono::duration_cast<std::chrono::duration<double, std::micro>>(
          end - start)
          .count();
  // Prevent optimizer from removing the loop.
  volatile uint64_t sink = entries_sum;
  (void)sink;
  return total_us / static_cast<double>(iters);
}

}  // namespace

int main() {
  const uint32_t n = 8;
  const uint32_t frame_slots = 1024;
  const uint32_t iters = 5000;

  const auto dense = MakeDenseDemand(n, 1.0);
  const auto ring = MakeRingDemand(n, 1.0);

  std::cout << "algo,pattern,avg_build_us\n";
  std::cout << "bvn,dense8x8," << BenchOne(dense, "bvn", frame_slots, iters)
            << "\n";
  std::cout << "solstice,dense8x8,"
            << BenchOne(dense, "solstice", frame_slots, iters) << "\n";
  std::cout << "bvn,ring8," << BenchOne(ring, "bvn", frame_slots, iters)
            << "\n";
  std::cout << "solstice,ring8," << BenchOne(ring, "solstice", frame_slots, iters)
            << "\n";
  return 0;
}
