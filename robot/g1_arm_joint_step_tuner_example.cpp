#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>

#include <unitree/idl/hg/LowCmd_.hpp>
#include <unitree/idl/hg/LowState_.hpp>
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>

static const std::string kTopicArmSDK = "rt/arm_sdk";
static const std::string kTopicState = "rt/lowstate";

enum JointIndex {
  kLeftHipPitch,
  kLeftHipRoll,
  kLeftHipYaw,
  kLeftKnee,
  kLeftAnkle,
  kLeftAnkleRoll,
  kRightHipPitch,
  kRightHipRoll,
  kRightHipYaw,
  kRightKnee,
  kRightAnkle,
  kRightAnkleRoll,
  kWaistYaw,
  kWaistRoll,
  kWaistPitch,
  kLeftShoulderPitch,
  kLeftShoulderRoll,
  kLeftShoulderYaw,
  kLeftElbow,
  kLeftWristRoll,
  kLeftWristPitch,
  kLeftWristYaw,
  kRightShoulderPitch,
  kRightShoulderRoll,
  kRightShoulderYaw,
  kRightElbow,
  kRightWristRoll,
  kRightWristPitch,
  kRightWristYaw,
  kNotUsedJoint,
  kNotUsedJoint1,
  kNotUsedJoint2,
  kNotUsedJoint3,
  kNotUsedJoint4,
  kNotUsedJoint5
};

struct PoseJoint {
  JointIndex index;
  const char* name;
};

using Pose = std::array<float, 14>;
using WaistPose = std::array<float, 3>;

static const std::array<PoseJoint, 14> kArmJoints = {{
    {kLeftShoulderPitch, "L_SHOULDER_PITCH"},
    {kLeftShoulderRoll, "L_SHOULDER_ROLL"},
    {kLeftShoulderYaw, "L_SHOULDER_YAW"},
    {kLeftElbow, "L_ELBOW"},
    {kLeftWristRoll, "L_WRIST_ROLL"},
    {kLeftWristPitch, "L_WRIST_PITCH"},
    {kLeftWristYaw, "L_WRIST_YAW"},
    {kRightShoulderPitch, "R_SHOULDER_PITCH"},
    {kRightShoulderRoll, "R_SHOULDER_ROLL"},
    {kRightShoulderYaw, "R_SHOULDER_YAW"},
    {kRightElbow, "R_ELBOW"},
    {kRightWristRoll, "R_WRIST_ROLL"},
    {kRightWristPitch, "R_WRIST_PITCH"},
    {kRightWristYaw, "R_WRIST_YAW"},
}};

struct TimingConfig {
  float control_dt = 0.02f;
  float weight_rate = 0.25f;
  float capture_seconds = 3.0f;
  float step_move_seconds = 2.0f;
  float release_seconds = 3.0f;
};

inline constexpr TimingConfig kTiming{};

Pose InterpolatePose(const Pose& from, const Pose& to, float alpha) {
  Pose out{};
  for (size_t i = 0; i < out.size(); ++i) {
    out[i] = from[i] * (1.0f - alpha) + to[i] * alpha;
  }
  return out;
}

void ApplyPose(unitree_hg::msg::dds_::LowCmd_& msg, const Pose& pose, float kp,
               float kd, float dq, float tau_ff) {
  for (size_t i = 0; i < kArmJoints.size(); ++i) {
    auto joint = kArmJoints[i].index;
    msg.motor_cmd().at(joint).q(pose[i]);
    msg.motor_cmd().at(joint).dq(dq);
    msg.motor_cmd().at(joint).kp(kp);
    msg.motor_cmd().at(joint).kd(kd);
    msg.motor_cmd().at(joint).tau(tau_ff);
  }
}

void ApplyWaistPose(unitree_hg::msg::dds_::LowCmd_& msg, const WaistPose& pose,
                    float kp, float kd, float dq, float tau_ff) {
  const std::array<JointIndex, 3> waist_joints = {kWaistYaw, kWaistRoll,
                                                  kWaistPitch};
  for (size_t i = 0; i < waist_joints.size(); ++i) {
    auto joint = waist_joints[i];
    msg.motor_cmd().at(joint).q(pose[i]);
    msg.motor_cmd().at(joint).dq(dq);
    msg.motor_cmd().at(joint).kp(kp);
    msg.motor_cmd().at(joint).kd(kd);
    msg.motor_cmd().at(joint).tau(tau_ff);
  }
}

void PrintPose(const Pose& pose) {
  std::cout << std::fixed << std::setprecision(4);
  for (size_t i = 0; i < kArmJoints.size(); ++i) {
    std::cout << std::setw(18) << kArmJoints[i].name << "  ["
              << static_cast<int>(kArmJoints[i].index) << "]  " << pose[i]
              << std::endl;
  }
  std::cout << "Pose array for copy/paste:" << std::endl;
  std::cout << "{";
  for (size_t i = 0; i < pose.size(); ++i) {
    std::cout << pose[i] << "f";
    if (i + 1 != pose.size()) {
      std::cout << ", ";
    }
  }
  std::cout << "}" << std::endl;
}

void MovePose(unitree::robot::ChannelPublisher<unitree_hg::msg::dds_::LowCmd_>& publisher,
              unitree_hg::msg::dds_::LowCmd_& msg, const Pose& from,
              const Pose& to, int steps, std::chrono::milliseconds sleep_time,
              float kp, float kd, float dq, float tau_ff, float weight,
              const WaistPose& waist_pose) {
  for (int i = 0; i < steps; ++i) {
    float alpha = static_cast<float>(i + 1) / steps;
    msg.motor_cmd().at(kNotUsedJoint).q(weight);
    ApplyPose(msg, InterpolatePose(from, to, alpha), kp, kd, dq, tau_ff);
    ApplyWaistPose(msg, waist_pose, kp, kd, dq, tau_ff);
    publisher.Write(msg);
    std::this_thread::sleep_for(sleep_time);
  }
}

int main(int argc, char const* argv[]) {
  if (argc < 2) {
    std::cout << "Usage: " << argv[0] << " networkInterface" << std::endl;
    std::cout << "Example: " << argv[0] << " enx6c1ff7189cbd" << std::endl;
    return -1;
  }

  const std::string network_interface = argv[1];

  unitree::robot::ChannelFactory::Instance()->Init(0, network_interface);

  auto arm_sdk_publisher =
      std::make_shared<
          unitree::robot::ChannelPublisher<unitree_hg::msg::dds_::LowCmd_>>(
          kTopicArmSDK);
  arm_sdk_publisher->InitChannel();

  auto low_state_subscriber =
      std::make_shared<
          unitree::robot::ChannelSubscriber<unitree_hg::msg::dds_::LowState_>>(
          kTopicState);

  unitree_hg::msg::dds_::LowState_ state_msg;
  low_state_subscriber->InitChannel(
      [&](const void* msg) {
        auto state = static_cast<const unitree_hg::msg::dds_::LowState_*>(msg);
        std::memcpy(&state_msg, state, sizeof(unitree_hg::msg::dds_::LowState_));
      },
      1);

  unitree_hg::msg::dds_::LowCmd_ cmd_msg;
  constexpr float kKp = 60.0f;
  constexpr float kKd = 1.5f;
  constexpr float kDq = 0.0f;
  constexpr float kTauFf = 0.0f;

  const auto sleep_time = std::chrono::milliseconds(
      static_cast<int>(kTiming.control_dt / 0.001f));
  const float delta_weight = kTiming.weight_rate * kTiming.control_dt;

  Pose current_pose{};
  Pose target_pose{};
  WaistPose waist_pose{};
  float weight = 0.0f;
  constexpr float kStepDelta = 0.2f;
  size_t selected_joint = 0;

  std::cout << "Available upper-body DOFs:" << std::endl;
  for (const auto& joint : kArmJoints) {
    std::cout << "  " << std::setw(18) << joint.name << "  ["
              << static_cast<int>(joint.index) << "]" << std::endl;
  }
  std::cout << "Press ENTER to capture current pose and take over arm control..."
            << std::endl;
  std::cin.get();

  for (size_t i = 0; i < kArmJoints.size(); ++i) {
    current_pose[i] = state_msg.motor_state().at(kArmJoints[i].index).q();
  }
  target_pose = current_pose;
  waist_pose[0] = state_msg.motor_state().at(kWaistYaw).q();
  waist_pose[1] = state_msg.motor_state().at(kWaistRoll).q();
  waist_pose[2] = state_msg.motor_state().at(kWaistPitch).q();

  const int capture_steps =
      static_cast<int>(kTiming.capture_seconds / kTiming.control_dt);
  for (int i = 0; i < capture_steps; ++i) {
    weight = std::clamp(weight + delta_weight, 0.0f, 1.0f);
    cmd_msg.motor_cmd().at(kNotUsedJoint).q(weight);
    ApplyPose(cmd_msg, current_pose, kKp, kKd, kDq, kTauFf);
    ApplyWaistPose(cmd_msg, waist_pose, kKp, kKd, kDq, kTauFf);
    arm_sdk_publisher->Write(cmd_msg);
    std::this_thread::sleep_for(sleep_time);
  }

  std::cout << "Captured pose:" << std::endl;
  PrintPose(target_pose);
  std::cout << "Commands:" << std::endl
            << "  w + ENTER   previous joint" << std::endl
            << "  s + ENTER   next joint" << std::endl
            << "  a + ENTER   -" << kStepDelta << " rad on selected joint"
            << std::endl
            << "  d + ENTER   +" << kStepDelta << " rad on selected joint"
            << std::endl
            << "  p         print current measured pose" << std::endl
            << "  l         list all upper-body DOFs" << std::endl
            << "  q         release and quit" << std::endl
            << "Selected joint: " << kArmJoints[selected_joint].name << " ["
            << static_cast<int>(kArmJoints[selected_joint].index) << "]"
            << std::endl;
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.empty()) {
      continue;
    }

    const char cmd = static_cast<char>(std::tolower(line[0]));
    if (cmd == 'q') {
      break;
    }

    if (cmd == 'p') {
      for (size_t i = 0; i < kArmJoints.size(); ++i) {
        current_pose[i] = state_msg.motor_state().at(kArmJoints[i].index).q();
      }
      std::cout << "\nCurrent measured pose:" << std::endl;
      PrintPose(current_pose);
      continue;
    }

    if (cmd == 'l') {
      std::cout << "\nAvailable upper-body DOFs:" << std::endl;
      for (const auto& joint : kArmJoints) {
        std::cout << "  " << std::setw(18) << joint.name << "  ["
                  << static_cast<int>(joint.index) << "]" << std::endl;
      }
      continue;
    }

    if (cmd == 'w') {
      selected_joint =
          (selected_joint + kArmJoints.size() - 1) % kArmJoints.size();
      std::cout << "Selected joint: " << kArmJoints[selected_joint].name << " ["
                << static_cast<int>(kArmJoints[selected_joint].index) << "]"
                << std::endl;
      continue;
    }

    if (cmd == 's') {
      selected_joint = (selected_joint + 1) % kArmJoints.size();
      std::cout << "Selected joint: " << kArmJoints[selected_joint].name << " ["
                << static_cast<int>(kArmJoints[selected_joint].index) << "]"
                << std::endl;
      continue;
    }

    if (cmd == 'a' || cmd == 'd') {
      const float step_delta = cmd == 'a' ? -kStepDelta : kStepDelta;
      Pose from_pose = target_pose;
      target_pose[selected_joint] += step_delta;
      std::cout << "\nStepping " << kArmJoints[selected_joint].name << " to "
                << target_pose[selected_joint] << " rad" << std::endl;
      MovePose(*arm_sdk_publisher, cmd_msg, from_pose, target_pose,
               static_cast<int>(kTiming.step_move_seconds / kTiming.control_dt),
               sleep_time, kKp, kKd, kDq, kTauFf, 1.0f, waist_pose);

      for (size_t i = 0; i < kArmJoints.size(); ++i) {
        current_pose[i] = state_msg.motor_state().at(kArmJoints[i].index).q();
      }
      std::cout << "Measured pose after step:" << std::endl;
      PrintPose(current_pose);
      target_pose = current_pose;
      std::cout << "Selected joint: " << kArmJoints[selected_joint].name
                << " [" << static_cast<int>(kArmJoints[selected_joint].index)
                << "]" << std::endl;
      continue;
    }

    std::cout << "Unknown command. Use w/s/a/d/p/l/q then press ENTER."
              << std::endl;
  }

  const int release_steps =
      static_cast<int>(kTiming.release_seconds / kTiming.control_dt);
  for (int i = 0; i < release_steps; ++i) {
    weight = std::clamp(weight - delta_weight, 0.0f, 1.0f);
    cmd_msg.motor_cmd().at(kNotUsedJoint).q(weight);
    ApplyPose(cmd_msg, target_pose, kKp, kKd, kDq, kTauFf);
    ApplyWaistPose(cmd_msg, waist_pose, kKp, kKd, kDq, kTauFf);
    arm_sdk_publisher->Write(cmd_msg);
    std::this_thread::sleep_for(sleep_time);
  }

  cmd_msg.motor_cmd().at(kNotUsedJoint).q(0.0f);
  arm_sdk_publisher->Write(cmd_msg);
  return 0;
}
