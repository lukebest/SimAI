#include "bvn_scheduler.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>

namespace calendar {
namespace {

double residual_total(const DemandMatrix& residual) {
  double total = 0.0;
  for (const auto& row : residual) {
    total = std::accumulate(row.begin(), row.end(), total);
  }
  return total;
}

bool is_identity(const std::vector<uint32_t>& permutation) {
  for (uint32_t row = 0; row < permutation.size(); ++row) {
    if (permutation[row] != row) {
      return false;
    }
  }
  return true;
}

DemandMatrix normalized_demand(const DemandMatrix& demand,
                               uint32_t sinkhorn_iterations,
                               double tolerance) {
  const uint32_t n = static_cast<uint32_t>(demand.size());
  DemandMatrix residual(n, std::vector<double>(n, 0.0));
  for (uint32_t row = 0; row < n; ++row) {
    for (uint32_t column = 0; column < n; ++column) {
      if (row != column) {
        residual[row][column] = std::max(0.0, demand[row][column]);
      }
    }
  }

  if (residual_total(residual) <= tolerance) {
    return residual;
  }

  for (uint32_t iter = 0; iter < sinkhorn_iterations; ++iter) {
    for (uint32_t row = 0; row < n; ++row) {
      const double row_sum =
          std::accumulate(residual[row].begin(), residual[row].end(), 0.0);
      if (row_sum > tolerance) {
        for (uint32_t column = 0; column < n; ++column) {
          residual[row][column] /= row_sum;
        }
      }
    }

    for (uint32_t column = 0; column < n; ++column) {
      double col_sum = 0.0;
      for (uint32_t row = 0; row < n; ++row) {
        col_sum += residual[row][column];
      }
      if (col_sum > tolerance) {
        for (uint32_t row = 0; row < n; ++row) {
          residual[row][column] /= col_sum;
        }
      }
    }

    double max_error = 0.0;
    for (uint32_t row = 0; row < n; ++row) {
      const double row_sum =
          std::accumulate(residual[row].begin(), residual[row].end(), 0.0);
      max_error = std::max(max_error, std::abs(row_sum - 1.0));
    }
    for (uint32_t column = 0; column < n; ++column) {
      double col_sum = 0.0;
      for (uint32_t row = 0; row < n; ++row) {
        col_sum += residual[row][column];
      }
      max_error = std::max(max_error, std::abs(col_sum - 1.0));
    }
    if (max_error <= tolerance) {
      break;
    }
  }

  for (uint32_t row = 0; row < n; ++row) {
    for (uint32_t column = 0; column < n; ++column) {
      if (residual[row][column] < tolerance) {
        residual[row][column] = 0.0;
      }
    }
  }
  return residual;
}

}  // namespace

std::vector<uint32_t> BvNScheduler::max_weight_matching(
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

std::pair<std::vector<uint32_t>,
          std::vector<std::pair<uint32_t, uint32_t>>>
BvNScheduler::active_matching(const DemandMatrix& residual, double tolerance) {
  const uint32_t n = static_cast<uint32_t>(residual.size());
  std::vector<uint32_t> active_rows;
  std::vector<uint32_t> active_columns;

  for (uint32_t row = 0; row < n; ++row) {
    if (*std::max_element(residual[row].begin(), residual[row].end()) >
        tolerance) {
      active_rows.push_back(row);
    }
  }

  for (uint32_t column = 0; column < n; ++column) {
    double max_column_weight = 0.0;
    for (uint32_t row = 0; row < n; ++row) {
      max_column_weight = std::max(max_column_weight, residual[row][column]);
    }
    if (max_column_weight > tolerance) {
      active_columns.push_back(column);
    }
  }

  std::vector<uint32_t> permutation(n, 0);
  std::iota(permutation.begin(), permutation.end(), 0);
  std::vector<std::pair<uint32_t, uint32_t>> matched_edges;
  if (active_rows.empty() || active_columns.empty()) {
    return {permutation, matched_edges};
  }

  const uint32_t matching_size = std::max(
      static_cast<uint32_t>(active_rows.size()),
      static_cast<uint32_t>(active_columns.size()));
  DemandMatrix matching_weights(matching_size,
                                std::vector<double>(matching_size, 0.0));
  const double cardinality_bonus = residual_total(residual) + 1.0;
  for (uint32_t local_row = 0; local_row < active_rows.size(); ++local_row) {
    const uint32_t row = active_rows[local_row];
    for (uint32_t local_column = 0; local_column < active_columns.size();
         ++local_column) {
      const uint32_t column = active_columns[local_column];
      const double edge_weight = residual[row][column];
      if (edge_weight > tolerance) {
        matching_weights[local_row][local_column] =
            cardinality_bonus + edge_weight;
      }
    }
  }

  const std::vector<uint32_t> local_permutation =
      max_weight_matching(matching_weights, matching_size);
  std::fill(permutation.begin(), permutation.end(), n);
  std::vector<bool> used_columns(n, false);
  for (uint32_t local_row = 0; local_row < active_rows.size(); ++local_row) {
    const uint32_t local_column = local_permutation[local_row];
    if (local_column >= active_columns.size()) {
      continue;
    }

    const uint32_t row = active_rows[local_row];
    const uint32_t column = active_columns[local_column];
    if (residual[row][column] <= tolerance) {
      continue;
    }

    permutation[row] = column;
    used_columns[column] = true;
    matched_edges.push_back({row, column});
  }

  std::vector<uint32_t> unused_columns;
  for (uint32_t column = 0; column < n; ++column) {
    if (!used_columns[column]) {
      unused_columns.push_back(column);
    }
  }

  uint32_t next_unused = 0;
  for (uint32_t row = 0; row < n; ++row) {
    if (permutation[row] == n) {
      permutation[row] = unused_columns[next_unused++];
    }
  }

  return {permutation, matched_edges};
}

Schedule BvNScheduler::compute(const DemandMatrix& demand) {
  Schedule schedule;
  if (!is_square_matrix(demand)) {
    return schedule;
  }

  const uint32_t n = matrix_size(demand);
  if (n <= 1 || frame_slots() == 0) {
    return schedule;
  }

  DemandMatrix residual =
      normalized_demand(demand, sinkhorn_iterations_, tolerance_);
  if (residual_total(residual) <= tolerance_) {
    return schedule;
  }

  uint32_t remaining_slots = frame_slots();
  const uint32_t iteration_limit =
      max_iterations_ == 0 ? std::max(frame_slots(), n * n * 4)
                           : max_iterations_;
  for (uint32_t iter = 0; iter < iteration_limit; ++iter) {
    if (remaining_slots == 0 || residual_total(residual) <= tolerance_) {
      break;
    }

    const auto matching = active_matching(residual, tolerance_);
    const std::vector<uint32_t>& permutation = matching.first;
    const std::vector<std::pair<uint32_t, uint32_t>>& matched_edges =
        matching.second;
    if (matched_edges.empty()) {
      break;
    }

    double weight = std::numeric_limits<double>::infinity();
    for (const auto& edge : matched_edges) {
      weight = std::min(weight, residual[edge.first][edge.second]);
    }
    if (!std::isfinite(weight) || weight <= tolerance_) {
      break;
    }

    for (const auto& edge : matched_edges) {
      residual[edge.first][edge.second] =
          std::max(0.0, residual[edge.first][edge.second] - weight);
    }

    for (uint32_t row = 0; row < n; ++row) {
      for (uint32_t column = 0; column < n; ++column) {
        if (residual[row][column] < tolerance_) {
          residual[row][column] = 0.0;
        }
      }
    }

    if (is_identity(permutation)) {
      continue;
    }

    uint32_t slots = std::max(
        1u, static_cast<uint32_t>(std::floor(weight * frame_slots() + 0.5)));
    slots = std::min(slots, remaining_slots);
    schedule.entries.push_back({permutation, slots});
    remaining_slots -= slots;
  }

  return schedule;
}

}  // namespace calendar
