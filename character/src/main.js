import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const canvas = document.querySelector('#vrm-canvas');
const statusEl = document.querySelector('#status');
const bridgeStatusEl = document.querySelector('#bridgeStatus');
const pageParams = new URLSearchParams(window.location.search);
if (pageParams.get('embed') === '1' || pageParams.get('embed') === 'true') {
  document.body.classList.add('embed');
}

const controlsState = {
  idle: true,
  blink: true,
  energy: 0.45,
  motionLoop: false,
  motionSpeed: 1,
  headYaw: 0,
  headPitch: 0,
  bodyYaw: 0,
  leftArm: 72,
  rightArm: -72,
  leftElbow: 10,
  rightElbow: -10,
  mouthAa: 0,
  mouthOh: 0,
  lipSync: true,
  lipSyncSensitivity: 2.8,
  lipSyncSmoothing: 0.35,
  expression: 'neutral',
  expressionIntensity: 1,
  pose: 'relaxed',
};

const posePresets = {
  relaxed: {
    pose: 'relaxed',
    expression: 'relaxed',
    headYaw: 0,
    headPitch: 0,
    bodyYaw: 0,
    leftArm: 72,
    rightArm: -72,
    leftElbow: 10,
    rightElbow: -10,
    energy: 0.35,
  },
  listening: {
    pose: 'listening',
    expression: 'relaxed',
    headYaw: 4,
    headPitch: -3,
    bodyYaw: 4,
    leftArm: 62,
    rightArm: -66,
    leftElbow: 24,
    rightElbow: -22,
    energy: 0.42,
  },
  shy: {
    pose: 'shy',
    expression: 'happy',
    headYaw: -8,
    headPitch: 8,
    bodyYaw: -6,
    leftArm: 46,
    rightArm: -48,
    leftElbow: 58,
    rightElbow: -58,
    energy: 0.32,
  },
  happy: {
    pose: 'happy',
    expression: 'happy',
    headYaw: 0,
    headPitch: -6,
    bodyYaw: 0,
    leftArm: 96,
    rightArm: -96,
    leftElbow: 34,
    rightElbow: -34,
    energy: 0.82,
  },
  wave: {
    pose: 'wave',
    expression: 'happy',
    headYaw: 6,
    headPitch: -4,
    bodyYaw: 5,
    leftArm: 70,
    rightArm: -118,
    leftElbow: 10,
    rightElbow: -64,
    energy: 0.72,
  },
  thinking: {
    pose: 'thinking',
    expression: 'relaxed',
    headYaw: -5,
    headPitch: 7,
    bodyYaw: -4,
    leftArm: 54,
    rightArm: -42,
    leftElbow: 28,
    rightElbow: -70,
    energy: 0.28,
  },
};

const fbxMotions = {};
let defaultIdleMotion = 'angry';

const mixamoBoneMap = {
  mixamorigHips: 'hips',
  mixamorigSpine: 'spine',
  mixamorigSpine1: 'chest',
  mixamorigSpine2: 'upperChest',
  mixamorigNeck: 'neck',
  mixamorigHead: 'head',
  mixamorigLeftShoulder: 'leftShoulder',
  mixamorigLeftArm: 'leftUpperArm',
  mixamorigLeftForeArm: 'leftLowerArm',
  mixamorigLeftHand: 'leftHand',
  mixamorigLeftHandThumb1: 'leftThumbMetacarpal',
  mixamorigLeftHandThumb2: 'leftThumbProximal',
  mixamorigLeftHandThumb3: 'leftThumbDistal',
  mixamorigLeftHandIndex1: 'leftIndexProximal',
  mixamorigLeftHandIndex2: 'leftIndexIntermediate',
  mixamorigLeftHandIndex3: 'leftIndexDistal',
  mixamorigLeftHandMiddle1: 'leftMiddleProximal',
  mixamorigLeftHandMiddle2: 'leftMiddleIntermediate',
  mixamorigLeftHandMiddle3: 'leftMiddleDistal',
  mixamorigLeftHandRing1: 'leftRingProximal',
  mixamorigLeftHandRing2: 'leftRingIntermediate',
  mixamorigLeftHandRing3: 'leftRingDistal',
  mixamorigLeftHandPinky1: 'leftLittleProximal',
  mixamorigLeftHandPinky2: 'leftLittleIntermediate',
  mixamorigLeftHandPinky3: 'leftLittleDistal',
  mixamorigRightShoulder: 'rightShoulder',
  mixamorigRightArm: 'rightUpperArm',
  mixamorigRightForeArm: 'rightLowerArm',
  mixamorigRightHand: 'rightHand',
  mixamorigRightHandPinky1: 'rightLittleProximal',
  mixamorigRightHandPinky2: 'rightLittleIntermediate',
  mixamorigRightHandPinky3: 'rightLittleDistal',
  mixamorigRightHandRing1: 'rightRingProximal',
  mixamorigRightHandRing2: 'rightRingIntermediate',
  mixamorigRightHandRing3: 'rightRingDistal',
  mixamorigRightHandMiddle1: 'rightMiddleProximal',
  mixamorigRightHandMiddle2: 'rightMiddleIntermediate',
  mixamorigRightHandMiddle3: 'rightMiddleDistal',
  mixamorigRightHandIndex1: 'rightIndexProximal',
  mixamorigRightHandIndex2: 'rightIndexIntermediate',
  mixamorigRightHandIndex3: 'rightIndexDistal',
  mixamorigRightHandThumb1: 'rightThumbMetacarpal',
  mixamorigRightHandThumb2: 'rightThumbProximal',
  mixamorigRightHandThumb3: 'rightThumbDistal',
  mixamorigLeftUpLeg: 'leftUpperLeg',
  mixamorigLeftLeg: 'leftLowerLeg',
  mixamorigLeftFoot: 'leftFoot',
  mixamorigLeftToeBase: 'leftToes',
  mixamorigRightUpLeg: 'rightUpperLeg',
  mixamorigRightLeg: 'rightLowerLeg',
  mixamorigRightFoot: 'rightFoot',
  mixamorigRightToeBase: 'rightToes',
};

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

const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
keyLight.position.set(1.8, 3.2, 2.0);
scene.add(keyLight);
scene.add(new THREE.HemisphereLight(0xffffff, 0xb7b1a3, 1.8));

let currentVrm = null;
let currentMixer = null;
let currentMotionAction = null;
let blinkUntil = 0;
let nextBlinkAt = 1.6;
let bridgeEvents = null;

const lipSyncState = {
  audioContext: null,
  analyser: null,
  data: null,
  source: null,
  stream: null,
  target: 0,
  level: 0,
  lastExternalAt: 0,
};

const mediaElementSources = new WeakMap();

function resize() {
  const { clientWidth, clientHeight } = canvas;
  renderer.setSize(clientWidth, clientHeight, false);
  camera.aspect = clientWidth / Math.max(clientHeight, 1);
  camera.updateProjectionMatrix();
}

window.addEventListener('resize', resize);

function rad(degrees) {
  return (degrees * Math.PI) / 180;
}

function setStatus(message) {
  statusEl.textContent = message;
}

function setBridgeStatus(message) {
  if (bridgeStatusEl) bridgeStatusEl.textContent = message;
}

function getBone(name) {
  return currentVrm?.humanoid?.getNormalizedBoneNode(name) ?? null;
}

function expressionNames() {
  const manager = currentVrm?.expressionManager;
  if (!manager) return ['neutral', 'happy', 'relaxed', 'sad', 'surprised', 'angry'];
  return Object.keys(manager.expressionMap || {});
}

function setExpression(name, value) {
  const manager = currentVrm?.expressionManager;
  if (!manager || !name) return;
  if (manager.expressionMap[name]) manager.setValue(name, value);
}

function clearExpressions() {
  const manager = currentVrm?.expressionManager;
  if (!manager) return;
  for (const name of expressionNames()) {
    if (manager.expressionMap[name]) manager.setValue(name, 0);
  }
}

function resetFace() {
  blinkUntil = 0;
  controlsState.mouthAa = 0;
  controlsState.mouthOh = 0;
  lipSyncState.target = 0;
  lipSyncState.level = 0;
  clearExpressions();
}

function clamp01(value) {
  return Math.min(Math.max(value, 0), 1);
}

function ensureAudioContext() {
  if (!lipSyncState.audioContext) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    lipSyncState.audioContext = new AudioContextClass();
  }
  return lipSyncState.audioContext;
}

function disconnectLipSyncSource() {
  if (lipSyncState.source?.disconnect) {
    try {
      lipSyncState.source.disconnect();
    } catch {
      // Source may already be disconnected by the browser.
    }
  }
  if (lipSyncState.stream) {
    lipSyncState.stream.getTracks().forEach((track) => track.stop());
  }
  lipSyncState.source = null;
  lipSyncState.stream = null;
  lipSyncState.analyser = null;
  lipSyncState.data = null;
  lipSyncState.target = 0;
  lipSyncState.level = 0;
}

function connectLipSyncSource(source, { connectToOutput = false } = {}) {
  const audioContext = ensureAudioContext();
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 1024;
  analyser.smoothingTimeConstant = 0.2;

  disconnectLipSyncSource();
  source.connect(analyser);
  if (connectToOutput) source.connect(audioContext.destination);

  lipSyncState.source = source;
  lipSyncState.analyser = analyser;
  lipSyncState.data = new Uint8Array(analyser.fftSize);
  controlsState.lipSync = true;
}

async function startMicrophoneLipSync() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const audioContext = ensureAudioContext();
  if (audioContext.state === 'suspended') await audioContext.resume();
  const source = audioContext.createMediaStreamSource(stream);
  connectLipSyncSource(source);
  lipSyncState.stream = stream;
  setStatus('Microphone lip sync enabled');
}

async function connectLipSyncElement(elementOrSelector) {
  const element =
    typeof elementOrSelector === 'string'
      ? document.querySelector(elementOrSelector)
      : elementOrSelector;
  if (!element) throw new Error('Audio element not found');

  const audioContext = ensureAudioContext();
  if (audioContext.state === 'suspended') await audioContext.resume();

  let source = mediaElementSources.get(element);
  if (!source) {
    source = audioContext.createMediaElementSource(element);
    mediaElementSources.set(element, source);
  }
  connectLipSyncSource(source, { connectToOutput: true });
  return element;
}

async function playAudioUrl(url) {
  const audio = new Audio(url);
  audio.crossOrigin = 'anonymous';
  await connectLipSyncElement(audio);
  await audio.play();
  return audio;
}

async function playAudioBlob(blob) {
  const url = URL.createObjectURL(blob);
  const audio = await playAudioUrl(url);
  audio.addEventListener('ended', () => URL.revokeObjectURL(url), { once: true });
  return audio;
}

function setMouth({ aa = controlsState.mouthAa, oh = controlsState.mouthOh } = {}) {
  controlsState.mouthAa = clamp01(Number(aa) || 0);
  controlsState.mouthOh = clamp01(Number(oh) || 0);
  const aaSlider = document.querySelector('#mouthAa');
  const ohSlider = document.querySelector('#mouthOh');
  if (aaSlider) aaSlider.value = controlsState.mouthAa;
  if (ohSlider) ohSlider.value = controlsState.mouthOh;
}

function setLipSyncLevel(level) {
  lipSyncState.target = clamp01(Number(level) || 0);
  lipSyncState.lastExternalAt = performance.now();
  controlsState.lipSync = true;
}

function updateLipSync() {
  if (!controlsState.lipSync) {
    lipSyncState.target = 0;
  } else if (lipSyncState.analyser && lipSyncState.data) {
    lipSyncState.analyser.getByteTimeDomainData(lipSyncState.data);
    let sum = 0;
    for (const sample of lipSyncState.data) {
      const centered = (sample - 128) / 128;
      sum += centered * centered;
    }
    const rms = Math.sqrt(sum / lipSyncState.data.length);
    lipSyncState.target = clamp01(Math.max(0, rms - 0.015) * controlsState.lipSyncSensitivity * 4);
  } else if (performance.now() - lipSyncState.lastExternalAt > 180) {
    lipSyncState.target *= 0.82;
  }

  const smoothing = controlsState.lipSyncSmoothing;
  lipSyncState.level += (lipSyncState.target - lipSyncState.level) * smoothing;
  return lipSyncState.level;
}

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

function bindControls() {
  for (const [id, initial] of Object.entries(controlsState)) {
    const el = document.querySelector(`#${id}`);
    if (!el) continue;
    if (el.type === 'checkbox') {
      el.checked = Boolean(initial);
      el.addEventListener('input', () => {
        controlsState[id] = el.checked;
      });
    } else if (el.type === 'range') {
      el.value = initial;
      el.addEventListener('input', () => {
        controlsState[id] = Number(el.value);
      });
    }
  }

  document.querySelectorAll('[data-expression]').forEach((button) => {
    button.addEventListener('click', () => {
      controlsState.expression = button.dataset.expression;
    });
  });

  document.querySelectorAll('[data-pose]').forEach((button) => {
    button.addEventListener('click', () => {
      applyPosePreset(button.dataset.pose);
    });
  });

  document.querySelectorAll('[data-motion]').forEach((button) => {
    button.addEventListener('click', () => {
      playMotion(button.dataset.motion);
    });
  });

  document.querySelector('#startMicLipSync')?.addEventListener('click', () => {
    startMicrophoneLipSync().catch((error) => {
      console.error('Could not start microphone lip sync.', error);
      setStatus('Microphone lip sync failed');
    });
  });

  document.querySelector('#stopLipSync')?.addEventListener('click', () => {
    disconnectLipSyncSource();
    controlsState.lipSync = false;
    const toggle = document.querySelector('#lipSync');
    if (toggle) toggle.checked = false;
    setMouth({ aa: 0, oh: 0 });
    setStatus('Lip sync stopped');
  });
}

async function loadMotionManifest() {
  try {
    const response = await fetch('./motions/manifest.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const manifest = await response.json();
    const motions = Array.isArray(manifest) ? manifest : manifest.motions || [];
    defaultIdleMotion = Array.isArray(manifest)
      ? defaultIdleMotion
      : manifest.defaultIdleMotion || defaultIdleMotion;
    const container = document.querySelector('#motionButtons');

    for (const motion of motions) {
      if (!motion.id || !motion.file) continue;
      fbxMotions[motion.id] = motion.file;

      if (!container || container.querySelector(`[data-motion="${motion.id}"]`)) continue;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.motion = motion.id;
      button.textContent = motion.label || motion.id;
      button.addEventListener('click', () => {
        playMotion(motion.id);
      });
      container.insertBefore(button, container.firstElementChild);
    }

    setStatus(`VRM ready · ${Object.keys(fbxMotions).length} motions`);
    if (defaultIdleMotion && fbxMotions[defaultIdleMotion]) {
      controlsState.motionLoop = true;
      const loopToggle = document.querySelector('#motionLoop');
      if (loopToggle) loopToggle.checked = true;
      playMotion(defaultIdleMotion);
    }
  } catch (error) {
    console.error('Could not load motion manifest.', error);
    setStatus('VRM ready · motion manifest failed');
  }
}

function setCharacterState(nextState = {}) {
  for (const [key, value] of Object.entries(nextState)) {
    if (!(key in controlsState)) continue;
    controlsState[key] = value;

    const el = document.querySelector(`#${key}`);
    if (!el) continue;
    if (el.type === 'checkbox') {
      el.checked = Boolean(value);
    } else if (el.type === 'range') {
      el.value = Number(value);
    }
  }
}

function getCapabilities() {
  return {
    poses: Object.keys(posePresets),
    motions: Object.keys(fbxMotions),
    expressions: expressionNames(),
    stateKeys: Object.keys(controlsState),
    lipSync: {
      audioUrl: true,
      audioBlob: true,
      microphone: true,
      externalLevel: true,
      mouthShapes: ['aa', 'oh'],
    },
  };
}

function applyPosePreset(name) {
  stopMotion();
  const preset = posePresets[name];
  if (!preset) return;
  setCharacterState(preset);
}

function stopMotion() {
  resetFace();
  if (currentMotionAction) {
    currentMotionAction.fadeOut(0.2);
    currentMotionAction = null;
  }
  if (currentMixer) {
    currentMixer.stopAllAction();
    currentMixer = null;
  }
  currentVrm?.humanoid?.resetNormalizedPose();
}

function playIdleMotion() {
  if (!defaultIdleMotion || !fbxMotions[defaultIdleMotion]) {
    applyPosePreset('relaxed');
    return;
  }
  controlsState.motionLoop = true;
  const loopToggle = document.querySelector('#motionLoop');
  if (loopToggle) loopToggle.checked = true;
  playMotion(defaultIdleMotion);
}

function normalizeMixamoBoneName(rawName) {
  return rawName
    .replace(/^mixamorig[:_]?/i, '')
    .replace(/^mixamo[:_]?/i, '')
    .replace(/[^A-Za-z0-9]/g, '');
}

function mixamoRigMapKey(rawName) {
  const normalized = normalizeMixamoBoneName(rawName);
  return normalized ? `mixamorig${normalized}` : rawName;
}

function findFbxObject(root, mixamoName) {
  const normalized = normalizeMixamoBoneName(mixamoName);
  return (
    root.getObjectByName(mixamoName) ??
    root.getObjectByName(`mixamorig:${normalized}`) ??
    root.getObjectByName(`mixamorig${normalized}`)
  );
}

function retargetFbxClipToVrm(fbx, sourceClip) {
  fbx.updateMatrixWorld(true);
  currentVrm.scene.updateMatrixWorld(true);

  const tracks = [];
  const restRotationInverse = new THREE.Quaternion();
  const parentRestWorldRotation = new THREE.Quaternion();
  const vrmRootY = currentVrm.humanoid.normalizedRestPose?.hips?.position?.[1] ?? 1;
  const motionHipsHeight = findFbxObject(fbx, 'mixamorigHips')?.position.y ?? 1;
  const hipsPositionScale = Math.abs(vrmRootY / motionHipsHeight) || 1;

  for (const track of sourceClip.tracks) {
    const trackSplitted = track.name.split('.');
    const mixamoRigName = trackSplitted[0];
    const propertyName = trackSplitted[1];
    const vrmBoneName = mixamoBoneMap[mixamoRigMapKey(mixamoRigName)];
    if (!vrmBoneName) continue;

    const vrmBone = getBone(vrmBoneName);
    const mixamoBone = findFbxObject(fbx, mixamoRigName);
    if (!vrmBone || !mixamoBone) continue;

    if (propertyName === 'quaternion') {
      mixamoBone.getWorldQuaternion(restRotationInverse).invert();
      parentRestWorldRotation.identity();
      mixamoBone.parent?.getWorldQuaternion(parentRestWorldRotation);
      const values = new Float32Array(track.values.length);

      for (let i = 0; i < track.values.length; i += 4) {
        const quat = new THREE.Quaternion(
          track.values[i],
          track.values[i + 1],
          track.values[i + 2],
          track.values[i + 3],
        );
        quat
          .premultiply(parentRestWorldRotation)
          .multiply(restRotationInverse);

        values[i] = quat.x;
        values[i + 1] = quat.y;
        values[i + 2] = quat.z;
        values[i + 3] = quat.w;
      }

      tracks.push(new THREE.QuaternionKeyframeTrack(`${vrmBone.name}.quaternion`, track.times, values));
    } else if (propertyName === 'position' && vrmBoneName === 'hips') {
      const values = new Float32Array(track.values.length);
      for (let i = 0; i < track.values.length; i += 3) {
        const sign = currentVrm.meta?.metaVersion === '0' ? -1 : 1;
        values[i] = track.values[i] * hipsPositionScale * sign;
        values[i + 1] = track.values[i + 1] * hipsPositionScale;
        values[i + 2] = track.values[i + 2] * hipsPositionScale * sign;
      }

      tracks.push(new THREE.VectorKeyframeTrack(`${vrmBone.name}.position`, track.times, values));
    }
  }

  return new THREE.AnimationClip(sourceClip.name || 'fbx-retargeted', sourceClip.duration, tracks);
}

function loadFbxMotion(name) {
  if (!currentVrm) return Promise.reject(new Error('VRM is not ready'));
  const fileName = fbxMotions[name];
  if (!fileName) return Promise.reject(new Error(`No FBX motion registered for ${name}`));

  const loader = new FBXLoader();
  return loader.loadAsync(`./motions/${fileName}`).then((fbx) => {
    const sourceClip = fbx.animations?.[0];
    if (!sourceClip) throw new Error(`No animation clip in ${fileName}`);

    const clip = retargetFbxClipToVrm(fbx, sourceClip);
    if (!clip.tracks.length) throw new Error(`No retargetable tracks in ${fileName}`);

    currentVrm.humanoid.resetNormalizedPose();
    currentMixer = new THREE.AnimationMixer(currentVrm.scene);
    currentMotionAction = currentMixer.clipAction(clip);
    currentMotionAction.reset();
    currentMotionAction.setLoop(
      controlsState.motionLoop ? THREE.LoopRepeat : THREE.LoopOnce,
      controlsState.motionLoop ? Infinity : 1,
    );
    currentMotionAction.clampWhenFinished = true;
    currentMotionAction.fadeIn(0.15).play();
    currentMixer.timeScale = controlsState.motionSpeed;
    if (!controlsState.motionLoop && name !== defaultIdleMotion) {
      const mixer = currentMixer;
      mixer.addEventListener('finished', () => {
        if (currentMixer !== mixer) return;
        window.setTimeout(() => {
          if (currentMixer === mixer) playIdleMotion();
        }, 250);
      });
    }
    resetFace();
    setStatus(`Playing FBX ${fileName} (${clip.tracks.length} tracks)`);
  });
}

function playMotion(name) {
  if (name === 'stop') {
    stopMotion();
    applyPosePreset('relaxed');
    setStatus('Motion stopped');
    return;
  }

  stopMotion();
  if (fbxMotions[name]) {
    loadFbxMotion(name)
      .catch((fbxError) => {
        console.error(`Could not play FBX motion "${name}".`, fbxError);
        setStatus(`Failed to play ${name}`);
      });
    return;
  }

  setStatus(`Unknown motion: ${name}`);
}

async function applyAgentCommand(command = {}) {
  const type = command.type || command.action;
  switch (type) {
    case 'batch':
      for (const item of command.commands || []) {
        await applyAgentCommand(item);
      }
      return { ok: true };
    case 'setState':
      setCharacterState(command.payload || command.state || {});
      return { ok: true };
    case 'setExpression':
      setCharacterState({
        expression: command.expression || command.name || 'neutral',
        expressionIntensity: command.value ?? command.intensity ?? 1,
      });
      return { ok: true };
    case 'setPose':
      applyPosePreset(command.pose || command.name);
      return { ok: true };
    case 'playMotion':
      playMotion(command.motion || command.name);
      return { ok: true };
    case 'stopMotion':
      stopMotion();
      playIdleMotion();
      setStatus('Motion stopped');
      return { ok: true };
    case 'playIdleMotion':
      playIdleMotion();
      return { ok: true };
    case 'setMouth':
      setMouth(command.payload || command);
      return { ok: true };
    case 'setLipSyncLevel':
      setLipSyncLevel(command.level ?? command.value ?? 0);
      return { ok: true };
    case 'playAudioUrl':
      await playAudioUrl(command.url);
      return { ok: true };
    case 'startMicrophoneLipSync':
      await startMicrophoneLipSync();
      return { ok: true };
    case 'stopLipSync':
      disconnectLipSyncSource();
      controlsState.lipSync = false;
      setMouth({ aa: 0, oh: 0 });
      return { ok: true };
    case 'getState':
      return { ok: true, state: { ...controlsState } };
    default:
      throw new Error(`Unknown agent command: ${type}`);
  }
}

function bridgeEventsUrl() {
  const params = new URLSearchParams(window.location.search);
  const bridge = params.get('bridge');
  if (bridge === 'off' || bridge === 'false') return null;
  if (bridge) {
    if (bridge.endsWith('/events')) return bridge;
    return `${bridge.replace(/\/$/, '')}/events`;
  }
  return 'http://127.0.0.1:8893/events';
}

function connectAgentBridge() {
  const url = bridgeEventsUrl();
  if (!url || !window.EventSource) {
    setBridgeStatus('Agent bridge disabled');
    return;
  }

  bridgeEvents?.close();
  bridgeEvents = new EventSource(url);
  setBridgeStatus(`Agent bridge connecting: ${url}`);

  bridgeEvents.addEventListener('open', () => {
    setBridgeStatus(`Agent bridge connected: ${url}`);
  });

  bridgeEvents.addEventListener('message', (event) => {
    if (!event.data || event.data === '{}') return;
    let command;
    try {
      command = JSON.parse(event.data);
    } catch (error) {
      console.error('Invalid agent bridge message.', event.data, error);
      return;
    }

    applyAgentCommand(command)
      .then((result) => {
        window.dispatchEvent(new CustomEvent('tanyue:command', { detail: { command, result } }));
      })
      .catch((error) => {
        console.error('Agent command failed.', command, error);
        setStatus(`Agent command failed: ${command.type || command.action || 'unknown'}`);
      });
  });

  bridgeEvents.addEventListener('error', () => {
    setBridgeStatus(`Agent bridge disconnected: ${url}`);
  });
}

window.tanyueCharacter = {
  applyCommand: applyAgentCommand,
  connectLipSyncElement,
  connectAgentBridge,
  getCapabilities,
  getState: () => ({ ...controlsState }),
  playMotion,
  playAudioBlob,
  playAudioUrl,
  setLipSyncLevel,
  setMouth,
  setPose: applyPosePreset,
  setState: setCharacterState,
  startMicrophoneLipSync,
  stopMotion,
  stopLipSync: disconnectLipSyncSource,
};

function applyPose(time) {
  if (!currentVrm) return;
  if (currentMixer) return;

  const energy = controlsState.energy;
  const idle = controlsState.idle ? 1 : 0;
  const breath = Math.sin(time * 2.2) * 0.025 * idle * (0.4 + energy);
  const sway = Math.sin(time * 1.25) * 0.06 * idle * energy;

  const head = getBone('head');
  if (head) {
    head.rotation.y = rad(controlsState.headYaw) + sway * 0.35;
    head.rotation.x = rad(controlsState.headPitch) + breath * 0.45;
    head.rotation.z = -sway * 0.18;
  }

  const chest = getBone('chest') || getBone('spine');
  if (chest) {
    chest.rotation.y = rad(controlsState.bodyYaw) + sway * 0.22;
    chest.rotation.x = breath;
  }

  const leftUpperArm = getBone('leftUpperArm');
  const rightUpperArm = getBone('rightUpperArm');
  const leftLowerArm = getBone('leftLowerArm');
  const rightLowerArm = getBone('rightLowerArm');
  const wave = controlsState.pose === 'wave' ? Math.sin(time * 7.5) * 18 : 0;

  if (leftUpperArm) {
    leftUpperArm.rotation.x = 0;
    leftUpperArm.rotation.y = controlsState.pose === 'shy' ? rad(-8) : 0;
    leftUpperArm.rotation.z = rad(controlsState.leftArm) + Math.sin(time * 1.7) * 0.035 * idle * energy;
  }
  if (rightUpperArm) {
    rightUpperArm.rotation.x = controlsState.pose === 'wave' ? rad(-10) : 0;
    rightUpperArm.rotation.y = controlsState.pose === 'shy' ? rad(8) : 0;
    rightUpperArm.rotation.z = rad(controlsState.rightArm + wave) - Math.sin(time * 1.7) * 0.035 * idle * energy;
  }
  if (leftLowerArm) {
    leftLowerArm.rotation.y = rad(controlsState.leftElbow);
  }
  if (rightLowerArm) {
    rightLowerArm.rotation.y = rad(controlsState.rightElbow - wave * 0.5);
  }
}

function applyFace(time) {
  if (!currentVrm) return;

  clearExpressions();
  if (controlsState.expression !== 'neutral') {
    setExpression(controlsState.expression, clamp01(Number(controlsState.expressionIntensity) || 0));
  }

  if (controlsState.blink && time >= nextBlinkAt) {
    blinkUntil = time + 0.12;
    nextBlinkAt = time + 2.2 + Math.random() * 2.5;
  }
  const blinking = controlsState.blink && time < blinkUntil;
  setExpression('blink', blinking ? 1 : 0);
  setExpression('blinkLeft', blinking ? 1 : 0);
  setExpression('blinkRight', blinking ? 1 : 0);

  const lipSyncLevel = updateLipSync();
  const aa = Math.max(controlsState.mouthAa, lipSyncLevel);
  const oh = Math.max(controlsState.mouthOh, lipSyncLevel * 0.28);
  setExpression('aa', aa);
  setExpression('oh', oh);
}

async function loadVrm() {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const modelParam = pageParams.get('model');
  const modelUrls = [
    modelParam ? `./models/${encodeURIComponent(modelParam)}` : null,
    './models/LiuRuYan.vrm',
    './models/test_02.vrm',
    './models/test_01.vrm',
  ].filter(Boolean);

  for (const modelUrl of modelUrls) {
    try {
      setStatus(`Loading ${modelUrl.split('/').pop()}...`);
      const gltf = await loader.loadAsync(modelUrl);
      const vrm = gltf.userData.vrm;
      VRMUtils.removeUnnecessaryVertices(gltf.scene);
      if (VRMUtils.combineSkeletons) {
        VRMUtils.combineSkeletons(gltf.scene);
      }

      currentVrm = vrm;
      currentVrm.scene.rotation.y = 0;
      currentVrm.scene.traverse((obj) => {
        obj.frustumCulled = false;
      });
      scene.add(currentVrm.scene);
      frameVrm(currentVrm);
      setStatus('VRM ready');
      loadMotionManifest();
      return;
    } catch (error) {
      console.warn(`Could not load VRM model ${modelUrl}.`, error);
    }
  }

  setStatus('Failed to load VRM');
}

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  resize();
  const delta = clock.getDelta();
  const time = clock.elapsedTime;

  orbit.update();
  applyPose(time);
  applyFace(time);
  if (currentMixer) currentMixer.timeScale = controlsState.motionSpeed;
  currentMixer?.update(delta);
  currentVrm?.update(delta);
  renderer.render(scene, camera);
}

bindControls();
loadVrm();
connectAgentBridge();
animate();
