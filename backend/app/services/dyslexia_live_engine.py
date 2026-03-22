"""
dyslexia_live_engine.py
=======================
Live webcam gaze capture engine using MediaPipe Tasks API (FaceLandmarker).
Outputs gaze data in the same (N,4) [LX,LY,RX,RY] format as A1R.txt so it
feeds directly into DyslexiaEyeEngineV2 without any changes.

Pipeline
--------
Webcam frame
  → FaceLandmarker (478 landmarks + transformation matrix)
  → iris center pixels (landmarks 468-477, left/right separately)
  → head pose correction (subtract rotation from facial_transformation_matrixes)
  → px → degrees of visual angle (geometric, screen size + distance)
  → blink masking (eye aspect ratio from eyelid landmarks)
  → upsample buffer to 50Hz
  → (N, 4) float32 [LX, LY, RX, RY]  ← same as A1R.txt

Requires
--------
pip install mediapipe opencv-python numpy scipy
Download:  face_landmarker.task  (see README or dyslexia_live_engine.py --download)

Usage
-----
from dyslexia_live_engine import LiveGazeCapture, GazeCalibration

cap = LiveGazeCapture(model_path="face_landmarker.task")
cal = GazeCalibration(cap)

# 5-point calibration
cal.run()  # shows calibration window, blocks until done

# Record 30 seconds of reading
arr = cap.record(duration_sec=30)  # returns (N,4) numpy array at 50Hz

# Feed directly into prediction engine
from dyslexia_eye_engine_v2 import DyslexiaEyeEngineV2
engine = DyslexiaEyeEngineV2(...)
result = engine.predict(arr)
print(result)
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

try:
    import mediapipe as mp
    _BaseOptions        = mp.tasks.BaseOptions
    _FaceLandmarker     = mp.tasks.vision.FaceLandmarker
    _FaceLandmarkerOpts = mp.tasks.vision.FaceLandmarkerOptions
    _FaceLandmarkerRes  = mp.tasks.vision.FaceLandmarkerResult
    _VisionRunningMode  = mp.tasks.vision.RunningMode
    _MP_OK = True
except ImportError:
    _MP_OK = False


# ──────────────────────────────────────────────────────────────────────────────
# Landmark indices (MediaPipe 478-point model)
# ──────────────────────────────────────────────────────────────────────────────

# Iris centres (added by the refined model — indices 468–477)
# MediaPipe landmark 468 = person's RIGHT eye, 473 = person's LEFT eye
# (in a front-facing camera the anatomical right eye is on the left of frame)
# After X-flip to correct mirror: 468 maps to screen-right, 473 to screen-left
# We label by screen position: L=screen-left=landmark 473, R=screen-right=landmark 468
L_IRIS_CENTER = 473   # left iris centre  (person's anatomical left eye)
R_IRIS_CENTER = 468   # right iris centre (person's anatomical right eye)

# Eyelid landmarks for blink detection (Eye Aspect Ratio)
# Left eye: upper lid, lower lid, corners
L_EYE_UPPER = [386, 374, 373, 390]
L_EYE_LOWER = [374, 380, 381, 382]
L_EYE_LEFT  = 263
L_EYE_RIGHT = 362

# Right eye
R_EYE_UPPER = [159, 145, 144, 163]
R_EYE_LOWER = [145, 153, 154, 155]
R_EYE_LEFT  = 33
R_EYE_RIGHT = 133

EAR_BLINK_THRESHOLD = 0.20   # below this → blink


# ──────────────────────────────────────────────────────────────────────────────
# Screen configuration — set these for your monitor
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ScreenConfig:
    """
    Physical screen parameters needed for px→degrees conversion.
    Measure your monitor and set these values for best accuracy.
    """
    width_px:   int   = 1920    # screen resolution width
    height_px:  int   = 1080    # screen resolution height
    width_mm:   float = 527.0   # physical screen width in mm  (23" = 527mm)
    height_mm:  float = 296.0   # physical screen height in mm (23" = 296mm)
    dist_mm:    float = 600.0   # default viewing distance in mm (~60cm)

    @property
    def px_per_mm_x(self) -> float:
        return self.width_px / self.width_mm

    @property
    def px_per_mm_y(self) -> float:
        return self.height_px / self.height_mm

    def px_to_degrees(self, delta_px_x: float, delta_px_y: float,
                      dist_mm: Optional[float] = None) -> Tuple[float, float]:
        """Convert pixel displacement from screen centre to degrees of visual angle."""
        d = dist_mm or self.dist_mm
        dx_mm = delta_px_x / self.px_per_mm_x
        dy_mm = delta_px_y / self.px_per_mm_y
        deg_x = math.degrees(math.atan2(dx_mm, d))
        deg_y = math.degrees(math.atan2(dy_mm, d))
        return deg_x, deg_y


# ──────────────────────────────────────────────────────────────────────────────
# Raw gaze sample (one frame)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class GazeSample:
    timestamp_ms:  int
    lx_px: float;  ly_px: float   # left iris pixel (raw)
    rx_px: float;  ry_px: float   # right iris pixel (raw)
    lx_deg: float; ly_deg: float  # left gaze in degrees
    rx_deg: float; ry_deg: float  # right gaze in degrees
    l_blink: bool = False
    r_blink: bool = False
    head_yaw:   float = 0.0
    head_pitch: float = 0.0
    head_roll:  float = 0.0
    face_dist_mm: float = 600.0   # estimated from face size


# ──────────────────────────────────────────────────────────────────────────────
# Calibration data
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class CalibrationData:
    """
    Calibration result using displacement-based gaze mapping.

    Rather than an affine iris→screen transform (which breaks when iris range
    is small relative to screen size), we store:
      - iris_centre_l/r : resting iris pixel position (straight-ahead gaze)
      - iris_px_per_deg : how many iris pixels = 1 degree of visual angle
      - left_matrix/right_matrix : kept for legacy compatibility but not used
        in apply() when displacement calibration is available
    """
    left_matrix:    Optional[np.ndarray] = None   # legacy, not used in apply()
    right_matrix:   Optional[np.ndarray] = None   # legacy, not used in apply()
    screen:         ScreenConfig = field(default_factory=ScreenConfig)
    is_valid:       bool = False
    # Displacement-based calibration fields
    iris_centre_l:  Optional[Tuple[float,float]] = None  # (x,y) resting left iris px
    iris_centre_r:  Optional[Tuple[float,float]] = None  # (x,y) resting right iris px
    iris_px_per_deg: Tuple[float,float] = (1.0, 1.0)    # (x_ppd, y_ppd)

    def apply(self, lx_px, ly_px, rx_px, ry_px,
               dist_mm: float = 600.0) -> Tuple[float, float, float, float]:
        """
        Map raw iris pixels → degrees of visual angle.

        Uses displacement-based mapping when calibration is valid:
          1. Subtract the resting iris centre (measured during calibration)
          2. Scale displacement by px_per_degree (derived from iris range + screen geometry)
          3. This gives degrees relative to straight-ahead gaze

        This approach is robust when iris pixel range is small (webcam limitation)
        because it never extrapolates -- it only measures relative movement.
        Absolute gaze position is sacrificed but relative movement (saccades,
        regressions, reading rhythm) is preserved -- which is all the model needs.
        """
        if not self.is_valid or self.iris_centre_l is None:
            # Geometric fallback -- no calibration data at all
            cx = self.screen.width_px / 2
            cy = self.screen.height_px / 2
            lx_d, ly_d = self.screen.px_to_degrees(lx_px - cx, ly_px - cy, dist_mm)
            rx_d, ry_d = self.screen.px_to_degrees(rx_px - cx, ry_px - cy, dist_mm)
            return lx_d, ly_d, rx_d, ry_d

        # Displacement from resting centre (in iris pixels)
        dlx = lx_px - self.iris_centre_l[0]
        dly = ly_px - self.iris_centre_l[1]
        drx = rx_px - self.iris_centre_r[0]
        dry = ry_px - self.iris_centre_r[1]

        # Scale: iris_px_per_deg was measured during range detection
        # degrees = displacement_px / px_per_degree
        ppd = self.iris_px_per_deg  # (x_ppd, y_ppd)
        lx_d = dlx / ppd[0] if ppd[0] > 0 else 0.0
        ly_d = dly / ppd[1] if ppd[1] > 0 else 0.0
        rx_d = drx / ppd[0] if ppd[0] > 0 else 0.0
        ry_d = dry / ppd[1] if ppd[1] > 0 else 0.0

        return lx_d, ly_d, rx_d, ry_d


# ──────────────────────────────────────────────────────────────────────────────
# Helper: EAR blink detection
# ──────────────────────────────────────────────────────────────────────────────
def _ear(landmarks, upper_ids, lower_ids, left_id, right_id, w, h) -> float:
    def pt(i):
        l = landmarks[i]
        return np.array([l.x * w, l.y * h])
    A = np.linalg.norm(pt(upper_ids[1]) - pt(lower_ids[1]))
    B = np.linalg.norm(pt(upper_ids[2]) - pt(lower_ids[2]))
    C = np.linalg.norm(pt(left_id)     - pt(right_id))
    return (A + B) / (2.0 * C + 1e-6)


# ──────────────────────────────────────────────────────────────────────────────
# Helper: head pose from facial transformation matrix
# ──────────────────────────────────────────────────────────────────────────────
def _head_pose_from_matrix(mat: np.ndarray) -> Tuple[float, float, float]:
    """
    Extract yaw, pitch, roll in degrees from the 4x4 facial transformation matrix
    returned by FaceLandmarker (output_facial_transformation_matrixes=True).
    """
    r = mat[:3, :3]
    # Pitch (x-rotation)
    pitch = math.degrees(math.atan2(-r[2, 1], r[2, 2]))
    # Yaw (y-rotation)
    yaw   = math.degrees(math.atan2(r[2, 0],
                math.sqrt(r[2, 1]**2 + r[2, 2]**2)))
    # Roll (z-rotation)
    roll  = math.degrees(math.atan2(-r[1, 0], r[0, 0]))
    return yaw, pitch, roll


# ──────────────────────────────────────────────────────────────────────────────
# Helper: estimate face distance from inter-pupil distance
# ──────────────────────────────────────────────────────────────────────────────
_AVG_IPD_MM = 63.0   # average inter-pupil distance in mm

def _estimate_face_dist(lx_px, ly_px, rx_px, ry_px,
                        screen: ScreenConfig) -> float:
    ipd_px = math.sqrt((rx_px - lx_px)**2 + (ry_px - ly_px)**2)
    if ipd_px < 1:
        return screen.dist_mm
    ipd_mm_per_px = _AVG_IPD_MM / ipd_px
    # focal_length_px ≈ px_per_mm * dist_mm (pinhole model approximation)
    # dist_mm ≈ ipd_mm * focal_length_px / ipd_px
    # We use a simpler: dist = IPD_mm * screen_width_px / (ipd_px * 2)
    dist = (_AVG_IPD_MM * screen.width_px) / (ipd_px * 2.0)
    return max(200.0, min(dist, 1500.0))   # clamp 20cm–150cm




# ──────────────────────────────────────────────────────────────────────────────
# Kalman filter for iris pixel smoothing
# ──────────────────────────────────────────────────────────────────────────────
class IrisKalman:
    """
    Two independent 2-state Kalman filters (one per eye) that smooth
    raw iris pixel coordinates before they enter calibration / degree conversion.

    State vector per eye: [x, y, vx, vy]  (position + velocity)
    Measurement:          [x, y]           (raw iris pixel)

    Tuning
    ------
    process_noise  : how much the iris is allowed to accelerate between frames
                     higher → filter trusts measurements more (less smooth)
    measure_noise  : estimated pixel measurement noise from MediaPipe
                     higher → filter trusts the model more (smoother but laggy)
    """

    def __init__(self, process_noise: float = 1e-2, measure_noise: float = 2.0):
        self._kf_l = self._make_kf(process_noise, measure_noise)
        self._kf_r = self._make_kf(process_noise, measure_noise)
        self._init_l = False
        self._init_r = False

    @staticmethod
    def _make_kf(q: float, r: float) -> cv2.KalmanFilter:
        kf = cv2.KalmanFilter(4, 2)   # 4 states, 2 measurements
        dt = 1.0 / 30.0               # assume ~30fps webcam

        # Transition matrix: x' = x + vx*dt
        kf.transitionMatrix = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1,  0],
            [0, 0, 0,  1],
        ], dtype=np.float32)

        # Measurement matrix: we observe [x, y] only
        kf.measurementMatrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float32)

        kf.processNoiseCov      = np.eye(4, dtype=np.float32) * q
        kf.measurementNoiseCov  = np.eye(2, dtype=np.float32) * r
        kf.errorCovPost         = np.eye(4, dtype=np.float32)
        return kf

    def _update(self, kf: cv2.KalmanFilter, x: float, y: float,
                initialised: bool) -> Tuple[float, float, bool]:
        meas = np.array([[x], [y]], dtype=np.float32)
        if not initialised:
            kf.statePost = np.array([[x], [y], [0], [0]], dtype=np.float32)
            initialised  = True
        kf.predict()
        est = kf.correct(meas)
        return float(est[0, 0]), float(est[1, 0]), initialised

    def smooth_left(self, lx: float, ly: float) -> Tuple[float, float]:
        lx_s, ly_s, self._init_l = self._update(self._kf_l, lx, ly, self._init_l)
        return lx_s, ly_s

    def smooth_right(self, rx: float, ry: float) -> Tuple[float, float]:
        rx_s, ry_s, self._init_r = self._update(self._kf_r, rx, ry, self._init_r)
        return rx_s, ry_s

    def reset(self):
        """Call when restarting capture or after a long blink gap."""
        self._init_l = False
        self._init_r = False

# ──────────────────────────────────────────────────────────────────────────────
# Main capture engine
# ──────────────────────────────────────────────────────────────────────────────
class LiveGazeCapture:
    """
    Captures live gaze data from webcam using MediaPipe FaceLandmarker.

    Parameters
    ----------
    model_path    : path to face_landmarker.task
    camera_index  : webcam index (default 0)
    screen        : ScreenConfig with your monitor's physical dimensions
    calibration   : CalibrationData from a prior calibration run (optional)
    head_correct  : subtract head rotation from gaze (recommended True)
    """

    def __init__(
        self,
        model_path:   str = "face_landmarker.task",
        camera_index: int = 0,
        screen:       Optional[ScreenConfig]    = None,
        calibration:  Optional[CalibrationData] = None,
        head_correct: bool = True,
    ):
        if not _MP_OK:
            raise ImportError("pip install mediapipe")

        self.screen      = screen or ScreenConfig()
        self.calibration = calibration or CalibrationData(screen=self.screen)
        self.head_correct = head_correct
        self.camera_index = camera_index

        self._model_path = str(model_path)
        if not Path(self._model_path).exists():
            raise FileNotFoundError(
                f"Model file not found: {self._model_path}\n"
                f"Download with:\n"
                f"  curl -L https://storage.googleapis.com/mediapipe-models/"
                f"face_landmarker/face_landmarker/float16/1/face_landmarker.task"
                f" -o face_landmarker.task"
            )

        # ring buffer for live samples
        self._buffer:  deque[GazeSample] = deque(maxlen=10000)
        self._lock     = threading.Lock()
        self._running  = False
        self._cap      = None
        self._landmarker = None

        # latest frame for UI overlay
        self._latest_frame:     Optional[np.ndarray] = None
        self._latest_sample:    Optional[GazeSample] = None
        self._frame_callbacks:  List[Callable] = []

        # head rotation smoothing (exponential moving average)
        self._head_yaw_smooth   = 0.0
        self._head_pitch_smooth = 0.0
        self._alpha             = 0.05  # EMA factor -- slow response prevents false regressions

        # Kalman filter for iris pixel smoothing (pure OpenCV)
        self._kalman = IrisKalman(process_noise=0.1, measure_noise=0.5)
        self.kalman_active = False   # disabled during calibration/range detection, enabled during recording

        self._init_landmarker()
        print(
            f"[LiveGazeCapture] Ready\n"
            f"  Model      : {model_path}\n"
            f"  Camera     : {camera_index}\n"
            f"  Screen     : {self.screen.width_px}x{self.screen.height_px} "
            f"({self.screen.width_mm:.0f}x{self.screen.height_mm:.0f}mm)\n"
            f"  Head corr  : {head_correct}\n"
            f"  Mirror fix : True (X-axis flipped)"
        )

    def _init_landmarker(self):
        """Initialise FaceLandmarker in LIVE_STREAM mode."""
        options = _FaceLandmarkerOpts(
            base_options=_BaseOptions(model_asset_path=self._model_path),
            running_mode=_VisionRunningMode.LIVE_STREAM,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,           # not needed
            output_facial_transformation_matrixes=True,  # needed for head pose
            result_callback=self._on_result,
        )
        self._landmarker = _FaceLandmarker.create_from_options(options)

    def _on_result(
        self,
        result: "_FaceLandmarkerRes",
        output_image: "mp.Image",
        timestamp_ms: int,
    ):
        """Callback fired by MediaPipe on each processed frame."""
        if not result.face_landmarks:
            return

        lms  = result.face_landmarks[0]   # first face
        h, w = output_image.height, output_image.width

        # ── Iris pixel coordinates ────────────────────────────────────────────
        # Flip X: MediaPipe reports mirrored camera coords (left/right inverted)
        # w - x converts from mirrored camera frame to screen-correct frame
        lx_raw = w - lms[L_IRIS_CENTER].x * w
        ly_raw = lms[L_IRIS_CENTER].y * h
        rx_raw = w - lms[R_IRIS_CENTER].x * w
        ry_raw = lms[R_IRIS_CENTER].y * h

        # ── Blink detection (EAR) — use raw pixels before Kalman ──────────────
        l_blink = _ear(lms, L_EYE_UPPER, L_EYE_LOWER, L_EYE_LEFT, L_EYE_RIGHT,
                       w, h) < EAR_BLINK_THRESHOLD
        r_blink = _ear(lms, R_EYE_UPPER, R_EYE_LOWER, R_EYE_LEFT, R_EYE_RIGHT,
                       w, h) < EAR_BLINK_THRESHOLD

        # ── Kalman smoothing (only during recording, not calibration/range detect) ──
        if self.kalman_active:
            if not l_blink:
                lx_px, ly_px = self._kalman.smooth_left(lx_raw, ly_raw)
            else:
                lx_px, ly_px = lx_raw, ly_raw
                self._kalman.reset()
            if not r_blink:
                rx_px, ry_px = self._kalman.smooth_right(rx_raw, ry_raw)
            else:
                rx_px, ry_px = rx_raw, ry_raw
        else:
            lx_px, ly_px = lx_raw, ly_raw
            rx_px, ry_px = rx_raw, ry_raw

        # ── Head pose ─────────────────────────────────────────────────────────
        yaw = pitch = roll = 0.0
        if result.facial_transformation_matrixes:
            mat = np.array(result.facial_transformation_matrixes[0]).reshape(4, 4)
            yaw, pitch, roll = _head_pose_from_matrix(mat)
            # EMA smoothing
            self._head_yaw_smooth   = (self._alpha * yaw
                                       + (1 - self._alpha) * self._head_yaw_smooth)
            self._head_pitch_smooth = (self._alpha * pitch
                                       + (1 - self._alpha) * self._head_pitch_smooth)

        # ── Face distance estimate ────────────────────────────────────────────
        dist_mm = _estimate_face_dist(lx_px, ly_px, rx_px, ry_px, self.screen)

        # ── px → degrees via calibration ──────────────────────────────────────
        lx_d, ly_d, rx_d, ry_d = self.calibration.apply(
            lx_px, ly_px, rx_px, ry_px, dist_mm
        )

        # ── Head pose correction ──────────────────────────────────────────────
        # Only correct for head movements > 1.5° to avoid false regressions
        # from small reading-posture adjustments
        if self.head_correct:
            DEADZONE = 1.5   # degrees
            yaw_corr   = self._head_yaw_smooth   if abs(self._head_yaw_smooth)   > DEADZONE else 0.0
            pitch_corr = self._head_pitch_smooth if abs(self._head_pitch_smooth) > DEADZONE else 0.0
            lx_d -= yaw_corr;   ly_d -= pitch_corr
            rx_d -= yaw_corr;   ry_d -= pitch_corr

        # ── Clamp to Tobii-like range [-40°, 40°] ─────────────────────────────
        for v in [lx_d, ly_d, rx_d, ry_d]:
            v = max(-39.0, min(39.0, v))

        # ── Build sample ──────────────────────────────────────────────────────
        sample = GazeSample(
            timestamp_ms  = timestamp_ms,
            lx_px=lx_px, ly_px=ly_px,
            rx_px=rx_px, ry_px=ry_px,
            lx_deg=lx_d, ly_deg=ly_d,
            rx_deg=rx_d, ry_deg=ry_d,
            l_blink=l_blink,
            r_blink=r_blink,
            head_yaw=yaw,
            head_pitch=pitch,
            head_roll=roll,
            face_dist_mm=dist_mm,
        )

        with self._lock:
            self._buffer.append(sample)
            self._latest_sample = sample

        # fire UI callbacks
        for cb in self._frame_callbacks:
            try:
                cb(sample, output_image)
            except Exception:
                pass

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        """Start the webcam capture thread."""
        if self._running:
            return
        self._running = True
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            self._running = False
            raise RuntimeError(f"Cannot open camera {self.camera_index}")
        threading.Thread(target=self._capture_loop, daemon=True).start()
        print(f"[LiveGazeCapture] Capture started (camera {self.camera_index})")

    def stop(self):
        """Stop the webcam capture thread."""
        self._running = False
        time.sleep(0.2)
        if self._cap:
            self._cap.release()
        print("[LiveGazeCapture] Capture stopped")

    def clear_buffer(self):
        """Clear the gaze sample buffer."""
        with self._lock:
            self._buffer.clear()

    def enable_kalman(self):
        """Enable Kalman smoothing -- call just before recording starts."""
        self._kalman.reset()
        self.kalman_active = True

    def disable_kalman(self):
        """Disable Kalman smoothing -- call during calibration/range detection."""
        self.kalman_active = False
        self._kalman.reset()

    def add_frame_callback(self, cb: Callable):
        """
        Register a callback fired on every processed frame.
        Signature: cb(sample: GazeSample, image: mp.Image)
        Used by the UI for live overlay rendering.
        """
        self._frame_callbacks.append(cb)

    def get_latest_sample(self) -> Optional[GazeSample]:
        """Return the most recent GazeSample (thread-safe)."""
        with self._lock:
            return self._latest_sample

    def get_buffer_as_array(self) -> np.ndarray:
        """
        Return current buffer contents as (N,4) float32 array [LX,LY,RX,RY]
        in degrees, resampled to 50Hz, with blinks set to NaN.
        Ready to feed into DyslexiaEyeEngineV2.predict().
        """
        with self._lock:
            samples = list(self._buffer)
        return _samples_to_array(samples, target_hz=50)

    def record(
        self,
        duration_sec: float = 30.0,
        on_progress:  Optional[Callable[[float], None]] = None,
    ) -> np.ndarray:
        """
        Record gaze for a fixed duration and return the (N,4) array.

        Parameters
        ----------
        duration_sec : recording duration in seconds
        on_progress  : optional callback(elapsed_sec) called every 0.5s

        Returns
        -------
        numpy array (N,4) [LX,LY,RX,RY] at 50Hz — feed directly into engine.predict()
        """
        if not self._running:
            self.start()

        self.clear_buffer()
        start = time.time()
        while True:
            elapsed = time.time() - start
            if on_progress:
                on_progress(elapsed)
            if elapsed >= duration_sec:
                break
            time.sleep(0.5)

        arr = self.get_buffer_as_array()
        print(f"[LiveGazeCapture] Recorded {len(arr)} samples "
              f"({len(arr)/50:.1f}s at 50Hz)")
        return arr

    def snapshot_buffer(self) -> List[GazeSample]:
        """Return a copy of the current buffer as a list of GazeSamples."""
        with self._lock:
            return list(self._buffer)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _capture_loop(self):
        """Webcam read loop — runs in background thread."""
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # store latest frame for UI
            self._latest_frame = frame.copy()

            # send to MediaPipe
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms  = int(time.time() * 1000)

            try:
                self._landmarker.detect_async(mp_img, ts_ms)
            except Exception as e:
                pass   # timestamp ordering error — skip frame

            time.sleep(0.01)   # ~100fps max read rate; MediaPipe throttles itself


# ──────────────────────────────────────────────────────────────────────────────
# Buffer → (N,4) array at 50Hz
# ──────────────────────────────────────────────────────────────────────────────

def _samples_to_array(
    samples: List[GazeSample],
    target_hz: int = 50,
) -> np.ndarray:
    """
    Convert a list of GazeSamples to a (N,4) float32 array [LX,LY,RX,RY]
    resampled to target_hz using linear interpolation.
    Blinks are marked as NaN (same as Tobii invalid sentinel).
    """
    if len(samples) < 2:
        return np.full((1, 4), np.nan, dtype=np.float32)

    # raw timestamps and values
    ts  = np.array([s.timestamp_ms for s in samples], dtype=float)
    lx  = np.array([s.lx_deg for s in samples], dtype=float)
    ly  = np.array([s.ly_deg for s in samples], dtype=float)
    rx  = np.array([s.rx_deg for s in samples], dtype=float)
    ry  = np.array([s.ry_deg for s in samples], dtype=float)
    lb  = np.array([s.l_blink for s in samples], dtype=bool)
    rb  = np.array([s.r_blink for s in samples], dtype=bool)

    # mark blinks as NaN before resampling
    lx[lb] = np.nan; ly[lb] = np.nan
    rx[rb] = np.nan; ry[rb] = np.nan

    # target timestamps at exactly target_hz
    t_start  = ts[0]
    t_end    = ts[-1]
    dt_ms    = 1000.0 / target_hz
    t_target = np.arange(t_start, t_end, dt_ms)

    if len(t_target) < 2:
        return np.full((1, 4), np.nan, dtype=np.float32)

    def interp_col(col):
        """
        Nearest-neighbour resampling — preserves sharp velocity spikes at saccade
        boundaries instead of smearing them across interpolated samples.
        Linear interpolation kills I-VT velocity detection by spreading 1-frame
        jumps across multiple 50Hz samples, dropping peak velocity below threshold.
        """
        valid = ~np.isnan(col)
        if valid.sum() < 2:
            return np.full(len(t_target), np.nan)
        ts_v  = ts[valid]
        col_v = col[valid]
        # nearest-neighbour: find closest real sample for each target timestamp
        idx   = np.searchsorted(ts_v, t_target, side="left")
        idx   = np.clip(idx, 0, len(ts_v) - 1)
        # pick nearest (left or right)
        idx_l = np.clip(idx - 1, 0, len(ts_v) - 1)
        closer = np.abs(t_target - ts_v[idx_l]) < np.abs(t_target - ts_v[idx])
        idx[closer] = idx_l[closer]
        out = col_v[idx].astype(float)
        # mark NaN outside the recorded range
        out[t_target < ts_v[0]]  = np.nan
        out[t_target > ts_v[-1]] = np.nan
        return out

    out = np.column_stack([
        interp_col(lx),
        interp_col(ly),
        interp_col(rx),
        interp_col(ry),
    ]).astype(np.float32)

    return out


# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
# Iris Range Detection + Adaptive Calibration
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IrisRange:
    """Measured iris pixel range from the range detection phase."""
    lx_min: float; lx_max: float
    ly_min: float; ly_max: float
    rx_min: float; rx_max: float
    ry_min: float; ry_max: float
    lx_center: float; ly_center: float
    rx_center: float; ry_center: float

    @property
    def lx_span(self): return self.lx_max - self.lx_min
    @property
    def ly_span(self): return self.ly_max - self.ly_min
    @property
    def rx_span(self): return self.rx_max - self.rx_min
    @property
    def ry_span(self): return self.ry_max - self.ry_min

    def is_usable(self, min_span_px: float = 4.0) -> bool:
        """Return True if the measured range is large enough to be meaningful."""
        return (self.lx_span >= min_span_px and self.ly_span >= min_span_px and
                self.rx_span >= min_span_px and self.ry_span >= min_span_px)

    def __str__(self):
        return (
            f"  Left  iris: X span={self.lx_span:.1f}px  Y span={self.ly_span:.1f}px  "
            f"center=({self.lx_center:.1f},{self.ly_center:.1f})\n"
            f"  Right iris: X span={self.rx_span:.1f}px  Y span={self.ry_span:.1f}px  "
            f"center=({self.rx_center:.1f},{self.ry_center:.1f})"
        )


def _run_range_detection(
    capture: "LiveGazeCapture",
    duration_sec: float = 5.0,
) -> IrisRange:
    """
    Phase 1 of calibration: guide the user through 4 extreme gaze positions
    (left, right, up, down) while recording iris pixel extremes.

    Shows a fullscreen OpenCV window with animated arrows.
    Records the min/max iris pixel coordinates seen during each direction.
    Returns an IrisRange with the measured extents and centre.
    """
    screen = capture.screen
    w, h   = screen.width_px, screen.height_px
    WIN    = "Eye Range Detection -- Follow the arrow with your eyes (not your head)"

    # directions: (label, arrow_pts, collect_sec)
    DIRS = [
        ("Look LEFT  (eyes only, keep head still)",  "LEFT",   1.2),
        ("Look RIGHT (eyes only, keep head still)",  "RIGHT",  1.2),
        ("Look UP    (eyes only, keep head still)",  "UP",     1.2),
        ("Look DOWN  (eyes only, keep head still)",  "DOWN",   1.2),
        ("Look at CENTRE",                           "CENTRE", 1.0),
    ]

    all_lx, all_ly = [], []
    all_rx, all_ry = [], []

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # Intro screen
    intro = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.putText(intro, "Eye Range Detection", (w//2 - 300, h//2 - 80),
                cv2.FONT_HERSHEY_DUPLEX, 2.0, (200, 210, 230), 2, cv2.LINE_AA)
    cv2.putText(intro, "Follow each arrow with your EYES ONLY -- keep your head still",
                (w//2 - 480, h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                (130, 150, 180), 1, cv2.LINE_AA)
    cv2.putText(intro, "Starting in 2 seconds...",
                (w//2 - 200, h//2 + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (80, 110, 150), 1, cv2.LINE_AA)
    cv2.imshow(WIN, intro)
    cv2.waitKey(2000)

    for label, direction, collect_sec in DIRS:
        t0 = time.time()
        capture.clear_buffer()

        while time.time() - t0 < collect_sec:
            elapsed  = time.time() - t0
            fraction = elapsed / collect_sec

            canvas = np.zeros((h, w, 3), dtype=np.uint8)

            # instruction text
            cv2.putText(canvas, label,
                        (w//2 - len(label)*14//2, h//2 - 120),
                        cv2.FONT_HERSHEY_DUPLEX, 1.1,
                        (210, 215, 230), 2, cv2.LINE_AA)

            # large directional arrow
            cx, cy = w//2, h//2
            asz    = 180   # arrow size px
            color  = (80, 200, 255)

            if direction == "LEFT":
                pts = np.array([[cx-asz, cy], [cx-asz//2, cy-60],
                                [cx-asz//2, cy-20], [cx+asz//2, cy-20],
                                [cx+asz//2, cy+20], [cx-asz//2, cy+20],
                                [cx-asz//2, cy+60]], np.int32)
            elif direction == "RIGHT":
                pts = np.array([[cx+asz, cy], [cx+asz//2, cy-60],
                                [cx+asz//2, cy-20], [cx-asz//2, cy-20],
                                [cx-asz//2, cy+20], [cx+asz//2, cy+20],
                                [cx+asz//2, cy+60]], np.int32)
            elif direction == "UP":
                pts = np.array([[cx, cy-asz], [cx-60, cy-asz//2],
                                [cx-20, cy-asz//2], [cx-20, cy+asz//2],
                                [cx+20, cy+asz//2], [cx+20, cy-asz//2],
                                [cx+60, cy-asz//2]], np.int32)
            elif direction == "DOWN":
                pts = np.array([[cx, cy+asz], [cx-60, cy+asz//2],
                                [cx-20, cy+asz//2], [cx-20, cy-asz//2],
                                [cx+20, cy-asz//2], [cx+20, cy+asz//2],
                                [cx+60, cy+asz//2]], np.int32)
            else:  # CENTRE
                color = (80, 255, 160)
                cv2.circle(canvas, (cx, cy), 40, color, -1)
                cv2.circle(canvas, (cx, cy), 12, (255,255,255), -1)
                pts = None

            if pts is not None:
                cv2.fillPoly(canvas, [pts], color)

            # progress bar
            bx0 = int(w*0.2); bx1 = int(w*0.8)
            by  = h - 40
            cv2.rectangle(canvas, (bx0, by), (bx1, by+8), (25,35,50), -1)
            bf  = int(bx0 + (bx1-bx0) * fraction)
            if bf > bx0:
                cv2.rectangle(canvas, (bx0, by), (bf, by+8), (80,200,255), -1)

            cv2.imshow(WIN, canvas)
            cv2.waitKey(33)

        # collect non-blink samples from this direction
        samples = capture.snapshot_buffer()
        valid   = [s for s in samples if not s.l_blink and not s.r_blink]
        if valid:
            all_lx += [s.lx_px for s in valid]
            all_ly += [s.ly_px for s in valid]
            all_rx += [s.rx_px for s in valid]
            all_ry += [s.ry_px for s in valid]

    cv2.destroyWindow(WIN)

    if not all_lx:
        # no samples at all -- return dummy range
        return IrisRange(0,1,0,1,0,1,0,1,0.5,0.5,0.5,0.5)

    # trim 5% outliers to remove noise spikes
    def robust(arr):
        a = np.array(arr)
        lo, hi = np.percentile(a, 5), np.percentile(a, 95)
        return float(lo), float(hi)

    lx_lo, lx_hi = robust(all_lx)
    ly_lo, ly_hi = robust(all_ly)
    rx_lo, rx_hi = robust(all_rx)
    ry_lo, ry_hi = robust(all_ry)

    ir = IrisRange(
        lx_min=lx_lo, lx_max=lx_hi,
        ly_min=ly_lo, ly_max=ly_hi,
        rx_min=rx_lo, rx_max=rx_hi,
        ry_min=ry_lo, ry_max=ry_hi,
        lx_center=float(np.median(all_lx)),
        ly_center=float(np.median(all_ly)),
        rx_center=float(np.median(all_rx)),
        ry_center=float(np.median(all_ry)),
    )
    print(f"[RangeDetect] Measured iris range:\n{ir}")
    return ir


# ──────────────────────────────────────────────────────────────────────────────
# Displacement-based Calibration
# ──────────────────────────────────────────────────────────────────────────────
# Core insight: webcam iris range (~10-26px) is too small to fit a reliable
# affine transform to 1920px screen. Instead we:
#   1. Measure resting iris centre (straightforward gaze)
#   2. Measure px-per-degree from range detection (iris span / visual angle span)
#   3. Convert: degrees = (iris_px - centre_px) / px_per_deg
#
# This only gives relative gaze angles, not absolute screen position.
# But the dyslexia model only needs relative movement -- saccade amplitudes,
# reading rhythm, regression rate -- so this is sufficient.
# ──────────────────────────────────────────────────────────────────────────────

def _compute_displacement_cal(capture, ir: "IrisRange") -> CalibrationData:
    """
    Build a CalibrationData from measured IrisRange using displacement mapping.

    px_per_degree is derived geometrically:
      - The screen subtends screen_deg_x degrees of visual angle at dist_mm
      - The iris spans ir.lx_span pixels when moving across the full gaze range
      - But we don't know what visual angle the iris span covers from webcam alone
      - So we use the screen geometry as a proxy: assume the range-detection
        extreme movements cover ~30 degrees (typical comfortable gaze range)
      - px_per_deg = iris_span_px / assumed_visual_angle_deg

    The assumed_visual_angle can be tuned, but 30° horizontal / 20° vertical
    is well-supported in the eye tracking literature for comfortable gaze range.
    """
    screen = capture.screen

    # Resting centre = median of all samples from range detection
    # (already stored in IrisRange)
    centre_l = (ir.lx_center, ir.ly_center)
    centre_r = (ir.rx_center, ir.ry_center)

    # Calibrate assumed range to produce Tobii-compatible velocity statistics.
    # The key constraint: after px→deg conversion, word-to-word saccades
    # (~2px iris movement) must exceed the 30°/s I-VT threshold.
    # At 50Hz: need delta_deg > 30 * 0.02 = 0.6° per sample
    # A 2px iris move must → >0.6° → ppd must be < 2/0.6 = 3.33 px/deg
    # With typical span=20px and ASSUMED_H_DEG=6: ppd = 20/6 = 3.33 ✓
    # This maps the full iris range to ±3° which is tight but correct
    # for a webcam where 1px ≈ 0.3° (matches Tobii resolution roughly)
    # ASSUMED range must be large enough that resampled velocity spikes fire the
    # 30°/s I-VT threshold. At 30fps webcam resampled to 50Hz, a 2px iris jump
    # spreads across ~1.67 samples → ~1.2px/sample. Need 1.2/ppd / 0.02 > 30
    # → ppd < 2.0 → ASSUMED_H_DEG > span/2.0. With typical span=17px: need >8.5
    # X=10 gives ppd=1.7, vel=35°/s ✓ and ±5° effective range (realistic reading)
    # With nearest-neighbour resampling, velocity spikes are preserved at full
    # amplitude. Use physiologically correct 30° range (±15° comfortable gaze).
    ASSUMED_H_DEG = 30.0
    ASSUMED_V_DEG = 20.0

    # px per degree from measured span
    ppd_x = max(ir.lx_span, ir.rx_span) / ASSUMED_H_DEG
    ppd_y = max(ir.ly_span, ir.ry_span) / ASSUMED_V_DEG

    # Minimum floor to avoid division by zero
    ppd_x = max(ppd_x, 0.1)
    ppd_y = max(ppd_y, 0.1)

    print(f"[DispCal] Centre: L=({centre_l[0]:.1f},{centre_l[1]:.1f})  "
          f"R=({centre_r[0]:.1f},{centre_r[1]:.1f})")
    print(f"[DispCal] px/deg: x={ppd_x:.3f}  y={ppd_y:.3f}")
    print(f"[DispCal] Effective range: "
          f"±{ir.lx_span/2/ppd_x:.1f}° H  ±{ir.ly_span/2/ppd_y:.1f}° V")

    return CalibrationData(
        screen         = screen,
        is_valid       = True,
        iris_centre_l  = centre_l,
        iris_centre_r  = centre_r,
        iris_px_per_deg= (ppd_x, ppd_y),
    )


class GazeCalibration:
    """
    Range-detection based displacement calibration.

    Runs the L/R/U/D/Centre range detection to measure iris pixel span
    and resting centre, then builds a displacement-based CalibrationData.
    No grid dots, no affine transform, no RANSAC.
    Takes ~10 seconds total.
    """
    def __init__(self, capture: "LiveGazeCapture"):
        self.capture    = capture
        self.iris_range = None

    def run(self, collect_sec: float = 2.5) -> CalibrationData:
        screen = self.capture.screen
        if not self.capture._running:
            self.capture.start()
            time.sleep(1.0)

        self.capture.disable_kalman()
        print("[Cal] Running range detection for displacement calibration...")
        ir = _run_range_detection(self.capture)
        self.iris_range = ir

        if not ir.is_usable(min_span_px=2.0):
            print("[Cal] Range too small -- geometric fallback")
            print("      Tip: sit closer (30cm) and move eyes widely L/R/U/D")
            self.capture.enable_kalman()
            return CalibrationData(screen=screen, is_valid=False)

        cal = _compute_displacement_cal(self.capture, ir)
        self.capture.enable_kalman()
        print("[Cal] Displacement calibration complete.")
        return cal


class MouseClickCalibration:
    """
    Click-assisted displacement calibration.

    Phase 1: Range detection (same as GazeCalibration) to get iris span + centre.
    Phase 2: Optional click phase to refine the centre estimate.
              User clicks the screen centre dot -- iris position at that moment
              is used as the true straight-ahead centre, overriding the median.
              This corrects for any head tilt offset in the range detection.

    The click phase is lightweight: just 1 click on a centre dot.
    No grid, no affine, no RANSAC needed.
    """
    def __init__(self, capture: "LiveGazeCapture"):
        self.capture = capture

    def run(self, n_clicks: int = 12) -> CalibrationData:
        screen = self.capture.screen
        w, h   = screen.width_px, screen.height_px

        if not self.capture._running:
            self.capture.start()
            time.sleep(1.0)

        self.capture.disable_kalman()

        # ── Phase 1: range detection ──────────────────────────────────────────
        print("[ClickCal] Phase 1: range detection...")
        ir = _run_range_detection(self.capture)

        if not ir.is_usable(min_span_px=2.0):
            print("[ClickCal] Range too small -- geometric fallback")
            self.capture.enable_kalman()
            return CalibrationData(screen=screen, is_valid=False)

        # ── Phase 2: centre refinement via single click ───────────────────────
        print("[ClickCal] Phase 2: look at centre dot and click it to refine centre...")
        centre_l, centre_r = self._collect_centre_click(w, h, ir)

        # ── Build displacement calibration ────────────────────────────────────
        # Override iris range centre with click-refined centre
        ir_refined = IrisRange(
            lx_min=ir.lx_min, lx_max=ir.lx_max,
            ly_min=ir.ly_min, ly_max=ir.ly_max,
            rx_min=ir.rx_min, rx_max=ir.rx_max,
            ry_min=ir.ry_min, ry_max=ir.ry_max,
            lx_center=centre_l[0], ly_center=centre_l[1],
            rx_center=centre_r[0], ry_center=centre_r[1],
        )

        cal = _compute_displacement_cal(self.capture, ir_refined)
        self.capture.enable_kalman()
        print("[ClickCal] Done.")
        return cal

    def _collect_centre_click(self, w, h, ir):
        """Show a single centre dot. User looks at it and clicks. Returns refined iris centre."""
        WIN     = "Centre Calibration  |  Look at dot then LEFT CLICK  |  ESC = skip"
        clicked = [None]

        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        def on_mouse(event, mx, my, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                clicked[0] = time.time()
        cv2.setMouseCallback(WIN, on_mouse)

        collecting    = False
        collect_start = 0.0
        iris_window   = []
        COLLECT_SEC   = 0.3
        done          = False
        centre_l      = (ir.lx_center, ir.ly_center)
        centre_r      = (ir.rx_center, ir.ry_center)

        cx, cy = w // 2, h // 2

        while not done:
            now    = time.time()
            canvas = np.zeros((h, w, 3), dtype=np.uint8)

            # pulsing centre dot
            pulse = 0.5 + 0.5 * math.sin(now * 4.0)
            r_out = int(28 + 8 * pulse)
            cv2.circle(canvas, (cx, cy), r_out, (50, 50, 180), 2)
            cv2.circle(canvas, (cx, cy), 18,    (70, 70, 220), -1)
            cv2.circle(canvas, (cx, cy),  7,    (255, 255, 255), -1)

            cv2.putText(canvas, "Look at the dot  then  LEFT CLICK it",
                        (w//2 - 300, h - 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (140, 150, 170), 2, cv2.LINE_AA)
            cv2.putText(canvas, "ESC = skip centre refinement",
                        (w//2 - 200, h - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 90, 110), 1, cv2.LINE_AA)

            if clicked[0] and not collecting:
                collecting    = True
                collect_start = clicked[0]
                self.capture.clear_buffer()
                iris_window   = []

            if collecting:
                prog = min((now - collect_start) / COLLECT_SEC, 1.0)
                cv2.ellipse(canvas, (cx, cy), (32, 32), -90, 0,
                            int(360 * prog), (80, 220, 255), 3)
                latest = self.capture.get_latest_sample()
                if latest and not latest.l_blink:
                    iris_window.append(latest)
                if now - collect_start >= COLLECT_SEC:
                    if len(iris_window) >= 2:
                        centre_l = (float(np.mean([s.lx_px for s in iris_window])),
                                    float(np.mean([s.ly_px for s in iris_window])))
                        centre_r = (float(np.mean([s.rx_px for s in iris_window])),
                                    float(np.mean([s.ry_px for s in iris_window])))
                        print(f"  [ClickCal] Centre refined: "
                              f"L=({centre_l[0]:.1f},{centre_l[1]:.1f})  "
                              f"R=({centre_r[0]:.1f},{centre_r[1]:.1f})")
                    done = True

            cv2.imshow(WIN, canvas)
            key = cv2.waitKey(16) & 0xFF
            if key in (27, ord('q')):
                print("  [ClickCal] Centre refinement skipped")
                done = True

        cv2.destroyWindow(WIN)
        return centre_l, centre_r

# Convenience: full live scan with calibration
# ──────────────────────────────────────────────────────────────────────────────

def run_live_scan(
    model_path:      str   = "face_landmarker.task",
    camera_index:    int   = 0,
    duration_sec:    float = 30.0,
    screen:          Optional[ScreenConfig] = None,
    skip_calibration: bool = False,
) -> np.ndarray:
    """
    One-shot convenience function:
      1. Start capture
      2. Run 5-point calibration (unless skip_calibration=True)
      3. Record for duration_sec
      4. Return (N,4) array ready for engine.predict()

    Parameters
    ----------
    model_path        : path to face_landmarker.task
    camera_index      : webcam index
    duration_sec      : recording duration in seconds
    screen            : ScreenConfig (uses defaults if None)
    skip_calibration  : skip calibration and use geometric fallback

    Returns
    -------
    numpy array (N,4) [LX,LY,RX,RY] at 50Hz
    """
    cap = LiveGazeCapture(
        model_path=model_path,
        camera_index=camera_index,
        screen=screen or ScreenConfig(),
    )

    if not skip_calibration:
        cal = GazeCalibration(cap)
        cap.calibration = cal.run()

    cap.start()
    print(f"[LiveScan] Recording for {duration_sec}s...")
    arr = cap.record(duration_sec=duration_sec)
    cap.stop()
    return arr


# ──────────────────────────────────────────────────────────────────────────────
# Entry point — quick test without model files
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  dyslexia_live_engine.py — dependency check")
    print("=" * 60)

    ok = True
    try:
        import mediapipe as mp
        print(f"  mediapipe  : {mp.__version__}  ✓")
    except ImportError:
        print("  mediapipe  : NOT INSTALLED  ✗  →  pip install mediapipe")
        ok = False

    try:
        import cv2
        print(f"  opencv     : {cv2.__version__}  ✓")
    except ImportError:
        print("  opencv     : NOT INSTALLED  ✗  →  pip install opencv-python")
        ok = False

    try:
        import numpy as np
        print(f"  numpy      : {np.__version__}  ✓")
    except ImportError:
        print("  numpy      : NOT INSTALLED  ✗")
        ok = False

    model_file = "face_landmarker.task"
    if Path(model_file).exists():
        print(f"  model file : {model_file}  ✓")
    else:
        print(f"  model file : NOT FOUND  ✗")
        print(f"\n  Download with PowerShell:")
        print(f"  Invoke-WebRequest -Uri \"https://storage.googleapis.com/mediapipe-models/"
              f"face_landmarker/face_landmarker/float16/1/face_landmarker.task\""
              f" -OutFile \"{model_file}\"")
        ok = False

    cam_idx = 0
    cap_test = cv2.VideoCapture(cam_idx)
    if cap_test.isOpened():
        print(f"  camera {cam_idx}   : accessible  ✓")
        cap_test.release()
    else:
        print(f"  camera {cam_idx}   : NOT accessible  ✗")
        ok = False

    print()
    if ok:
        print("  All checks passed. Ready to use LiveGazeCapture.")
        print()
        print("  Quick start:")
        print("    from dyslexia_live_engine import run_live_scan")
        print("    from dyslexia_eye_engine_v2 import DyslexiaEyeEngineV2")
        print("    arr    = run_live_scan(duration_sec=30)")
        print("    engine = DyslexiaEyeEngineV2(...)")
        print("    result = engine.predict(arr)")
        print("    print(result)")
    else:
        print("  Fix the issues above before using LiveGazeCapture.")
        sys.exit(1)