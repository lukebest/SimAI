/* 
*Copyright (c) 2024, Alibaba Group;
*Licensed under the Apache License, Version 2.0 (the "License");
*you may not use this file except in compliance with the License.
*You may obtain a copy of the License at

*   http://www.apache.org/licenses/LICENSE-2.0

*Unless required by applicable law or agreed to in writing, software
*distributed under the License is distributed on an "AS IS" BASIS,
*WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
*See the License for the specific language governing permissions and
*limitations under the License.
*/

#ifndef __ENTRY_H__
#define __ENTRY_H__

#undef PGO_TRAINING
#define PATH_TO_PGO_CONFIG "path_to_pgo_config"
#define _QPS_PER_CONNECTION_  1
#include "common.h"
#include "granularity_controller.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/error-model.h"
#include "ns3/global-route-manager.h"
#include "ns3/internet-module.h"
#include "ns3/ipv4-static-routing-helper.h"
#include "ns3/packet.h"
#include "ns3/point-to-point-helper.h"
#include "ns3/qbb-helper.h"
#include <algorithm>
#include <cctype>
#include <fstream>
#include <iostream>
#include <memory>
#include <fstream>
#include <ns3/rdma-client-helper.h>
#include <ns3/rdma-client.h>
#include <ns3/rdma-driver.h>
#include <ns3/rdma.h>
#include <ns3/sim-setting.h>
#include <ns3/switch-node.h>
#include <time.h>
#include <unordered_map>
#include <mutex>
#include <vector>
#ifdef NS3_MTP
#include "ns3/mtp-interface.h"
#endif
#include <map>
#include"astra-sim/system/MockNcclQps.h"
#include "astra-sim/system/MockNcclLog.h"
using namespace ns3;
using namespace std;


std::map<std::pair<std::pair<int, int>,int>, AstraSim::ncclFlowTag> receiver_pending_queue;


std::map<std::pair<int, std::pair<int, int>>, AstraSim::ncclFlowTag> sender_src_port_map; 
std::unique_ptr<calendar::GranularityController> g_granularity_controller;
std::ofstream g_switch_metrics_trace;
bool g_switch_metrics_header_written = false;
bool g_switch_metrics_polling_started = false;
std::unordered_map<uint32_t, std::pair<uint64_t, uint64_t>> g_last_switch_admission_counters;
constexpr uint32_t kSwitchPortCount = 1025;
constexpr uint32_t kSwitchQueueCount = 8;
std::map<std::pair<uint32_t, uint32_t>, double> g_calendar_outstanding_demand;
uint64_t g_watchdog_last_allowed = 0;
uint64_t g_watchdog_last_blocked = 0;
bool g_calendar_watchdog_started = false;
enum class CalendarRecomputePolicy { DYNAMIC, STATIC_OPERATOR, STATIC_PHASE };
bool g_calendar_policy_initialized = false;
CalendarRecomputePolicy g_calendar_recompute_policy = CalendarRecomputePolicy::DYNAMIC;
bool g_static_operator_schedule_loaded = false;
int g_static_phase_last_chunk = -1;
bool g_calendar_static_pattern_initialized = false;
std::string g_calendar_static_pattern = "demand_fallback";
ns3::CalendarSchedule g_active_calendar_schedule;
bool g_active_calendar_schedule_valid = false;

inline void AppendFlowTimingTrace(const std::string& event,
                                  int src,
                                  int dst,
                                  int tag_id,
                                  int flow_id,
                                  int chunk_id,
                                  int sport,
                                  uint64_t aux_ns) {
  if (calendar_trace_enable == 0 || calendar_trace_file.empty()) {
    return;
  }
  static std::ofstream trace;
  static bool header_written = false;
  if (!trace.is_open()) {
    trace.open(calendar_trace_file + ".flow_timing.csv",
               std::ios::out | std::ios::app);
    if (!trace.is_open()) {
      return;
    }
  }
  if (!header_written) {
    trace << "sim_ns,event,src,dst,tag_id,flow_id,chunk_id,sport,aux_ns\n";
    header_written = true;
  }
  trace << Simulator::Now().GetNanoSeconds() << ","
        << event << ","
        << src << ","
        << dst << ","
        << tag_id << ","
        << flow_id << ","
        << chunk_id << ","
        << sport << ","
        << aux_ns << "\n";
  trace.flush();
}

inline void AppendCalendarTrace(const std::string& event,
                                int src,
                                int dst,
                                int tag_id,
                                int flow_id,
                                int chunk_id,
                                double demand_sum,
                                size_t schedule_entries,
                                uint32_t applied_switches) {
  if (calendar_trace_enable == 0 || calendar_trace_file.empty()) {
    return;
  }
  static std::ofstream trace;
  static bool header_written = false;
  if (!trace.is_open()) {
    trace.open(calendar_trace_file, std::ios::out | std::ios::app);
    if (!trace.is_open()) {
      return;
    }
  }
  if (!header_written) {
    trace << "sim_ns,event,src,dst,tag_id,flow_id,chunk_id,demand_sum,schedule_entries,applied_switches\n";
    header_written = true;
  }
  trace << Simulator::Now().GetNanoSeconds() << ","
        << event << ","
        << src << ","
        << dst << ","
        << tag_id << ","
        << flow_id << ","
        << chunk_id << ","
        << demand_sum << ","
        << schedule_entries << ","
        << applied_switches << "\n";
  trace.flush();
}
inline void EnsureGranularityController(uint32_t num_nodes) {
  if (g_granularity_controller) {
    g_granularity_controller->EnsureNumNodes(num_nodes);
    return;
  }
  if (num_nodes == 0) {
    num_nodes = 1;
  }
  g_granularity_controller = std::make_unique<calendar::GranularityController>(
      calendar::ParseGranularityMode(calendar_granularity_mode), num_nodes);
}

inline CalendarRecomputePolicy ParseCalendarRecomputePolicy(const std::string& policy) {
  std::string normalized = policy;
  std::transform(
      normalized.begin(), normalized.end(), normalized.begin(),
      [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (normalized == "static_operator" || normalized == "operator_static" ||
      normalized == "static") {
    return CalendarRecomputePolicy::STATIC_OPERATOR;
  }
  if (normalized == "static_phase" || normalized == "phase_static") {
    return CalendarRecomputePolicy::STATIC_PHASE;
  }
  return CalendarRecomputePolicy::DYNAMIC;
}

inline CalendarRecomputePolicy GetCalendarRecomputePolicy() {
  if (!g_calendar_policy_initialized) {
    g_calendar_recompute_policy =
        ParseCalendarRecomputePolicy(calendar_recompute_policy);
    g_calendar_policy_initialized = true;
  }
  return g_calendar_recompute_policy;
}

inline uint32_t CountTrafficEndpoints();
inline void StartCalendarStallWatchdog();

inline std::string NormalizeToken(const std::string& value) {
  std::string normalized = value;
  std::transform(
      normalized.begin(), normalized.end(), normalized.begin(),
      [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  return normalized;
}

inline const std::string& GetCalendarStaticPattern() {
  if (!g_calendar_static_pattern_initialized) {
    g_calendar_static_pattern = NormalizeToken(calendar_static_pattern);
    if (g_calendar_static_pattern.empty()) {
      g_calendar_static_pattern = "demand_fallback";
    }
    g_calendar_static_pattern_initialized = true;
  }
  return g_calendar_static_pattern;
}

inline ns3::CalendarSchedule BuildStaticCalendarSchedule(uint32_t radix) {
  ns3::CalendarSchedule schedule;
  if (radix == 0 || calendar_frame_slots == 0) {
    return schedule;
  }
  ns3::CalendarScheduleEntry entry;
  entry.permutation.resize(radix);
  for (uint32_t in = 0; in < radix; ++in) {
    entry.permutation[in] = (in + 1) % radix;
  }
  entry.slots = calendar_frame_slots;
  schedule.entries.push_back(entry);
  return schedule;
}

inline uint64_t EstimateIngressArrivalNs(uint32_t src, uint32_t dst, uint64_t base_send_ns) {
  if (src >= n.GetN() || dst >= n.GetN()) {
    return base_send_ns;
  }
  Ptr<Node> src_node = n.Get(src);
  Ptr<Node> dst_node = n.Get(dst);
  uint64_t total_delay = 0;
  uint64_t total_tx_delay = 0;
  if (pairDelay[src_node].count(dst_node) > 0) {
    total_delay = pairDelay[src_node][dst_node];
  }
  if (pairTxDelay[src_node].count(dst_node) > 0) {
    total_tx_delay = pairTxDelay[src_node][dst_node];
  }
  const uint64_t one_hop_budget = std::max<uint64_t>(1, (total_delay + total_tx_delay) / 2);
  return base_send_ns + one_hop_budget;
}

inline uint64_t ComputeScheduleAwareSendTimeNs(uint32_t src, uint32_t dst, uint64_t base_send_ns) {
  if (!g_active_calendar_schedule_valid || g_active_calendar_schedule.entries.empty() ||
      calendar_slot_ns == 0 || calendar_frame_slots == 0) {
    return base_send_ns;
  }
  uint32_t host_radix = CountTrafficEndpoints();
  if (src >= host_radix || dst >= host_radix) {
    return base_send_ns;
  }
  std::vector<uint32_t> allowed_slots;
  allowed_slots.reserve(calendar_frame_slots);
  uint32_t slot_cursor = 0;
  for (const auto& entry : g_active_calendar_schedule.entries) {
    bool match = false;
    if (src < entry.permutation.size() && dst < entry.permutation.size()) {
      match = entry.permutation[src] == dst;
    }
    for (uint32_t i = 0; i < entry.slots && slot_cursor < calendar_frame_slots; ++i) {
      if (match) {
        allowed_slots.push_back(slot_cursor);
      }
      slot_cursor++;
    }
    if (slot_cursor >= calendar_frame_slots) {
      break;
    }
  }
  if (allowed_slots.empty()) {
    return base_send_ns;
  }

  const uint64_t frame_ns =
      static_cast<uint64_t>(calendar_slot_ns) * static_cast<uint64_t>(calendar_frame_slots);
  if (frame_ns == 0) {
    return base_send_ns;
  }
  const uint64_t now_ns = static_cast<uint64_t>(Simulator::Now().GetNanoSeconds());
  const uint64_t ingress_arrival_ns = EstimateIngressArrivalNs(src, dst, base_send_ns);
  const uint64_t earliest_arrival_ns = std::max(now_ns + 1, ingress_arrival_ns);

  uint64_t frame_base = (earliest_arrival_ns / frame_ns) * frame_ns;
  while (true) {
    const uint64_t offset_ns = earliest_arrival_ns - frame_base;
    const uint32_t current_slot = static_cast<uint32_t>(offset_ns / calendar_slot_ns);
    for (uint32_t slot : allowed_slots) {
      if (slot >= current_slot) {
        const uint64_t target_arrival_ns =
            frame_base + static_cast<uint64_t>(slot) * static_cast<uint64_t>(calendar_slot_ns) +
            static_cast<uint64_t>(calendar_slot_ns / 4);
        if (target_arrival_ns > ingress_arrival_ns) {
          const uint64_t ingress_budget = ingress_arrival_ns - base_send_ns;
          return target_arrival_ns > ingress_budget
                     ? (target_arrival_ns - ingress_budget)
                     : base_send_ns;
        }
      }
    }
    frame_base += frame_ns;
  }
}

inline uint32_t CountTrafficEndpoints() {
  uint32_t endpoints = 0;
  for (uint32_t nodeIndex = 0; nodeIndex < n.GetN(); ++nodeIndex) {
    if (n.Get(nodeIndex)->GetNodeType() == 0) {
      endpoints++;
    }
  }
  return std::max(1u, endpoints);
}

inline double SumOutstandingCalendarDemand() {
  double total = 0.0;
  for (const auto& kv : g_calendar_outstanding_demand) {
    if (kv.second > 0.0) {
      total += kv.second;
    }
  }
  return total;
}

inline void AddOutstandingCalendarDemand(int src, int dst, uint64_t bytes) {
  if (src < 0 || dst < 0 || bytes == 0) {
    return;
  }
  g_calendar_outstanding_demand[std::make_pair(static_cast<uint32_t>(src),
                                                static_cast<uint32_t>(dst))] +=
      static_cast<double>(bytes);
}

inline void ConsumeOutstandingCalendarDemand(uint32_t src, uint32_t dst,
                                             uint64_t bytes) {
  if (bytes == 0) {
    return;
  }
  const auto key = std::make_pair(src, dst);
  const auto it = g_calendar_outstanding_demand.find(key);
  if (it == g_calendar_outstanding_demand.end()) {
    return;
  }
  const double remain = it->second - static_cast<double>(bytes);
  if (remain <= 0.0) {
    g_calendar_outstanding_demand.erase(it);
  } else {
    it->second = remain;
  }
}

inline calendar::DemandMatrix BuildDemandMatrixWithOutstanding() {
  auto demand = g_granularity_controller->BuildDemandMatrix();
  const uint32_t endpoints = CountTrafficEndpoints();
  if (demand.size() < endpoints) {
    demand.resize(endpoints, std::vector<double>(endpoints, 0.0));
  }
  for (auto& row : demand) {
    if (row.size() < endpoints) {
      row.resize(endpoints, 0.0);
    }
  }
  for (const auto& kv : g_calendar_outstanding_demand) {
    const uint32_t src = kv.first.first;
    const uint32_t dst = kv.first.second;
    if (src < demand.size() && dst < demand[src].size() && kv.second > 0.0) {
      demand[src][dst] += kv.second;
    }
  }
  return demand;
}

inline void ApplyCalendarScheduleFromDemand(
    const calendar::DemandMatrix& demand, int src, int dst,
    const AstraSim::ncclFlowTag& flow_tag, const std::string& event_name) {
  ns3::CalendarSchedule schedule;
  if (GetCalendarRecomputePolicy() == CalendarRecomputePolicy::STATIC_OPERATOR &&
      GetCalendarStaticPattern() == "allgather_ring") {
    schedule = BuildStaticCalendarSchedule(CountTrafficEndpoints());
  } else {
    auto generatedSchedule = calendar::BuildCalendarSchedule(
        demand, calendar_algorithm, calendar_frame_slots);
    for (const auto& entry : generatedSchedule.entries) {
      ns3::CalendarScheduleEntry ns3Entry;
      ns3Entry.permutation = entry.permutation;
      ns3Entry.slots = entry.slots;
      schedule.entries.push_back(ns3Entry);
    }
  }

  uint32_t applied_switches = 0;
  for (uint32_t nodeIndex = 0; nodeIndex < n.GetN(); ++nodeIndex) {
    Ptr<CalendarSwitchNode> calendarSwitch =
        DynamicCast<CalendarSwitchNode>(n.Get(nodeIndex));
    if (calendarSwitch) {
      calendarSwitch->LoadSchedule(schedule, calendar_slot_ns, calendar_frame_slots);
      applied_switches++;
    }
  }
  g_active_calendar_schedule = schedule;
  g_active_calendar_schedule_valid = !schedule.entries.empty();

  double demand_sum = 0.0;
  for (const auto& row : demand) {
    for (double value : row) {
      if (value > 0.0) {
        demand_sum += value;
      }
    }
  }
  AppendCalendarTrace(event_name, src, dst, flow_tag.tag_id, flow_tag.current_flow_id,
                      flow_tag.chunk_id, demand_sum, schedule.entries.size(),
                      applied_switches);
}

inline void PollCalendarStallWatchdog() {
  if (!enable_calendar_switch ||
      GetCalendarRecomputePolicy() != CalendarRecomputePolicy::DYNAMIC) {
    return;
  }

  uint64_t total_allowed = 0;
  uint64_t total_blocked = 0;
  uint32_t switch_count = 0;
  for (uint32_t nodeIndex = 0; nodeIndex < n.GetN(); ++nodeIndex) {
    Ptr<CalendarSwitchNode> calendarSwitch = DynamicCast<CalendarSwitchNode>(n.Get(nodeIndex));
    if (!calendarSwitch) {
      continue;
    }
    total_allowed += calendarSwitch->GetAllowedPackets();
    total_blocked += calendarSwitch->GetBlockedPackets();
    switch_count++;
  }
  if (switch_count > 0) {
    const uint64_t delta_allowed = total_allowed - g_watchdog_last_allowed;
    const uint64_t delta_blocked = total_blocked - g_watchdog_last_blocked;
    const double outstanding_sum = SumOutstandingCalendarDemand();
    if (delta_allowed == 0 && delta_blocked > 0 && outstanding_sum > 0.0 &&
        g_granularity_controller) {
      const auto demand = BuildDemandMatrixWithOutstanding();
      const AstraSim::ncclFlowTag unknown_tag;
      ApplyCalendarScheduleFromDemand(demand, -1, -1, unknown_tag,
                                      "reschedule_watchdog");
    }
  }
  g_watchdog_last_allowed = total_allowed;
  g_watchdog_last_blocked = total_blocked;

  const uint64_t interval_ns = std::max<uint64_t>(
      static_cast<uint64_t>(calendar_slot_ns), static_cast<uint64_t>(100));
  Simulator::Schedule(NanoSeconds(interval_ns), &PollCalendarStallWatchdog);
}

inline void StartCalendarStallWatchdog() {
  if (g_calendar_watchdog_started || !enable_calendar_switch ||
      GetCalendarRecomputePolicy() != CalendarRecomputePolicy::DYNAMIC) {
    return;
  }
  g_calendar_watchdog_started = true;
  g_watchdog_last_allowed = 0;
  g_watchdog_last_blocked = 0;
  Simulator::ScheduleNow(&PollCalendarStallWatchdog);
}

inline void PollCalendarSwitchMetrics() {
  if (calendar_trace_enable == 0 || calendar_trace_file.empty() || !enable_calendar_switch) {
    return;
  }

  if (!g_switch_metrics_trace.is_open()) {
    g_switch_metrics_trace.open(calendar_trace_file + ".switch_metrics.csv",
                                std::ios::out | std::ios::app);
    if (!g_switch_metrics_trace.is_open()) {
      return;
    }
    g_switch_metrics_header_written = false;
  }

  if (!g_switch_metrics_header_written) {
    g_switch_metrics_trace
        << "sim_ns,switch_type,switch_id,slot_idx,port_id,egress_bytes_q0,egress_bytes_non_q0,"
           "slot_allowed,slot_blocked,total_allowed,total_blocked\n";
    g_switch_metrics_header_written = true;
  }

  const uint64_t sim_ns = static_cast<uint64_t>(Simulator::Now().GetNanoSeconds());
  for (uint32_t nodeIndex = 0; nodeIndex < n.GetN(); ++nodeIndex) {
    Ptr<CalendarSwitchNode> calendarSwitch = DynamicCast<CalendarSwitchNode>(n.Get(nodeIndex));
    Ptr<NVSwitchNode> nvSwitch = DynamicCast<NVSwitchNode>(n.Get(nodeIndex));
    if ((!calendarSwitch || !calendarSwitch->m_mmu) &&
        (!nvSwitch || !nvSwitch->m_mmu)) {
      continue;
    }

    const bool is_calendar = (calendarSwitch != nullptr && calendarSwitch->m_mmu != nullptr);
    const std::string switch_type = is_calendar ? "calendar" : "nvswitch";
    const uint64_t total_allowed =
        is_calendar ? calendarSwitch->GetAllowedPackets() : nvSwitch->GetAllowedPackets();
    const uint64_t total_blocked =
        is_calendar ? calendarSwitch->GetBlockedPackets() : nvSwitch->GetBlockedPackets();
    const auto last = g_last_switch_admission_counters.find(nodeIndex);
    uint64_t slot_allowed = total_allowed;
    uint64_t slot_blocked = total_blocked;
    if (last != g_last_switch_admission_counters.end()) {
      slot_allowed = total_allowed - last->second.first;
      slot_blocked = total_blocked - last->second.second;
    }
    g_last_switch_admission_counters[nodeIndex] =
        std::make_pair(total_allowed, total_blocked);

    uint32_t slot_idx = 0;
    if (is_calendar) {
      slot_idx = calendarSwitch->GetCurrentSlotIndex();
    } else if (calendar_slot_ns > 0) {
      slot_idx = static_cast<uint32_t>(
          (Simulator::Now().GetNanoSeconds() / calendar_slot_ns) % std::max(1u, calendar_frame_slots));
    }

    const uint32_t num_ports =
        std::min(static_cast<uint32_t>(n.Get(nodeIndex)->GetNDevices()), kSwitchPortCount);
    std::vector<std::pair<uint32_t, uint64_t>> active_port_samples;
    active_port_samples.reserve(16);
    for (uint32_t port_id = 0; port_id < num_ports; ++port_id) {
      uint64_t q0_bytes =
          is_calendar ? calendarSwitch->GetPortQueueBytes(port_id, 0)
                      : nvSwitch->GetPortQueueBytes(port_id, 0);
      uint64_t non_q0_bytes = 0;
      for (uint32_t q_idx = 1; q_idx < kSwitchQueueCount; ++q_idx) {
        non_q0_bytes +=
            is_calendar ? calendarSwitch->GetPortQueueBytes(port_id, q_idx)
                        : nvSwitch->GetPortQueueBytes(port_id, q_idx);
      }
      if (q0_bytes > 0 || non_q0_bytes > 0) {
        active_port_samples.push_back(
            std::make_pair(port_id, (q0_bytes << 32) | (non_q0_bytes & 0xffffffffu)));
      }
    }
    if (active_port_samples.empty()) {
      active_port_samples.push_back(std::make_pair(0u, 0u));
    }
    for (const auto& sample : active_port_samples) {
      const uint64_t q0_bytes = sample.second >> 32;
      const uint64_t non_q0_bytes = sample.second & 0xffffffffu;
      g_switch_metrics_trace << sim_ns << "," << switch_type << "," << nodeIndex << "," << slot_idx << ","
                             << sample.first << "," << q0_bytes << "," << non_q0_bytes << ","
                             << slot_allowed << "," << slot_blocked << ","
                             << total_allowed << "," << total_blocked << "\n";
    }
  }
  g_switch_metrics_trace.flush();

  const uint64_t interval_ns = std::max<uint64_t>(1, calendar_slot_ns);
  Simulator::Schedule(NanoSeconds(interval_ns), &PollCalendarSwitchMetrics);
}

inline void StartCalendarSwitchMetricsPolling() {
  if (g_switch_metrics_polling_started || calendar_trace_enable == 0 || calendar_trace_file.empty()) {
    return;
  }
  g_switch_metrics_polling_started = true;
  Simulator::ScheduleNow(&PollCalendarSwitchMetrics);
}
struct task1 {
  int src;
  int dest;
  int type;
  uint64_t count;
  void *fun_arg;
  void (*msg_handler)(void *fun_arg);
  double schTime; 
};
map<std::pair<int, std::pair<int, int>>, struct task1> expeRecvHash;
map<std::pair<int, std::pair<int, int>>, uint64_t> recvHash;
map<std::pair<int, std::pair<int, int>>, struct task1> sentHash;
map<std::pair<int, int>, int64_t> nodeHash;
map<std::pair<int,std::pair<int,int>>,int> waiting_to_sent_callback;  
map<std::pair<int,std::pair<int,int>>,int>waiting_to_notify_receiver;
map<std::pair<int,std::pair<int,int>>,uint64_t>received_chunksize;  
map<std::pair<int,std::pair<int,int>>,uint64_t>sent_chunksize;  
bool is_sending_finished(int src,int dst,AstraSim::ncclFlowTag flowTag){
  int tag_id = flowTag.current_flow_id;
  if (waiting_to_sent_callback.count(
          std::make_pair(tag_id, std::make_pair(src, dst)))) {
    if (--waiting_to_sent_callback[std::make_pair(
            tag_id, std::make_pair(src, dst))] == 0) {
      waiting_to_sent_callback.erase(
          std::make_pair(tag_id, std::make_pair(src, dst)));
      return true;
    }
  }
  return false;
}

bool is_receive_finished(int src,int dst,AstraSim::ncclFlowTag flowTag){
  int tag_id = flowTag.current_flow_id;
  map<std::pair<int,std::pair<int,int>>,int>::iterator it;
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  if (waiting_to_notify_receiver.count(
          std::make_pair(tag_id, std::make_pair(src, dst)))) {
    NcclLog->writeLog(NcclLogLevel::DEBUG," is_receive_finished waiting_to_notify_receiver  tag_id  %d src  %d dst  %d count  %d",tag_id,src,dst,waiting_to_notify_receiver[std::make_pair(
                     tag_id, std::make_pair(src, dst))]);
    if (--waiting_to_notify_receiver[std::make_pair(
            tag_id, std::make_pair(src, dst))] == 0) {
      waiting_to_notify_receiver.erase(
          std::make_pair(tag_id, std::make_pair(src, dst)));
      return true;
    }
  }
  return false;
}

void SendFlow(int src, int dst, uint64_t maxPacketCount,
              void (*msg_handler)(void *fun_arg), void *fun_arg, int tag, AstraSim::sim_request *request) {
  MockNcclLog*NcclLog = MockNcclLog::getInstance();
  uint64_t PacketCount=((maxPacketCount+_QPS_PER_CONNECTION_-1)/_QPS_PER_CONNECTION_);
  uint64_t leftPacketCount = maxPacketCount;
  for(int index = 0 ;index<_QPS_PER_CONNECTION_;index++){
  uint64_t real_PacketCount = min(PacketCount,leftPacketCount);
  leftPacketCount-=real_PacketCount;
  uint32_t port = portNumber[src][dst]++; 
    {
      #ifdef NS3_MTP
      MtpInterface::explicitCriticalSection cs;
      #endif
      sender_src_port_map[make_pair(port, make_pair(src, dst))] = request->flowTag;
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
    }
  int flow_id = request->flowTag.current_flow_id;
  bool nvls_on = request->flowTag.nvls_on;
  const CalendarRecomputePolicy recompute_policy = GetCalendarRecomputePolicy();
  if (enable_calendar_switch) {
    StartCalendarSwitchMetricsPolling();
    StartCalendarStallWatchdog();
    uint32_t observed_nodes = CountTrafficEndpoints();
    if (src >= 0 && dst >= 0) {
      observed_nodes = static_cast<uint32_t>(std::max(src, dst) + 1);
    }
    EnsureGranularityController(std::max(CountTrafficEndpoints(), observed_nodes));
    bool should_reschedule = false;

    if (recompute_policy == CalendarRecomputePolicy::DYNAMIC) {
      g_granularity_controller->OnFlowStart(src, dst, real_PacketCount,
                                            request->flowTag);
      should_reschedule = g_granularity_controller->ShouldReschedule(request->flowTag);
    } else if (recompute_policy == CalendarRecomputePolicy::STATIC_OPERATOR) {
      if (!g_static_operator_schedule_loaded) {
        g_granularity_controller->OnFlowStart(src, dst, real_PacketCount,
                                              request->flowTag);
        if (GetCalendarStaticPattern() == "allgather_ring") {
          // For allgather static-ring mode, install the static calendar
          // immediately to avoid startup burst before slot-gating becomes active.
          should_reschedule = true;
        } else {
          should_reschedule = g_granularity_controller->ShouldReschedule(request->flowTag);
        }
      }
    } else {  // STATIC_PHASE
      g_granularity_controller->OnFlowStart(src, dst, real_PacketCount,
                                            request->flowTag);
      if (g_static_phase_last_chunk < 0) {
        should_reschedule = g_granularity_controller->ShouldReschedule(request->flowTag);
        if (should_reschedule) {
          g_static_phase_last_chunk = request->flowTag.chunk_id;
        }
      } else if (request->flowTag.chunk_id >= 0 &&
                 request->flowTag.chunk_id != g_static_phase_last_chunk) {
        should_reschedule = true;
        g_static_phase_last_chunk = request->flowTag.chunk_id;
      }
    }

    if (should_reschedule) {
      const auto demand = BuildDemandMatrixWithOutstanding();
      ApplyCalendarScheduleFromDemand(demand, src, dst, request->flowTag,
                                      recompute_policy == CalendarRecomputePolicy::DYNAMIC
                                          ? "reschedule_dynamic"
                                          : (recompute_policy ==
                                                     CalendarRecomputePolicy::STATIC_OPERATOR
                                                 ? "reschedule_static_operator"
                                                 : "reschedule_static_phase"));
      if (recompute_policy == CalendarRecomputePolicy::STATIC_OPERATOR) {
        g_static_operator_schedule_loaded = true;
      }
    }
  }
  AddOutstandingCalendarDemand(src, dst, real_PacketCount);
  int pg = 3, dport = 100;
  int send_lat = 6000;
  const char* send_lat_env = std::getenv("AS_SEND_LAT");
  if (send_lat_env) {
    try {
      send_lat = std::stoi(send_lat_env);
    } catch (const std::invalid_argument& e) {
      NcclLog->writeLog(NcclLogLevel::ERROR,"send_lat set error");
      exit(-1);
    }
  }
  send_lat *= 1000;
  uint64_t send_time_ns = static_cast<uint64_t>(send_lat);
  if (enable_calendar_switch &&
      recompute_policy == CalendarRecomputePolicy::STATIC_OPERATOR &&
      g_active_calendar_schedule_valid) {
    send_time_ns = ComputeScheduleAwareSendTimeNs(
        static_cast<uint32_t>(src), static_cast<uint32_t>(dst),
        static_cast<uint64_t>(send_lat));
  }
  flow_input.idx++;
  if(real_PacketCount == 0) real_PacketCount = 1;
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG," [Packet sending event]  %dSendFlow to  %d channelid:  %d flow_id  %d srcip  %d dstip  %d size:  %llu at the tick:  %d",src,dst,tag,flow_id,serverAddress[src],serverAddress[dst],maxPacketCount,AstraSim::Sys::boostedTick());
    NcclLog->writeLog(NcclLogLevel::DEBUG," request->flowTag [Packet sending event]  %dSendFlow to  %d tag_id:  %d flow_id  %d srcip  %d dstip  %d size:  %llu at the tick:  %d",request->flowTag.sender_node,request->flowTag.receiver_node,request->flowTag.tag_id,request->flowTag.current_flow_id,serverAddress[src],serverAddress[dst],maxPacketCount,AstraSim::Sys::boostedTick());
  const uint64_t now_ns = static_cast<uint64_t>(Simulator::Now().GetNanoSeconds());
  const uint64_t pacing_defer_ns = send_time_ns > now_ns ? (send_time_ns - now_ns) : 0;
  AppendFlowTimingTrace("sendflow_schedule",
                        src,
                        dst,
                        request->flowTag.tag_id,
                        request->flowTag.current_flow_id,
                        request->flowTag.chunk_id,
                        static_cast<int>(port),
                        pacing_defer_ns);
  RdmaClientHelper clientHelper(
      pg, serverAddress[src], serverAddress[dst], port, dport, real_PacketCount,
      has_win ? (global_t == 1 ? maxBdp : pairBdp[n.Get(src)][n.Get(dst)]) : 0,
      global_t == 1 ? maxRtt : pairRtt[src][dst], msg_handler, fun_arg, tag,
      src, dst);
  if(nvls_on) clientHelper.SetAttribute("NVLS_enable", UintegerValue (1));
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    ApplicationContainer appCon = clientHelper.Install(n.Get(src));
    const uint64_t start_delay_ns = send_time_ns > now_ns ? (send_time_ns - now_ns) : 0;
    appCon.Start(NanoSeconds(start_delay_ns));
    waiting_to_sent_callback[std::make_pair(request->flowTag.current_flow_id,std::make_pair(src,dst))]++;
    waiting_to_notify_receiver[std::make_pair(request->flowTag.current_flow_id,std::make_pair(src,dst))]++;
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  NcclLog->writeLog(NcclLogLevel::DEBUG,"waiting_to_notify_receiver  current_flow_id  %d src  %d dst  %d count  %d",request->flowTag.current_flow_id,src,dst,waiting_to_notify_receiver[std::make_pair(request->flowTag.tag_id,std::make_pair(src,dst))]);
  }
}

void notify_receiver_receive_data(int sender_node, int receiver_node,
                                  uint64_t message_size, AstraSim::ncclFlowTag flowTag) {
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;   
    #endif                         
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG," %d notify recevier:  %d message size:  %llu",sender_node,receiver_node,message_size);
    int tag = flowTag.tag_id;   
    if (expeRecvHash.find(make_pair(
            tag, make_pair(sender_node, receiver_node))) != expeRecvHash.end()) {
      task1 t2 =
          expeRecvHash[make_pair(tag, make_pair(sender_node, receiver_node))];
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG," %d notify recevier:  %d message size:  %llu t2.count:  %llu channle id:  %d",sender_node,receiver_node,message_size,t2.count,flowTag.channel_id);
      AstraSim::RecvPacketEventHadndlerData* ehd = (AstraSim::RecvPacketEventHadndlerData*) t2.fun_arg;
      if (message_size == t2.count) {
        NcclLog->writeLog(NcclLogLevel::DEBUG," message_size = t2.count expeRecvHash.erase  %d notify recevier:  %d message size:  %llu channel_id  %d",sender_node,receiver_node,message_size,tag);
        expeRecvHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
        AppendFlowTimingTrace("receiver_done",
                              sender_node,
                              receiver_node,
                              flowTag.tag_id,
                              flowTag.current_flow_id,
                              flowTag.chunk_id,
                              -1,
                              message_size);
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        assert(ehd->flowTag.current_flow_id == -1 && ehd->flowTag.child_flow_id == -1);
        ehd->flowTag = flowTag;
        t2.msg_handler(t2.fun_arg);
        goto receiver_end_1st_section;
      } else if (message_size > t2.count) {
        recvHash[make_pair(tag, make_pair(sender_node, receiver_node))] =
            message_size - t2.count;
        NcclLog->writeLog(NcclLogLevel::DEBUG,"message_size > t2.count expeRecvHash.erase %d notify recevier:  %d message size:  %llu channel_id  %d",sender_node,receiver_node,message_size,tag);
        expeRecvHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        assert(ehd->flowTag.current_flow_id == -1 && ehd->flowTag.child_flow_id == -1);
        ehd->flowTag = flowTag;
        t2.msg_handler(t2.fun_arg);
        goto receiver_end_1st_section;
      } else {
        t2.count -= message_size;
        expeRecvHash[make_pair(tag, make_pair(sender_node, receiver_node))] = t2;
      }
    } else {
      receiver_pending_queue[std::make_pair(std::make_pair(receiver_node, sender_node),tag)] = flowTag;
      if (recvHash.find(make_pair(tag, make_pair(sender_node, receiver_node))) ==
          recvHash.end()) {
        recvHash[make_pair(tag, make_pair(sender_node, receiver_node))] =
            message_size;
      } else {
        recvHash[make_pair(tag, make_pair(sender_node, receiver_node))] +=
            message_size;
      }
    }
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  receiver_end_1st_section:
    {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs2;
    #endif  
    if (nodeHash.find(make_pair(receiver_node, 1)) == nodeHash.end()) {
      nodeHash[make_pair(receiver_node, 1)] = message_size;
    } else {
      nodeHash[make_pair(receiver_node, 1)] += message_size;
    }
    #ifdef NS3_MTP
    cs2.ExitSection();
    #endif
    }
  }
}

void notify_sender_sending_finished(int sender_node, int receiver_node,
                                    uint64_t message_size, AstraSim::ncclFlowTag flowTag) {
  { 
    MockNcclLog * NcclLog = MockNcclLog::getInstance();
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif    
    int tag = flowTag.tag_id;        
    if (sentHash.find(make_pair(tag, make_pair(sender_node, receiver_node))) !=
      sentHash.end()) {
      task1 t2 = sentHash[make_pair(tag, make_pair(sender_node, receiver_node))];
      AstraSim::SendPacketEventHandlerData* ehd = (AstraSim::SendPacketEventHandlerData*) t2.fun_arg;
      ehd->flowTag=flowTag;   
      if (t2.count == message_size) {
        sentHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
        if (nodeHash.find(make_pair(sender_node, 0)) == nodeHash.end()) {
          nodeHash[make_pair(sender_node, 0)] = message_size;
        } else {
          nodeHash[make_pair(sender_node, 0)] += message_size;
        }
        AppendFlowTimingTrace("sender_done",
                              sender_node,
                              receiver_node,
                              flowTag.tag_id,
                              flowTag.current_flow_id,
                              flowTag.chunk_id,
                              -1,
                              message_size);
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        t2.msg_handler(t2.fun_arg);
        goto sender_end_1st_section;
      }else{
        NcclLog->writeLog(NcclLogLevel::ERROR,"sentHash msg size != sender_node %d receiver_node %d message_size %lu flow_id ",sender_node,receiver_node,message_size);
      }
    }else{
      NcclLog->writeLog(NcclLogLevel::ERROR,"sentHash cann't find sender_node %d receiver_node %d message_size %lu",sender_node,receiver_node,message_size);
    }       
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
sender_end_1st_section:
  return;
}


void notify_sender_packet_arrivered_receiver(int sender_node, int receiver_node,
                                    uint64_t message_size, AstraSim::ncclFlowTag flowTag) {
  int tag = flowTag.channel_id;
  if (sentHash.find(make_pair(tag, make_pair(sender_node, receiver_node))) !=
      sentHash.end()) {
    task1 t2 = sentHash[make_pair(tag, make_pair(sender_node, receiver_node))];
    AstraSim::SendPacketEventHandlerData* ehd = (AstraSim::SendPacketEventHandlerData*) t2.fun_arg;
    ehd->flowTag=flowTag;
    if (t2.count == message_size) {
      sentHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
      if (nodeHash.find(make_pair(sender_node, 0)) == nodeHash.end()) {
        nodeHash[make_pair(sender_node, 0)] = message_size;
      } else {
        nodeHash[make_pair(sender_node, 0)] += message_size;
      }
      t2.msg_handler(t2.fun_arg);
    }
  }
}

void qp_finish(FILE *fout, Ptr<RdmaQueuePair> q) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  uint64_t base_rtt = pairRtt[sid][did], b = pairBw[sid][did];
  uint32_t total_bytes =
      q->m_size +
      ((q->m_size - 1) / packet_payload_size + 1) *
          (CustomHeader::GetStaticWholeHeaderSize() -
           IntHeader::GetStaticSize()); 
  uint64_t standalone_fct = base_rtt + total_bytes * 8000000000lu / b;
  fprintf(fout, "%08x %08x %u %u %lu %lu %lu %lu\n", q->sip.Get(), q->dip.Get(),
          q->sport, q->dport, q->m_size, q->startTime.GetTimeStep(),
          (Simulator::Now() - q->startTime).GetTimeStep(), standalone_fct);
  fflush(fout);

  AstraSim::ncclFlowTag flowTag;
  uint64_t notify_size;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    Ptr<Node> dstNode = n.Get(did);
    Ptr<RdmaDriver> rdma = dstNode->GetObject<RdmaDriver>();
    rdma->m_rdma->DeleteRxQp(q->sip.Get(), q->m_pg, q->sport);
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG,"qp finish, src:  %d did:  %d port:  %d total bytes:  %llu at the tick:  %d",sid,did,q->sport,q->m_size,AstraSim::Sys::boostedTick());
    if (sender_src_port_map.find(make_pair(q->sport, make_pair(sid, did))) ==
        sender_src_port_map.end()) {
      NcclLog->writeLog(NcclLogLevel::ERROR,"could not find the tag, there must be something wrong");
      exit(-1);
    }
    flowTag = sender_src_port_map[make_pair(q->sport, make_pair(sid, did))];
    sender_src_port_map.erase(make_pair(q->sport, make_pair(sid, did)));
    AppendFlowTimingTrace("qp_finish",
                          static_cast<int>(sid),
                          static_cast<int>(did),
                          flowTag.tag_id,
                          flowTag.current_flow_id,
                          flowTag.chunk_id,
                          static_cast<int>(q->sport),
                          q->m_size);
    ConsumeOutstandingCalendarDemand(sid, did, q->m_size);
    received_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))]+=q->m_size;
    if(!is_receive_finished(sid,did,flowTag)) {
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      return; 
    }
    notify_size = received_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))];
    received_chunksize.erase(std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did)));    
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  notify_receiver_receive_data(sid, did, notify_size, flowTag);
}

void send_finish(FILE *fout, Ptr<RdmaQueuePair> q) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  AstraSim::ncclFlowTag flowTag;
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  NcclLog->writeLog(NcclLogLevel::DEBUG,"[Packet sent from NIC] send finish, src:  %d did:  %d port:  %d srcip  %d dstip  %d total bytes:  %llu at the tick:  %d",sid,did,q->sport,q->sip,q->dip,q->m_size,AstraSim::Sys::boostedTick());
  uint64_t all_sent_chunksize;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    flowTag = sender_src_port_map[make_pair(q->sport, make_pair(sid, did))];
    sent_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))]+=q->m_size;
    if(!is_sending_finished(sid,did,flowTag)) {
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      return;
    }
    all_sent_chunksize = sent_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))];
    sent_chunksize.erase(std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did)));
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  AppendFlowTimingTrace("send_finish_agg",
                        static_cast<int>(sid),
                        static_cast<int>(did),
                        flowTag.tag_id,
                        flowTag.current_flow_id,
                        flowTag.chunk_id,
                        static_cast<int>(q->sport),
                        all_sent_chunksize);
  notify_sender_sending_finished(sid, did, all_sent_chunksize, flowTag);
}

int main1(string network_topo,string network_conf) {
  clock_t begint, endt;
  begint = clock();

  if (!ReadConf(network_topo,network_conf))
    return -1;
  SetConfig();
  SetupNetwork(qp_finish,send_finish);

std::cout << "Running Simulation.\n";
  fflush(stdout);
  NS_LOG_INFO("Run Simulation.");

  endt = clock();
  return 0;
}
#endif