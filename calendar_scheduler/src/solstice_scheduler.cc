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

uint32_t count_bits(uint64_t value) {
  uint32_t count = 0;
  while (value != 0) {
    count += static_cast<uint32_t>(value & 1u);
    value >>= 1u;
  }
  return count;
}

std::vector<uint32_t> greedy_matching(const DemandMatrix& residual, uint32_t n) {
  struct Cell {
    double weight;
    uint32_t row;
    uint32_t column;
  };

  std::vector<Cell> cells;
  cells.reserve(static_cast<std::size_t>(n) * n);
  for (uint32_t row = 0; row < n; ++row) {
    for (uint32_t column = 0; column < n; ++column) {
      if (residual[row][column] > 0.0) {
        cells.push_back({residual[row][column], row, column});
      }
    }
  }

  std::sort(cells.begin(), cells.end(), [](const Cell& lhs, const Cell& rhs) {
    if (lhs.weight != rhs.weight) {
      return lhs.weight > rhs.weight;
    }
    if (lhs.row != rhs.row) {
      return lhs.row < rhs.row;
    }
    return lhs.column < rhs.column;
  });

  std::vector<uint32_t> permutation(n, std::numeric_limits<uint32_t>::max());
  std::vector<bool> used_columns(n, false);
  uint32_t used_count = 0;

  for (const Cell& cell : cells) {
    if (permutation[cell.row] != std::numeric_limits<uint32_t>::max() ||
        used_columns[cell.column]) {
      continue;
    }
    permutation[cell.row] = cell.column;
    used_columns[cell.column] = true;
    ++used_count;
    if (used_count == n) {
      break;
    }
  }

  std::vector<uint32_t> remaining_columns;
  remaining_columns.reserve(n - used_count);
  for (uint32_t column = 0; column < n; ++column) {
    if (!used_columns[column]) {
      remaining_columns.push_back(column);
    }
  }

  std::size_t next_remaining = 0;
  for (uint32_t row = 0; row < n; ++row) {
    if (permutation[row] == std::numeric_limits<uint32_t>::max()) {
      permutation[row] = remaining_columns[next_remaining];
      ++next_remaining;
    }
  }

  return permutation;
}

}  // namespace

std::vector<uint32_t> SolsticeScheduler::max_weight_matching(
    const DemandMatrix& residual, uint32_t n) {
  if (n > 20) {
    // Bitmask DP is exponential; large exploratory runs keep a deterministic
    // fallback rather than exhausting memory.
    return greedy_matching(residual, n);
  }

  const uint64_t state_count = 1ull << n;
  std::vector<double> scores(state_count,
                             -std::numeric_limits<double>::infinity());
  std::vector<int32_t> parent_columns(state_count, -1);
  std::vector<uint64_t> parent_masks(state_count, 0);
  scores[0] = 0.0;

  for (uint64_t mask = 0; mask < state_count; ++mask) {
    const uint32_t row = count_bits(mask);
    if (row >= n || scores[mask] == -std::numeric_limits<double>::infinity()) {
      continue;
    }

    for (uint32_t column = 0; column < n; ++column) {
      const uint64_t column_mask = 1ull << column;
      if ((mask & column_mask) != 0) {
        continue;
      }

      const uint64_t next_mask = mask | column_mask;
      const double candidate = scores[mask] + residual[row][column];
      if (candidate > scores[next_mask] + 1e-12) {
        scores[next_mask] = candidate;
        parent_columns[next_mask] = static_cast<int32_t>(column);
        parent_masks[next_mask] = mask;
      }
    }
  }

  std::vector<uint32_t> permutation(n, 0);
  uint64_t mask = state_count - 1;
  for (uint32_t reverse_row = 0; reverse_row < n; ++reverse_row) {
    const uint32_t row = n - reverse_row - 1;
    permutation[row] = static_cast<uint32_t>(parent_columns[mask]);
    mask = parent_masks[mask];
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
