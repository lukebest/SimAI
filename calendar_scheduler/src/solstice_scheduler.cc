#include "solstice_scheduler.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>

namespace calendar {
namespace {

constexpr double kEpsilon = 1e-9;

double residual_total(const DemandMatrix& residual) {
  double total = 0.0;
  for (const auto& row : residual) {
    total = std::accumulate(row.begin(), row.end(), total);
  }
  return total;
}

}  // namespace

std::vector<uint32_t> SolsticeScheduler::max_weight_matching(
    const DemandMatrix& residual, uint32_t n) {
  double max_weight = residual[0][0];
  for (uint32_t row = 0; row < n; ++row) {
    for (uint32_t column = 0; column < n; ++column) {
      max_weight = std::max(max_weight, residual[row][column]);
    }
  }

  DemandMatrix costs(n, std::vector<double>(n, 0.0));
  for (uint32_t row = 0; row < n; ++row) {
    for (uint32_t column = 0; column < n; ++column) {
      costs[row][column] = max_weight - residual[row][column];
    }
  }

  std::vector<double> potentials_rows(n + 1, 0.0);
  std::vector<double> potentials_cols(n + 1, 0.0);
  std::vector<uint32_t> matched_rows(n + 1, 0);
  std::vector<uint32_t> previous_cols(n + 1, 0);

  for (uint32_t row = 1; row <= n; ++row) {
    matched_rows[0] = row;
    uint32_t col0 = 0;
    std::vector<double> min_values(n + 1,
                                   std::numeric_limits<double>::infinity());
    std::vector<bool> used_cols(n + 1, false);

    while (true) {
      used_cols[col0] = true;
      const uint32_t row0 = matched_rows[col0];
      double delta = std::numeric_limits<double>::infinity();
      uint32_t col1 = 0;

      for (uint32_t col = 1; col <= n; ++col) {
        if (used_cols[col]) {
          continue;
        }
        const double current = costs[row0 - 1][col - 1] -
                               potentials_rows[row0] - potentials_cols[col];
        if (current < min_values[col]) {
          min_values[col] = current;
          previous_cols[col] = col0;
        }
        if (min_values[col] < delta) {
          delta = min_values[col];
          col1 = col;
        }
      }

      for (uint32_t col = 0; col <= n; ++col) {
        if (used_cols[col]) {
          potentials_rows[matched_rows[col]] += delta;
          potentials_cols[col] -= delta;
        } else {
          min_values[col] -= delta;
        }
      }

      col0 = col1;
      if (matched_rows[col0] == 0) {
        break;
      }
    }

    while (true) {
      const uint32_t col1 = previous_cols[col0];
      matched_rows[col0] = matched_rows[col1];
      col0 = col1;
      if (col0 == 0) {
        break;
      }
    }
  }

  std::vector<uint32_t> permutation(n, 0);
  for (uint32_t col = 1; col <= n; ++col) {
    permutation[matched_rows[col] - 1] = col - 1;
  }

  return permutation;
}

Schedule SolsticeScheduler::compute(const DemandMatrix& demand) {
  Schedule schedule;
  if (!is_square_matrix(demand)) {
    return schedule;
  }

  const uint32_t n = matrix_size(demand);
  const double original_total_demand = total_demand(demand);
  if (n <= 1 || frame_slots() == 0 || original_total_demand <= 0.0) {
    return schedule;
  }

  DemandMatrix residual = demand;
  uint32_t remaining_slots = frame_slots();

  for (uint32_t iter = 0; iter < max_iterations_; ++iter) {
    if (remaining_slots == 0 || residual_total(residual) <= kEpsilon) {
      break;
    }

    std::vector<uint32_t> permutation = max_weight_matching(residual, n);
    double matching_weight = 0.0;
    for (uint32_t row = 0; row < n; ++row) {
      matching_weight += std::max(0.0, residual[row][permutation[row]]);
    }
    if (matching_weight <= kEpsilon) {
      break;
    }

    const double slot_fraction = matching_weight / original_total_demand;
    uint32_t slots = std::max(
        1u, static_cast<uint32_t>(std::llround(slot_fraction * frame_slots())));
    slots = std::min(slots, remaining_slots);

    const double served_fraction =
        static_cast<double>(slots) /
        std::max(1.0, static_cast<double>(frame_slots()) * slot_fraction);
    for (uint32_t row = 0; row < n; ++row) {
      const uint32_t column = permutation[row];
      if (residual[row][column] > 0.0) {
        residual[row][column] =
            std::max(0.0, residual[row][column] * (1.0 - served_fraction));
      }
    }

    schedule.entries.push_back({permutation, slots});
    remaining_slots -= slots;
  }

  return schedule;
}

}  // namespace calendar
