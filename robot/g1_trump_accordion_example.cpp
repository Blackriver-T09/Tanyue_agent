#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iostream>
#include <memory>
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

using Pose = std::array<float, 17>;

struct TimingConfig {
  float control_dt = 0.02f;
  float weight_rate = 0.25f;
  float init_seconds = 4.0f;
  float ready_hold_seconds = 1.5f;
  float sway_seconds = 6.0f;
  float sway_cycle_seconds = 1.2f;
  float return_seconds = 4.0f;
  float release_seconds = 4.0f;
};

inline constexpr TimingConfig kTiming{};

static const std::array<JointIndex, 17> kArmJoints = {
    kLeftShoulderPitch,  kLeftShoulderRoll,  kLeftShoulderYaw,
    kLeftElbow,          kLeftWristRoll,     kLeftWristPitch,
    kLeftWristYaw,       kRightShoulderPitch, kRightShoulderRoll,
    kRightShoulderYaw,   kRightElbow,        kRightWristRoll,
    kRightWristPitch,    kRightWristYaw,     kWaistYaw,
    kWaistRoll,          kWaistPitch};

Pose InterpolatePose(const Pose &from, const Pose &to, float alpha) {
  Pose out{};
  for (size_t i = 0; i < out.size(); ++i) {
    out[i] = from[i] * (1.0f - alpha) + to[i] * alpha;
  }
  return out;
}

void ApplyPose(unitree_hg::msg::dds_::LowCmd_ &msg, const Pose &pose, float kp,
               float kd, float dq, float tau_ff) {
  for (size_t i = 0; i < kArmJoints.size(); ++i) {
    auto joint = kArmJoints[i];
    msg.motor_cmd().at(joint).q(pose[i]);
    msg.motor_cmd().at(joint).dq(dq);
    msg.motor_cmd().at(joint).kp(kp);
    msg.motor_cmd().at(joint).kd(kd);
    msg.motor_cmd().at(joint).tau(tau_ff);
  }
}

void HoldPose(
    unitree::robot::ChannelPublisher<unitree_hg::msg::dds_::LowCmd_> &publisher,
    unitree_hg::msg::dds_::LowCmd_ &msg, const Pose &pose, int steps,
    std::chrono::milliseconds sleep_time, float kp, float kd, float dq,
    float tau_ff, float weight) {
  for (int i = 0; i < steps; ++i) {
    msg.motor_cmd().at(kNotUsedJoint).q(weight);
    ApplyPose(msg, pose, kp, kd, dq, tau_ff);
    publisher.Write(msg);
    std::this_thread::sleep_for(sleep_time);
  }
}

void SwayHandsInward(
    unitree::robot::ChannelPublisher<unitree_hg::msg::dds_::LowCmd_> &publisher,
    unitree_hg::msg::dds_::LowCmd_ &msg, const Pose &base_pose, int steps,
    std::chrono::milliseconds sleep_time, float kp, float kd, float dq,
    float tau_ff, float weight, float cycle_seconds, float control_dt) {
  constexpr float kTwoPi = 6.28318530718f;
  for (int i = 0; i < steps; ++i) {
    const float t = static_cast<float>(i) * control_dt;
    const float sway = std::sin(kTwoPi * t / cycle_seconds);
    Pose pose = base_pose;

    // Swing both wrist pitch joints in the same direction,
    // while shoulder yaw moves inward/outward oppositely.
    pose[2] += 0.10f * sway;    // L_SHOULDER_YAW
    pose[9] += -0.10f * sway;   // R_SHOULDER_YAW
    pose[5] += 0.18f * sway;    // L_WRIST_PITCH
    pose[12] += 0.18f * sway;   // R_WRIST_PITCH

    msg.motor_cmd().at(kNotUsedJoint).q(weight);
    ApplyPose(msg, pose, kp, kd, dq, tau_ff);
    publisher.Write(msg);
    std::this_thread::sleep_for(sleep_time);
  }
}

int main(int argc, char const *argv[]) {
  if (argc < 2) {
    std::cout << "Usage: " << argv[0]
              << " networkInterface [--auto --i-understand-low-level-arm-risk]"
              << std::endl;
    return -1;
  }

  bool auto_mode = false;
  bool risk_confirmed = false;
  for (int i = 2; i < argc; ++i) {
    const std::string option = argv[i];
    auto_mode = auto_mode || option == "--auto";
    risk_confirmed =
        risk_confirmed || option == "--i-understand-low-level-arm-risk";
  }
  if (auto_mode && !risk_confirmed) {
    std::cerr << "Refusing automatic low-level arm control without the explicit "
                 "risk acknowledgement flag."
              << std::endl;
    return 2;
  }

  unitree::robot::ChannelFactory::Instance()->Init(0, argv[1]);

  auto arm_sdk_publisher =
      std::make_shared<
          unitree::robot::ChannelPublisher<unitree_hg::msg::dds_::LowCmd_>>(
          kTopicArmSDK);
  arm_sdk_publisher->InitChannel();

  unitree_hg::msg::dds_::LowCmd_ cmd_msg;
  unitree_hg::msg::dds_::LowState_ state_msg;
  std::atomic<bool> state_ready{false};

  auto low_state_subscriber =
      std::make_shared<
          unitree::robot::ChannelSubscriber<unitree_hg::msg::dds_::LowState_>>(
          kTopicState);
  low_state_subscriber->InitChannel(
      [&](const void *msg) {
        auto state = static_cast<const unitree_hg::msg::dds_::LowState_ *>(msg);
        std::memcpy(&state_msg, state, sizeof(unitree_hg::msg::dds_::LowState_));
        state_ready.store(true);
      },
      1);

  const auto state_deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!state_ready.load() && std::chrono::steady_clock::now() < state_deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  if (!state_ready.load()) {
    std::cerr << "No rt/lowstate received; refusing arm takeover." << std::endl;
    return 3;
  }

  auto gate = [&](const char *message) {
    std::cout << message << std::endl;
    if (!auto_mode) {
      std::cin.get();
    }
  };

  constexpr float kKp = 60.0f;
  constexpr float kKd = 1.5f;
  constexpr float kDq = 0.0f;
  constexpr float kTauFf = 0.0f;
  const auto sleep_time =
      std::chrono::milliseconds(static_cast<int>(kTiming.control_dt / 0.001f));
  const float delta_weight = kTiming.weight_rate * kTiming.control_dt;

  Pose init_pose{};
  Pose current_pose{};
  // First key pose:
  // left arm comes from the captured pose, right arm mirrors the left arm.
  Pose ready_pose = {
      0.1931f,  0.1469f,  -0.0378f, -0.4019f, 1.1787f, -0.0549f, 1.3462f,
      0.1931f,  -0.1469f, 0.0378f,  -0.4019f, -1.1787f, -0.0549f, -1.3462f,
      0.00f,    0.00f,    0.00f};
  gate("Press ENTER to capture current arm pose...");

  for (size_t i = 0; i < kArmJoints.size(); ++i) {
    current_pose[i] = state_msg.motor_state().at(kArmJoints[i]).q();
  }

  float weight = 0.0f;
  gate("Press ENTER to take over arm control and move to the ready pose...");

  std::cout << "Taking over arm control and moving to ready pose..." << std::endl;
  const int init_steps = static_cast<int>(kTiming.init_seconds / kTiming.control_dt);
  for (int i = 0; i < init_steps; ++i) {
    weight = std::clamp(weight + delta_weight, 0.0f, 1.0f);
    cmd_msg.motor_cmd().at(kNotUsedJoint).q(weight);

    float alpha = static_cast<float>(i + 1) / init_steps;
    ApplyPose(cmd_msg, InterpolatePose(current_pose, ready_pose, alpha), kKp,
              kKd, kDq, kTauFf);
    arm_sdk_publisher->Write(cmd_msg);
    std::this_thread::sleep_for(sleep_time);
  }

  gate("Press ENTER to hold the ready pose...");
  HoldPose(*arm_sdk_publisher, cmd_msg, ready_pose,
           static_cast<int>(kTiming.ready_hold_seconds / kTiming.control_dt),
           sleep_time, kKp, kKd, kDq,
           kTauFf, 1.0f);

  gate("Press ENTER to run wrist waving...");
  SwayHandsInward(
      *arm_sdk_publisher, cmd_msg, ready_pose,
      static_cast<int>(kTiming.sway_seconds / kTiming.control_dt), sleep_time,
      kKp, kKd, kDq, kTauFf, 1.0f, kTiming.sway_cycle_seconds,
      kTiming.control_dt);

  gate("Press ENTER to return to the neutral pose...");

  std::cout << "Returning to neutral pose..." << std::endl;
  const int return_steps =
      static_cast<int>(kTiming.return_seconds / kTiming.control_dt);
  for (int i = 0; i < return_steps; ++i) {
    float alpha = static_cast<float>(i + 1) / return_steps;
    cmd_msg.motor_cmd().at(kNotUsedJoint).q(1.0f);
    ApplyPose(cmd_msg, InterpolatePose(ready_pose, init_pose, alpha), kKp,
              kKd, kDq, kTauFf);
    arm_sdk_publisher->Write(cmd_msg);
    std::this_thread::sleep_for(sleep_time);
  }

  gate("Press ENTER to release arm control...");

  std::cout << "Releasing arm control..." << std::endl;
  const int release_steps =
      static_cast<int>(kTiming.release_seconds / kTiming.control_dt);
  for (int i = 0; i < release_steps; ++i) {
    weight = std::clamp(weight - delta_weight, 0.0f, 1.0f);
    cmd_msg.motor_cmd().at(kNotUsedJoint).q(weight);
    arm_sdk_publisher->Write(cmd_msg);
    std::this_thread::sleep_for(sleep_time);
  }

  cmd_msg.motor_cmd().at(kNotUsedJoint).q(0.0f);
  arm_sdk_publisher->Write(cmd_msg);

  std::cout << "Done." << std::endl;
  return 0;
}
