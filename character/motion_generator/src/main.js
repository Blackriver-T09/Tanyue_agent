import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const canvas = document.querySelector('#vrmCanvas');
const vrmSkeletonCanvas = document.querySelector('#vrmSkeletonCanvas');
const vrmSkeletonCtx = vrmSkeletonCanvas.getContext('2d');
const video = document.querySelector('#inputVideo');
const overlay = document.querySelector('#overlayCanvas');
const overlayCtx = overlay.getContext('2d');
const statusEl = document.querySelector('#status');
const trackingStatusEl = document.querySelector('#trackingStatus');
const trackingMeterEl = document.querySelector('#trackingMeter');
const recordStatusEl = document.querySelector('#recordStatus');
const countdownEl = document.querySelector('#countdownOverlay');

const startCameraBtn = document.querySelector('#startCamera');
const stopCameraBtn = document.querySelector('#stopCamera');
const startRecordBtn = document.querySelector('#startRecord');
const stopRecordBtn = document.querySelector('#stopRecord');
const downloadRecordBtn = document.querySelector('#downloadRecord');
const resetPoseBtn = document.querySelector('#resetPose');
const recordDurationInput = document.querySelector('#recordDuration');

const mirrorInput = document.querySelector('#mirrorInput');
const showVrmSkeletonInput = document.querySelector('#showVrmSkeleton');
const driveFullBodyInput = document.querySelector('#driveFullBody');
const driveHandsInput = document.querySelector('#driveHands');
const driveFaceInput = document.querySelector('#driveFace');
const smoothingInput = document.querySelector('#smoothing');
const armGainInput = document.querySelector('#armGain');
const torsoGainInput = document.querySelector('#torsoGain');
const retargetSolverInput = document.querySelector('#retargetSolver');

const pageParams = new URLSearchParams(window.location.search);
const modelParam = pageParams.get('model');

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: true,
  preserveDrawingBuffer: true,
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);
camera.position.set(0, 1.35, 3.0);

const orbit = new OrbitControls(camera, renderer.domElement);
orbit.target.set(0, 1.25, 0);
orbit.enableDamping = true;
orbit.enablePan = false;
orbit.minDistance = 1.8;
orbit.maxDistance = 5.0;

scene.add(new THREE.HemisphereLight(0xffffff, 0xb7b1a3, 1.8));
const keyLight = new THREE.DirectionalLight(0xffffff, 2.35);
keyLight.position.set(1.8, 3.2, 2.0);
scene.add(keyLight);

let currentVrm = null;
let holistic = null;
let cameraSource = null;
let latestResults = null;
let isRecording = false;
let recordStartedAt = 0;
let recordTimer = null;
let countdownTimer = null;
let recordedFrames = [];
const restPose = new Map();
const reusable = {
  vecA: new THREE.Vector3(),
  vecB: new THREE.Vector3(),
  quatA: new THREE.Quaternion(),
  quatB: new THREE.Quaternion(),
  quatC: new THREE.Quaternion(),
};
const faceState = {
  lookTarget: new THREE.Euler(),
};

const expressionPreset = {
  A: 'aa',
  E: 'ee',
  I: 'ih',
  O: 'oh',
  U: 'ou',
  Blink: 'blink',
  BlinkL: 'blinkLeft',
  BlinkR: 'blinkRight',
};

const pose = {
  nose: 0,
  leftEar: 7,
  rightEar: 8,
  leftShoulder: 11,
  rightShoulder: 12,
  leftElbow: 13,
  rightElbow: 14,
  leftWrist: 15,
  rightWrist: 16,
  leftHip: 23,
  rightHip: 24,
  leftKnee: 25,
  rightKnee: 26,
  leftAnkle: 27,
  rightAnkle: 28,
};

const fingerChains = {
  Thumb: [1, 2, 3, 4],
  Index: [5, 6, 7, 8],
  Middle: [9, 10, 11, 12],
  Ring: [13, 14, 15, 16],
  Little: [17, 18, 19, 20],
};

const boneAxis = {
  leftUpperArm: new THREE.Vector3(-1, 0, 0),
  leftLowerArm: new THREE.Vector3(-1, 0, 0),
  leftHand: new THREE.Vector3(-1, 0, 0),
  rightUpperArm: new THREE.Vector3(1, 0, 0),
  rightLowerArm: new THREE.Vector3(1, 0, 0),
  rightHand: new THREE.Vector3(1, 0, 0),
  leftUpperLeg: new THREE.Vector3(0, -1, 0),
  leftLowerLeg: new THREE.Vector3(0, -1, 0),
  leftFoot: new THREE.Vector3(0, 0, 1),
  rightUpperLeg: new THREE.Vector3(0, -1, 0),
  rightLowerLeg: new THREE.Vector3(0, -1, 0),
  rightFoot: new THREE.Vector3(0, 0, 1),
};

const vrmSkeletonConnections = [
  ['hips', 'spine'],
  ['spine', 'chest'],
  ['chest', 'upperChest'],
  ['upperChest', 'neck'],
  ['neck', 'head'],
  ['upperChest', 'leftShoulder'],
  ['leftShoulder', 'leftUpperArm'],
  ['leftUpperArm', 'leftLowerArm'],
  ['leftLowerArm', 'leftHand'],
  ['upperChest', 'rightShoulder'],
  ['rightShoulder', 'rightUpperArm'],
  ['rightUpperArm', 'rightLowerArm'],
  ['rightLowerArm', 'rightHand'],
  ['hips', 'leftUpperLeg'],
  ['leftUpperLeg', 'leftLowerLeg'],
  ['leftLowerLeg', 'leftFoot'],
  ['leftFoot', 'leftToes'],
  ['hips', 'rightUpperLeg'],
  ['rightUpperLeg', 'rightLowerLeg'],
  ['rightLowerLeg', 'rightFoot'],
  ['rightFoot', 'rightToes'],
];

const captureBoneNames = [
  'hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand',
  'rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'leftUpperLeg', 'leftLowerLeg', 'leftFoot', 'leftToes',
  'rightUpperLeg', 'rightLowerLeg', 'rightFoot', 'rightToes',
  'leftThumbMetacarpal', 'leftThumbProximal', 'leftThumbIntermediate', 'leftThumbDistal',
  'leftIndexProximal', 'leftIndexIntermediate', 'leftIndexDistal',
  'leftMiddleProximal', 'leftMiddleIntermediate', 'leftMiddleDistal',
  'leftRingProximal', 'leftRingIntermediate', 'leftRingDistal',
  'leftLittleProximal', 'leftLittleIntermediate', 'leftLittleDistal',
  'rightThumbMetacarpal', 'rightThumbProximal', 'rightThumbIntermediate', 'rightThumbDistal',
  'rightIndexProximal', 'rightIndexIntermediate', 'rightIndexDistal',
  'rightMiddleProximal', 'rightMiddleIntermediate', 'rightMiddleDistal',
  'rightRingProximal', 'rightRingIntermediate', 'rightRingDistal',
  'rightLittleProximal', 'rightLittleIntermediate', 'rightLittleDistal',
];

for (const side of ['left', 'right']) {
  for (const finger of ['Thumb', 'Index', 'Middle', 'Ring', 'Little']) {
    const root = finger === 'Thumb' ? `${side}${finger}Metacarpal` : `${side}${finger}Proximal`;
    const proximal = `${side}${finger}Proximal`;
    const intermediate = `${side}${finger}Intermediate`;
    const distal = `${side}${finger}Distal`;
    vrmSkeletonConnections.push([`${side}Hand`, root]);
    if (root !== proximal) vrmSkeletonConnections.push([root, proximal]);
    vrmSkeletonConnections.push([proximal, intermediate], [intermediate, distal]);
  }
}

function setStatus(message) {
  statusEl.textContent = message;
}

function setTrackingStatus(message) {
  trackingStatusEl.textContent = message;
}

function setRecordStatus(message) {
  recordStatusEl.textContent = message;
}

function resize() {
  const { clientWidth, clientHeight } = canvas;
  renderer.setSize(clientWidth, clientHeight, false);
  camera.aspect = clientWidth / Math.max(clientHeight, 1);
  camera.updateProjectionMatrix();

  if (vrmSkeletonCanvas.width !== clientWidth || vrmSkeletonCanvas.height !== clientHeight) {
    vrmSkeletonCanvas.width = clientWidth || 1;
    vrmSkeletonCanvas.height = clientHeight || 1;
  }

  const width = overlay.clientWidth || 1;
  const height = overlay.clientHeight || 1;
  if (overlay.width !== width || overlay.height !== height) {
    overlay.width = width;
    overlay.height = height;
  }
}

window.addEventListener('resize', resize);

function frameVrm(vrm) {
  vrm.scene.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(vrm.scene);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 1);
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const verticalDistance = size.y / (2 * Math.tan(fov / 2));
  const horizontalFov = 2 * Math.atan(Math.tan(fov / 2) * camera.aspect);
  const horizontalDistance = size.x / (2 * Math.tan(horizontalFov / 2));
  const distance = Math.max(verticalDistance, horizontalDistance, maxDim) * 1.18;
  const targetY = center.y + size.y * 0.1;

  orbit.target.set(center.x, targetY, center.z);
  camera.position.set(center.x, targetY + size.y * 0.02, center.z + distance);
  camera.near = Math.max(distance / 100, 0.01);
  camera.far = distance * 100;
  camera.updateProjectionMatrix();
  orbit.update();
}

function getBone(name) {
  return currentVrm?.humanoid?.getNormalizedBoneNode(name) ?? null;
}

function kalidokitBoneName(name) {
  return name.charAt(0).toLowerCase() + name.slice(1);
}

function vrmMetaVersion() {
  return currentVrm?.meta?.metaVersion || currentVrm?.meta?.version || '1';
}

function rigRotation(name, rotation = { x: 0, y: 0, z: 0 }, dampener = 1, lerpAmount = null) {
  if (!currentVrm || !rotation) return;
  const bone = getBone(kalidokitBoneName(name));
  if (!bone) return;
  const versionSign = vrmMetaVersion() === '1' ? -1 : 1;
  const euler = new THREE.Euler(
    versionSign * (rotation.x || 0) * dampener,
    (rotation.y || 0) * dampener,
    versionSign * (rotation.z || 0) * dampener,
    rotation.rotationOrder || 'XYZ',
  );
  const quaternion = new THREE.Quaternion().setFromEuler(euler);
  bone.quaternion.slerp(quaternion, lerpAmount ?? Number(smoothingInput.value));
}

function rigPosition(name, position = { x: 0, y: 0, z: 0 }, dampener = 1, lerpAmount = 0.07) {
  if (!currentVrm || !position) return;
  const bone = getBone(kalidokitBoneName(name));
  if (!bone) return;
  const vector = new THREE.Vector3(
    (position.x || 0) * dampener,
    (position.y || 0) * dampener,
    (position.z || 0) * dampener,
  );
  bone.position.lerp(vector, lerpAmount);
}

function getExpressionValue(name) {
  return currentVrm?.expressionManager?.getValue(name) ?? 0;
}

function setExpressionValue(name, value) {
  if (!currentVrm?.expressionManager || value == null || Number.isNaN(value)) return;
  currentVrm.expressionManager.setValue(name, THREE.MathUtils.clamp(value, 0, 1));
}

function lerpExpression(name, target, amount = 0.3) {
  setExpressionValue(name, THREE.MathUtils.lerp(getExpressionValue(name), target, amount));
}

function applyFaceCapture(riggedFace) {
  if (!currentVrm || !riggedFace || !driveFaceInput.checked) return;

  if (riggedFace.eye) {
    const blinkLeft = THREE.MathUtils.clamp(1 - riggedFace.eye.l, 0, 1) / 0.8;
    const blinkRight = THREE.MathUtils.clamp(1 - riggedFace.eye.r, 0, 1) / 0.8;
    lerpExpression(expressionPreset.BlinkL, blinkLeft, 0.4);
    lerpExpression(expressionPreset.BlinkR, blinkRight, 0.4);
  }

  const mouth = riggedFace.mouth?.shape;
  if (mouth) {
    lerpExpression(expressionPreset.I, (mouth.I || 0) / 0.8, 0.3);
    lerpExpression(expressionPreset.A, (mouth.A || 0) / 0.8, 0.3);
    lerpExpression(expressionPreset.E, (mouth.E || 0) / 0.8, 0.3);
    lerpExpression(expressionPreset.O, (mouth.O || 0) / 0.8, 0.3);
    lerpExpression(expressionPreset.U, (mouth.U || 0) / 0.8, 0.3);
  }

  if (riggedFace.pupil && currentVrm.lookAt?.applier?.applyYawPitch) {
    const lookTarget = new THREE.Euler(
      THREE.MathUtils.lerp(faceState.lookTarget.x, riggedFace.pupil.y, 0.4),
      THREE.MathUtils.lerp(faceState.lookTarget.y, riggedFace.pupil.x, 0.4),
      0,
      'XYZ',
    );
    faceState.lookTarget.copy(lookTarget);
    currentVrm.lookAt.applier.applyYawPitch(lookTarget.y, lookTarget.x);
  }
}

function relaxFaceCapture(amount = 0.18) {
  for (const name of [
    expressionPreset.A,
    expressionPreset.E,
    expressionPreset.I,
    expressionPreset.O,
    expressionPreset.U,
    expressionPreset.BlinkL,
    expressionPreset.BlinkR,
  ]) {
    lerpExpression(name, 0, amount);
  }
}

function projectedBonePoint(name) {
  const bone = getBone(name);
  if (!bone) return null;
  const point = bone.getWorldPosition(new THREE.Vector3());
  point.project(camera);
  return {
    x: (point.x * 0.5 + 0.5) * vrmSkeletonCanvas.width,
    y: (-point.y * 0.5 + 0.5) * vrmSkeletonCanvas.height,
    z: point.z,
  };
}

function drawVrmSkeleton() {
  vrmSkeletonCtx.clearRect(0, 0, vrmSkeletonCanvas.width, vrmSkeletonCanvas.height);
  if (!currentVrm || !showVrmSkeletonInput.checked) return;
  currentVrm.scene.updateMatrixWorld(true);

  vrmSkeletonCtx.save();
  vrmSkeletonCtx.lineCap = 'round';
  vrmSkeletonCtx.lineJoin = 'round';
  vrmSkeletonCtx.strokeStyle = 'rgba(34, 126, 111, 0.92)';
  vrmSkeletonCtx.lineWidth = 3;
  for (const [aName, bName] of vrmSkeletonConnections) {
    const a = projectedBonePoint(aName);
    const b = projectedBonePoint(bName);
    if (!a || !b || a.z < -1 || a.z > 1 || b.z < -1 || b.z > 1) continue;
    vrmSkeletonCtx.beginPath();
    vrmSkeletonCtx.moveTo(a.x, a.y);
    vrmSkeletonCtx.lineTo(b.x, b.y);
    vrmSkeletonCtx.stroke();
  }

  vrmSkeletonCtx.fillStyle = '#ffffff';
  vrmSkeletonCtx.strokeStyle = 'rgba(21, 78, 69, 0.95)';
  vrmSkeletonCtx.lineWidth = 1.5;
  const names = new Set(vrmSkeletonConnections.flat());
  for (const name of names) {
    const point = projectedBonePoint(name);
    if (!point || point.z < -1 || point.z > 1) continue;
    vrmSkeletonCtx.beginPath();
    vrmSkeletonCtx.arc(point.x, point.y, name.includes('Hand') ? 4 : 3, 0, Math.PI * 2);
    vrmSkeletonCtx.fill();
    vrmSkeletonCtx.stroke();
  }
  vrmSkeletonCtx.restore();
}

function captureRestPose() {
  restPose.clear();
  currentVrm?.humanoid?.resetNormalizedPose();
  currentVrm?.scene.updateMatrixWorld(true);
  for (const [boneName, axis] of Object.entries(boneAxis)) {
    const bone = getBone(boneName);
    if (!bone) continue;
    const worldQuat = bone.getWorldQuaternion(new THREE.Quaternion());
    const worldAxis = axis.clone().normalize().applyQuaternion(worldQuat).normalize();
    restPose.set(boneName, {
      localQuaternion: bone.quaternion.clone(),
      worldQuaternion: worldQuat.clone(),
      worldAxis,
    });
  }
}

function resetVrmPose() {
  if (!currentVrm) return;
  currentVrm.humanoid.resetNormalizedPose();
  currentVrm.scene.updateMatrixWorld(true);
  captureRestPose();
  setStatus('VRM pose reset');
}

async function loadVrm() {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const modelUrls = [
    modelParam ? `../models/${encodeURIComponent(modelParam)}` : null,
    '../models/LiuRuYan.vrm',
    '../models/test_02.vrm',
    '../models/test_01.vrm',
  ].filter(Boolean);

  for (const modelUrl of modelUrls) {
    try {
      setStatus(`Loading ${modelUrl.split('/').pop()}...`);
      const gltf = await loader.loadAsync(modelUrl);
      const vrm = gltf.userData.vrm;
      VRMUtils.removeUnnecessaryVertices(gltf.scene);
      if (VRMUtils.combineSkeletons) VRMUtils.combineSkeletons(gltf.scene);
      currentVrm = vrm;
      currentVrm.scene.rotation.y = 0;
      currentVrm.scene.traverse((obj) => {
        obj.frustumCulled = false;
      });
      scene.add(currentVrm.scene);
      frameVrm(currentVrm);
      captureRestPose();
      setStatus('VRM ready. Start camera to drive motion.');
      return;
    } catch (error) {
      console.warn(`Could not load VRM model ${modelUrl}.`, error);
    }
  }

  setStatus('Failed to load VRM');
}

function mpPoint(landmark) {
  if (!landmark) return null;
  const aspect = (video.videoWidth || 16) / Math.max(video.videoHeight || 9, 1);
  // Keep retarget data in raw camera coordinates. Mirroring is display-only,
  // matching SysMocap's approach and avoiding double-flipped depth/side axes.
  return new THREE.Vector3(
    (landmark.x - 0.5) * aspect,
    -(landmark.y - 0.5),
    -(landmark.z || 0) * aspect,
  );
}

function pointByIndex(landmarks, index) {
  return mpPoint(landmarks?.[index]);
}

function directionBetween(landmarks, startIndex, endIndex) {
  const start = pointByIndex(landmarks, startIndex);
  const end = pointByIndex(landmarks, endIndex);
  if (!start || !end) return null;
  return end.sub(start).normalize();
}

function landmarkVisibility(landmarks, index) {
  const item = landmarks?.[index];
  return item ? item.visibility ?? 1 : 0;
}

function driveBoneTowardWorldDirection(boneName, desiredDirection, amount = 1) {
  if (!currentVrm || !desiredDirection) return;
  const bone = getBone(boneName);
  const rest = restPose.get(boneName);
  if (!bone || !rest) return;

  const parent = bone.parent;
  const parentWorldInverse = parent
    ? parent.getWorldQuaternion(reusable.quatA).invert()
    : reusable.quatA.identity();

  const targetWorld = desiredDirection.clone().normalize();
  const delta = reusable.quatB.setFromUnitVectors(rest.worldAxis, targetWorld);
  const targetWorldQuaternion = reusable.quatC.copy(delta).multiply(rest.worldQuaternion);
  const targetLocalQuaternion = parentWorldInverse.multiply(targetWorldQuaternion);

  const smoothing = Number(smoothingInput.value);
  bone.quaternion.slerp(targetLocalQuaternion, smoothing * amount);
}

function applyTorso(results) {
  const landmarks = results.poseLandmarks;
  const leftShoulder = pointByIndex(landmarks, pose.leftShoulder);
  const rightShoulder = pointByIndex(landmarks, pose.rightShoulder);
  const leftHip = pointByIndex(landmarks, pose.leftHip);
  const rightHip = pointByIndex(landmarks, pose.rightHip);
  if (!leftShoulder || !rightShoulder || !leftHip || !rightHip) return;

  const shoulderCenter = reusable.vecA.copy(leftShoulder).add(rightShoulder).multiplyScalar(0.5);
  const hipCenter = reusable.vecB.copy(leftHip).add(rightHip).multiplyScalar(0.5);
  const torso = shoulderCenter.sub(hipCenter);
  const shoulderLine = rightShoulder.clone().sub(leftShoulder);
  const gain = Number(torsoGainInput.value);

  const chest = getBone('chest') || getBone('spine');
  if (chest) {
    chest.rotation.y += THREE.MathUtils.clamp(torso.x * 0.8 * gain, -0.45, 0.45);
    chest.rotation.z += THREE.MathUtils.clamp(shoulderLine.y * 1.1 * gain, -0.35, 0.35);
    chest.rotation.x += THREE.MathUtils.clamp(-torso.z * 0.8 * gain, -0.35, 0.35);
  }

  const nose = pointByIndex(landmarks, pose.nose);
  const leftEar = pointByIndex(landmarks, pose.leftEar);
  const rightEar = pointByIndex(landmarks, pose.rightEar);
  const head = getBone('head');
  if (head && nose && leftEar && rightEar) {
    const earCenter = leftEar.add(rightEar).multiplyScalar(0.5);
    const faceDirection = nose.sub(earCenter);
    head.rotation.y += THREE.MathUtils.clamp(faceDirection.x * 1.9, -0.55, 0.55);
    head.rotation.x += THREE.MathUtils.clamp(-faceDirection.y * 1.1, -0.35, 0.35);
  }
}

function applyArms(results) {
  const landmarks = results.poseLandmarks;
  const armGain = Number(armGainInput.value);
  const sides = [
    {
      side: 'left',
      upper: 'leftUpperArm',
      lower: 'leftLowerArm',
      hand: 'leftHand',
      shoulder: pose.leftShoulder,
      elbow: pose.leftElbow,
      wrist: pose.leftWrist,
    },
    {
      side: 'right',
      upper: 'rightUpperArm',
      lower: 'rightLowerArm',
      hand: 'rightHand',
      shoulder: pose.rightShoulder,
      elbow: pose.rightElbow,
      wrist: pose.rightWrist,
    },
  ];

  for (const item of sides) {
    const confidence = Math.min(
      landmarkVisibility(landmarks, item.shoulder),
      landmarkVisibility(landmarks, item.elbow),
      landmarkVisibility(landmarks, item.wrist),
    );
    if (confidence < 0.35) continue;
    driveBoneTowardWorldDirection(
      item.upper,
      directionBetween(landmarks, item.shoulder, item.elbow),
      armGain,
    );
    driveBoneTowardWorldDirection(
      item.lower,
      directionBetween(landmarks, item.elbow, item.wrist),
      armGain,
    );

    const handLandmarks = item.side === 'left' ? results.leftHandLandmarks : results.rightHandLandmarks;
    const handDirection = handLandmarks
      ? directionBetween(handLandmarks, 0, 9)
      : directionBetween(landmarks, item.elbow, item.wrist);
    driveBoneTowardWorldDirection(item.hand, handDirection, armGain * 0.8);
  }
}

function fingerBend(handLandmarks, chain) {
  const a = mpPoint(handLandmarks[chain[0]]);
  const b = mpPoint(handLandmarks[chain[1]]);
  const c = mpPoint(handLandmarks[chain[2]]);
  const d = mpPoint(handLandmarks[chain[3]]);
  if (!a || !b || !c || !d) return 0;
  const proximal = a.sub(b).normalize();
  const distal = d.sub(c).normalize();
  const dot = THREE.MathUtils.clamp(proximal.dot(distal), -1, 1);
  return THREE.MathUtils.clamp((1 - dot) * 0.85, 0, 1);
}

function applyHandFingers(results) {
  if (!driveHandsInput.checked) return;
  const hands = [
    { prefix: 'left', landmarks: results.leftHandLandmarks },
    { prefix: 'right', landmarks: results.rightHandLandmarks },
  ];
  for (const hand of hands) {
    if (!hand.landmarks) continue;
    for (const [finger, chain] of Object.entries(fingerChains)) {
      const bend = fingerBend(hand.landmarks, chain);
      for (const part of ['Proximal', 'Intermediate', 'Distal']) {
        const boneName = `${hand.prefix}${finger}${part}`;
        const bone = getBone(boneName);
        if (!bone) continue;
        const sign = hand.prefix === 'left' ? -1 : 1;
        const target = -bend * 1.05 * sign;
        bone.rotation.z += (target - bone.rotation.z) * Number(smoothingInput.value);
      }
    }
  }
}

function applyLegs(results) {
  if (!driveFullBodyInput.checked) return;
  const landmarks = results.poseLandmarks;
  const sides = [
    {
      upper: 'leftUpperLeg',
      lower: 'leftLowerLeg',
      foot: 'leftFoot',
      hip: pose.leftHip,
      knee: pose.leftKnee,
      ankle: pose.leftAnkle,
    },
    {
      upper: 'rightUpperLeg',
      lower: 'rightLowerLeg',
      foot: 'rightFoot',
      hip: pose.rightHip,
      knee: pose.rightKnee,
      ankle: pose.rightAnkle,
    },
  ];
  for (const item of sides) {
    const confidence = Math.min(
      landmarkVisibility(landmarks, item.hip),
      landmarkVisibility(landmarks, item.knee),
      landmarkVisibility(landmarks, item.ankle),
    );
    if (confidence < 0.45) continue;
    driveBoneTowardWorldDirection(item.upper, directionBetween(landmarks, item.hip, item.knee), 0.7);
    driveBoneTowardWorldDirection(item.lower, directionBetween(landmarks, item.knee, item.ankle), 0.7);
  }
}

function solveWithKalidokit(results) {
  const kit = window.Kalidokit;
  if (!kit) return null;
  const pose3D = results.poseWorldLandmarks || results.za || results.ea;
  const pose2D = results.poseLandmarks;
  // SysMocap keeps Kalidokit input in raw camera coordinates and mirrors only
  // the display layer. MediaPipe hand labels arrive reversed for this rigging
  // path, so left/right are intentionally swapped before Hand.solve.
  const leftHandLandmarks = results.rightHandLandmarks;
  const rightHandLandmarks = results.leftHandLandmarks;

  let riggedPose = null;
  let riggedLeftHand = null;
  let riggedRightHand = null;
  let riggedFace = null;

  if (pose2D && pose3D) {
    riggedPose = kit.Pose.solve(pose3D, pose2D, {
      runtime: 'mediapipe',
      video,
    });
  }
  if (driveHandsInput.checked && leftHandLandmarks) {
    riggedLeftHand = kit.Hand.solve(leftHandLandmarks, 'Left');
  }
  if (driveHandsInput.checked && rightHandLandmarks) {
    riggedRightHand = kit.Hand.solve(rightHandLandmarks, 'Right');
  }
  if (driveFaceInput.checked && results.faceLandmarks && kit.Face) {
    riggedFace = kit.Face.solve(results.faceLandmarks, {
      runtime: 'mediapipe',
      video,
    });
  }

  return { riggedPose, riggedLeftHand, riggedRightHand, riggedFace };
}

function applyKalidokitCapture(results) {
  const rigged = solveWithKalidokit(results);
  const riggedPose = rigged?.riggedPose;
  if (!riggedPose) {
    applyVectorCapture(results);
    return;
  }

  const armGain = Number(armGainInput.value);
  const torsoGain = Number(torsoGainInput.value);

  if (rigged.riggedFace?.head) {
    rigRotation('Neck', rigged.riggedFace.head, 0.55);
    applyFaceCapture(rigged.riggedFace);
  } else {
    relaxFaceCapture();
  }

  rigRotation('Hips', riggedPose.Hips?.rotation, 0.35);
  if (driveFullBodyInput.checked && riggedPose.Hips?.position) {
    rigPosition('Hips', {
      x: riggedPose.Hips.position.x * 0.45,
      y: riggedPose.Hips.position.y + 1,
      z: -riggedPose.Hips.position.z * 0.35,
    });
  }

  rigRotation('Chest', riggedPose.Chest, 0.25 * torsoGain);
  rigRotation('Spine', riggedPose.Spine, 0.45 * torsoGain);
  rigRotation('RightUpperArm', riggedPose.RightUpperArm, armGain);
  rigRotation('RightLowerArm', riggedPose.RightLowerArm, armGain);
  rigRotation('LeftUpperArm', riggedPose.LeftUpperArm, armGain);
  rigRotation('LeftLowerArm', riggedPose.LeftLowerArm, armGain);

  if (driveFullBodyInput.checked) {
    rigRotation('LeftUpperLeg', riggedPose.LeftUpperLeg, 0.8);
    rigRotation('LeftLowerLeg', riggedPose.LeftLowerLeg, 0.8);
    rigRotation('RightUpperLeg', riggedPose.RightUpperLeg, 0.8);
    rigRotation('RightLowerLeg', riggedPose.RightLowerLeg, 0.8);
  }

  if (driveHandsInput.checked && rigged.riggedLeftHand) {
    rigRotation('LeftHand', {
      z: riggedPose.LeftHand?.z ?? 0,
      y: rigged.riggedLeftHand.LeftWrist?.y ?? 0,
      x: rigged.riggedLeftHand.LeftWrist?.x ?? 0,
    }, armGain);
    for (const name of [
      'LeftRingProximal', 'LeftRingIntermediate', 'LeftRingDistal',
      'LeftIndexProximal', 'LeftIndexIntermediate', 'LeftIndexDistal',
      'LeftMiddleProximal', 'LeftMiddleIntermediate', 'LeftMiddleDistal',
      'LeftThumbProximal', 'LeftThumbIntermediate', 'LeftThumbDistal',
      'LeftLittleProximal', 'LeftLittleIntermediate', 'LeftLittleDistal',
    ]) {
      rigRotation(name, rigged.riggedLeftHand[name], 1);
    }
  }

  if (driveHandsInput.checked && rigged.riggedRightHand) {
    rigRotation('RightHand', {
      z: riggedPose.RightHand?.z ?? 0,
      y: rigged.riggedRightHand.RightWrist?.y ?? 0,
      x: rigged.riggedRightHand.RightWrist?.x ?? 0,
    }, armGain);
    for (const name of [
      'RightRingProximal', 'RightRingIntermediate', 'RightRingDistal',
      'RightIndexProximal', 'RightIndexIntermediate', 'RightIndexDistal',
      'RightMiddleProximal', 'RightMiddleIntermediate', 'RightMiddleDistal',
      'RightThumbProximal', 'RightThumbIntermediate', 'RightThumbDistal',
      'RightLittleProximal', 'RightLittleIntermediate', 'RightLittleDistal',
    ]) {
      rigRotation(name, rigged.riggedRightHand[name], 1);
    }
  }
}

function applyVectorCapture(results) {
  if (!currentVrm || !results?.poseLandmarks) return;
  currentVrm.humanoid.resetNormalizedPose();
  currentVrm.scene.updateMatrixWorld(true);
  applyTorso(results);
  applyArms(results);
  applyHandFingers(results);
  applyLegs(results);
}

function applyCaptureToVrm(results) {
  if (!currentVrm || !results?.poseLandmarks) return;
  if (retargetSolverInput.value === 'kalidokit') {
    applyKalidokitCapture(results);
  } else {
    applyVectorCapture(results);
  }
}

function cloneLandmarks(landmarks) {
  return landmarks?.map((item) => ({
    x: Number(item.x.toFixed(5)),
    y: Number(item.y.toFixed(5)),
    z: Number((item.z || 0).toFixed(5)),
    visibility: item.visibility == null ? undefined : Number(item.visibility.toFixed(4)),
  })) ?? null;
}

function cloneVrmBoneFrame() {
  const bones = {};
  if (!currentVrm) return bones;
  for (const name of captureBoneNames) {
    const bone = getBone(name);
    if (!bone) continue;
    bones[name] = {
      position: [
        Number(bone.position.x.toFixed(5)),
        Number(bone.position.y.toFixed(5)),
        Number(bone.position.z.toFixed(5)),
      ],
      quaternion: [
        Number(bone.quaternion.x.toFixed(6)),
        Number(bone.quaternion.y.toFixed(6)),
        Number(bone.quaternion.z.toFixed(6)),
        Number(bone.quaternion.w.toFixed(6)),
      ],
    };
  }
  return bones;
}

function recordFrame(results) {
  if (!isRecording) return;
  recordedFrames.push({
    t: Number(((performance.now() - recordStartedAt) / 1000).toFixed(4)),
    pose: cloneLandmarks(results.poseLandmarks),
    leftHand: cloneLandmarks(results.leftHandLandmarks),
    rightHand: cloneLandmarks(results.rightHandLandmarks),
    bones: cloneVrmBoneFrame(),
  });
  setRecordStatus(`Recording ${recordedFrames.length} frames`);
}

function drawResults(results) {
  overlayCtx.clearRect(0, 0, overlay.width, overlay.height);
  if (!results) return;
  overlayCtx.save();
  if (mirrorInput.checked) {
    overlayCtx.translate(overlay.width, 0);
    overlayCtx.scale(-1, 1);
  }
  overlayCtx.drawImage(results.image, 0, 0, overlay.width, overlay.height);
  const drawConnectors = window.drawConnectors;
  const drawLandmarks = window.drawLandmarks;
  if (drawConnectors && drawLandmarks) {
    drawConnectors(overlayCtx, results.poseLandmarks, window.POSE_CONNECTIONS, {
      color: '#28a38f',
      lineWidth: 2,
    });
    drawLandmarks(overlayCtx, results.poseLandmarks, {
      color: '#ffffff',
      lineWidth: 1,
      radius: 1.8,
    });
    for (const hand of [results.leftHandLandmarks, results.rightHandLandmarks]) {
      if (!hand) continue;
      drawConnectors(overlayCtx, hand, window.HAND_CONNECTIONS, {
        color: '#f2a33a',
        lineWidth: 2,
      });
      drawLandmarks(overlayCtx, hand, {
        color: '#ffffff',
        lineWidth: 1,
        radius: 2,
      });
    }
  }
  overlayCtx.restore();
}

function updateTrackingUi(results) {
  const poseCount = results.poseLandmarks?.length || 0;
  const handCount = (results.leftHandLandmarks ? 1 : 0) + (results.rightHandLandmarks ? 1 : 0);
  const score = Math.min(1, (poseCount ? 0.6 : 0) + handCount * 0.2);
  trackingMeterEl.style.width = `${Math.round(score * 100)}%`;
  setTrackingStatus(`Pose ${poseCount ? 'locked' : 'missing'} · hands ${handCount}/2`);
}

async function createHolistic() {
  if (holistic) return holistic;
  if (!window.Holistic) throw new Error('MediaPipe Holistic failed to load');
  if (retargetSolverInput.value === 'kalidokit' && !window.Kalidokit) {
    retargetSolverInput.value = 'vector';
    setStatus('Kalidokit failed to load; using vector fallback');
  }
  holistic = new window.Holistic({
    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/holistic/${file}`,
  });
  holistic.setOptions({
    modelComplexity: 1,
    smoothLandmarks: true,
    enableSegmentation: false,
    refineFaceLandmarks: true,
    minDetectionConfidence: 0.55,
    minTrackingConfidence: 0.55,
  });
  holistic.onResults((results) => {
    latestResults = results;
    drawResults(results);
    updateTrackingUi(results);
    applyCaptureToVrm(results);
    recordFrame(results);
  });
  return holistic;
}

async function startCamera() {
  await createHolistic();
  if (!window.Camera) throw new Error('MediaPipe camera utils failed to load');
  cameraSource = new window.Camera(video, {
    onFrame: async () => {
      await holistic.send({ image: video });
    },
    width: 960,
    height: 540,
  });
  await cameraSource.start();
  document.body.classList.toggle('no-mirror', !mirrorInput.checked);
  startCameraBtn.disabled = true;
  stopCameraBtn.disabled = false;
  setStatus('Camera tracking active');
}

function stopCamera() {
  cameraSource?.stop();
  cameraSource = null;
  const stream = video.srcObject;
  if (stream) stream.getTracks().forEach((track) => track.stop());
  video.srcObject = null;
  startCameraBtn.disabled = false;
  stopCameraBtn.disabled = true;
  trackingMeterEl.style.width = '0%';
  overlayCtx.clearRect(0, 0, overlay.width, overlay.height);
  setTrackingStatus('Camera stopped');
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function findCaptureParentName(bone) {
  let cursor = bone?.parent;
  while (cursor) {
    for (const name of captureBoneNames) {
      if (getBone(name) === cursor) return name;
    }
    cursor = cursor.parent;
  }
  return null;
}

function fbxArray(values) {
  return values.map((value) => Number.isFinite(value) ? Number(value.toFixed(6)) : 0).join(',');
}

function fbxKeyTimes(frames) {
  const tick = 46186158000;
  return frames.map((frame) => Math.round(frame.t * tick));
}

function boneEulerDegrees(frame, name) {
  const q = frame.bones?.[name]?.quaternion;
  if (!q) return [0, 0, 0];
  const euler = new THREE.Euler().setFromQuaternion(
    new THREE.Quaternion(q[0], q[1], q[2], q[3]),
    'XYZ',
  );
  return [
    THREE.MathUtils.radToDeg(euler.x),
    THREE.MathUtils.radToDeg(euler.y),
    THREE.MathUtils.radToDeg(euler.z),
  ];
}

function fbxCurve(id, values) {
  return [
    `\tAnimationCurve: ${id}, "AnimCurve::", "" {`,
    `\t\tDefault: 0`,
    `\t\tKeyVer: 4008`,
    `\t\tKeyTime: *${values.times.length} {`,
    `\t\t\ta: ${values.times.join(',')}`,
    `\t\t}`,
    `\t\tKeyValueFloat: *${values.values.length} {`,
    `\t\t\ta: ${fbxArray(values.values)}`,
    `\t\t}`,
    `\t\tKeyAttrFlags: *${values.values.length} {`,
    `\t\t\ta: ${values.values.map(() => 24836).join(',')}`,
    `\t\t}`,
    `\t\tKeyAttrDataFloat: *${values.values.length * 4} {`,
    `\t\t\ta: ${values.values.map(() => '0,0,0,0').join(',')}`,
    `\t\t}`,
    `\t\tKeyAttrRefCount: *${values.values.length} {`,
    `\t\t\ta: ${values.values.map(() => 1).join(',')}`,
    `\t\t}`,
    `\t}`,
  ].join('\n');
}

function buildAsciiFbx(frames) {
  const presentBones = captureBoneNames.filter((name) => frames.some((frame) => frame.bones?.[name]));
  const baseId = 100000;
  let nextId = baseId;
  const rootId = nextId++;
  const stackId = nextId++;
  const layerId = nextId++;
  const modelIds = new Map();
  const nodeIds = new Map();
  const curveIds = new Map();
  const curveBlocks = [];
  const connections = [];
  const times = fbxKeyTimes(frames);

  for (const name of presentBones) modelIds.set(name, nextId++);

  for (const name of presentBones) {
    for (const property of ['T', 'R']) {
      const nodeId = nextId++;
      nodeIds.set(`${name}.${property}`, nodeId);
      for (const axis of ['X', 'Y', 'Z']) {
        curveIds.set(`${name}.${property}.${axis}`, nextId++);
      }
    }
  }

  connections.push(`\tC: "OO",${layerId},${stackId}`);

  const objectBlocks = [
    `\tModel: ${rootId}, "Model::Tanyue_Motion_Capture", "Null" {`,
    `\t\tProperties70:  {`,
    `\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",0,0,0`,
    `\t\t\tP: "Lcl Rotation", "Lcl Rotation", "", "A",0,0,0`,
    `\t\t}`,
    `\t}`,
    `\tAnimationStack: ${stackId}, "AnimStack::tanyue_capture", "" {}`,
    `\tAnimationLayer: ${layerId}, "AnimLayer::BaseLayer", "" {}`,
  ];

  for (const name of presentBones) {
    const firstFrame = frames.find((frame) => frame.bones?.[name]);
    const position = firstFrame?.bones?.[name]?.position ?? [0, 0, 0];
    const rotation = boneEulerDegrees(firstFrame, name);
    const modelId = modelIds.get(name);
    objectBlocks.push([
      `\tModel: ${modelId}, "Model::${name}", "LimbNode" {`,
      `\t\tProperties70:  {`,
      `\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",${fbxArray(position)}`,
      `\t\t\tP: "Lcl Rotation", "Lcl Rotation", "", "A",${fbxArray(rotation)}`,
      `\t\t}`,
      `\t}`,
    ].join('\n'));

    const parentName = findCaptureParentName(getBone(name));
    const parentId = parentName && modelIds.has(parentName) ? modelIds.get(parentName) : rootId;
    connections.push(`\tC: "OO",${modelId},${parentId}`);

    for (const property of ['T', 'R']) {
      const nodeId = nodeIds.get(`${name}.${property}`);
      const propertyName = property === 'T' ? 'Lcl Translation' : 'Lcl Rotation';
      objectBlocks.push(`\tAnimationCurveNode: ${nodeId}, "AnimCurveNode::${name}_${property}", "" {}`);
      connections.push(`\tC: "OO",${nodeId},${layerId}`);
      connections.push(`\tC: "OP",${nodeId},${modelId},"${propertyName}"`);

      for (const axisIndex of [0, 1, 2]) {
        const axis = ['X', 'Y', 'Z'][axisIndex];
        const values = frames.map((frame) => {
          if (property === 'T') return frame.bones?.[name]?.position?.[axisIndex] ?? 0;
          return boneEulerDegrees(frame, name)[axisIndex];
        });
        const curveId = curveIds.get(`${name}.${property}.${axis}`);
        curveBlocks.push(fbxCurve(curveId, { times, values }));
        connections.push(`\tC: "OP",${curveId},${nodeId},"d|${axis}"`);
      }
    }
  }

  const durationTick = times.at(-1) ?? 0;
  return [
    '; FBX 7.4.0 project file',
    '; Generated by Tanyue Motion Generator',
    'FBXHeaderExtension:  {',
    '\tFBXHeaderVersion: 1003',
    '\tFBXVersion: 7400',
    '}',
    'GlobalSettings:  {',
    '\tProperties70:  {',
    '\t\tP: "UpAxis", "int", "Integer", "",1',
    '\t\tP: "UpAxisSign", "int", "Integer", "",1',
    '\t\tP: "FrontAxis", "int", "Integer", "",2',
    '\t\tP: "FrontAxisSign", "int", "Integer", "",1',
    '\t\tP: "CoordAxis", "int", "Integer", "",0',
    '\t\tP: "CoordAxisSign", "int", "Integer", "",1',
    '\t}',
    '}',
    'Definitions:  {',
    `\tCount: ${objectBlocks.length + curveBlocks.length}`,
    '}',
    'Objects:  {',
    ...objectBlocks,
    ...curveBlocks,
    '}',
    'Connections:  {',
    ...connections,
    '}',
    'Takes:  {',
    '\tCurrent: "tanyue_capture"',
    '\tTake: "tanyue_capture" {',
    '\t\tFileName: "tanyue_capture.takes"',
    `\t\tLocalTime: 0,${durationTick}`,
    `\t\tReferenceTime: 0,${durationTick}`,
    '\t}',
    '}',
    '',
  ].join('\n');
}

function exportFbxRecording() {
  if (!recordedFrames.length || !currentVrm) return;
  const filename = `tanyue-motion-capture-${Date.now()}.fbx`;
  const fbx = buildAsciiFbx(recordedFrames);
  downloadBlob(new Blob([fbx], { type: 'application/octet-stream' }), filename);
  setRecordStatus(`Captured ${recordedFrames.length} frames · exported ${filename}`);
}

function beginRecordingNow(durationSeconds) {
  recordedFrames = [];
  recordStartedAt = performance.now();
  isRecording = true;
  startRecordBtn.disabled = true;
  stopRecordBtn.disabled = false;
  downloadRecordBtn.disabled = true;
  setRecordStatus(`Recording ${durationSeconds}s...`);
  recordTimer = window.setTimeout(() => {
    stopRecording({ autoExport: true });
  }, durationSeconds * 1000);
}

function showCountdown(value) {
  countdownEl.hidden = false;
  countdownEl.textContent = value;
}

function hideCountdown() {
  countdownEl.hidden = true;
  countdownEl.textContent = '';
}

function startRecording() {
  if (!currentVrm) {
    setRecordStatus('VRM is not ready');
    return;
  }
  if (!latestResults?.poseLandmarks) {
    setRecordStatus('Start camera and wait for pose lock before recording');
    return;
  }
  const durationSeconds = THREE.MathUtils.clamp(
    Number.parseFloat(recordDurationInput.value) || 5,
    1,
    120,
  );
  recordDurationInput.value = String(durationSeconds);

  startRecordBtn.disabled = true;
  stopRecordBtn.disabled = true;
  downloadRecordBtn.disabled = true;
  let count = 3;
  showCountdown(count);
  setRecordStatus(`Recording starts in ${count}...`);
  countdownTimer = window.setInterval(() => {
    count -= 1;
    if (count > 0) {
      showCountdown(count);
      setRecordStatus(`Recording starts in ${count}...`);
      return;
    }
    window.clearInterval(countdownTimer);
    countdownTimer = null;
    showCountdown('GO');
    window.setTimeout(hideCountdown, 420);
    beginRecordingNow(durationSeconds);
  }, 1000);
}

function stopRecording(options = {}) {
  if (countdownTimer) {
    window.clearInterval(countdownTimer);
    countdownTimer = null;
    hideCountdown();
  }
  if (recordTimer) {
    window.clearTimeout(recordTimer);
    recordTimer = null;
  }
  isRecording = false;
  startRecordBtn.disabled = false;
  stopRecordBtn.disabled = true;
  downloadRecordBtn.disabled = recordedFrames.length === 0;
  setRecordStatus(`Captured ${recordedFrames.length} frames`);
  if (options.autoExport && recordedFrames.length) {
    exportFbxRecording();
  }
}

function downloadRecording() {
  const payload = {
    version: 1,
    source: 'tanyue-motion-generator',
    createdAt: new Date().toISOString(),
    fpsApprox: recordedFrames.length > 1
      ? Math.round(recordedFrames.length / recordedFrames.at(-1).t)
      : 0,
    model: modelParam || 'LiuRuYan.vrm',
    mirror: mirrorInput.checked,
    solver: retargetSolverInput.value,
    frames: recordedFrames,
  };
  downloadBlob(
    new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
    `tanyue-motion-capture-${Date.now()}.json`,
  );
}

function bindControls() {
  startCameraBtn.addEventListener('click', () => {
    startCamera().catch((error) => {
      console.error(error);
      setStatus(`Camera failed: ${error.message || error}`);
    });
  });
  stopCameraBtn.addEventListener('click', stopCamera);
  startRecordBtn.addEventListener('click', startRecording);
  stopRecordBtn.addEventListener('click', () => stopRecording({ autoExport: true }));
  downloadRecordBtn.addEventListener('click', downloadRecording);
  resetPoseBtn.addEventListener('click', resetVrmPose);
  mirrorInput.addEventListener('input', () => {
    document.body.classList.toggle('no-mirror', !mirrorInput.checked);
  });
  showVrmSkeletonInput.addEventListener('input', () => {
    vrmSkeletonCanvas.classList.toggle('is-hidden', !showVrmSkeletonInput.checked);
    drawVrmSkeleton();
  });
  retargetSolverInput.addEventListener('change', () => {
    resetVrmPose();
    setStatus(`Retarget solver: ${retargetSolverInput.value}`);
  });
}

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  resize();
  const delta = clock.getDelta();
  orbit.update();
  currentVrm?.update(delta);
  renderer.render(scene, camera);
  drawVrmSkeleton();
}

window.tanyueMotionGenerator = {
  get latestResults() {
    return latestResults;
  },
  get recordedFrames() {
    return recordedFrames;
  },
  resetVrmPose,
  startCamera,
  stopCamera,
  solveWithKalidokit,
};

bindControls();
loadVrm();
animate();
