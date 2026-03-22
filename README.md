# NeuroScan

Multimodal Dyslexia & Dysarthria Screening Dashboard — React + FastAPI.

```
neuroscan/
├── frontend/                      React 18 · TypeScript · Tailwind CSS
└── backend/
    ├── app/                       FastAPI application
    ├── models/                    Model weight files (place here)
    ├── neuroscan_speech_runner.py  Desktop speech recorder (auto-launched)
    ├── neuroscan_eye_runner.py     Desktop eye-tracking runner (auto-launched)
    ├── neuroscan_bridge.py         CLI bridge for manual posting
    └── run.py                      Server launcher
```

---

## Quick start

### 1. Backend

```bash
cd backend
cp .env.example .env          # edit model paths if needed also only run this if .env is not present
pip install -r requirements.txt
python run.py
```

API docs: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm start          # http://localhost:3000
```

---

## Model files

Place all model files in `backend/models/`:

| File | Module | Notes |
|------|--------|-------|
| `dysarthria_cnn_bilstm.pt` | Speech | CNN+BiLSTM trained on TORGO |
| `dyslexia_ensemble.joblib` | Eye tracking | VotingClassifier (RF+SVM+XGBoost) |
| `dyslexia_rfecv.joblib` | Eye tracking | RFECV feature selector |
| `dyslexia_feature_meta.json` | Eye tracking | Feature names + col means |
| `handwriting_yolo.pt` | Handwriting | YOLOv8 letter classifier |

Also place `face_landmarker.task` in `backend/`:

```powershell
# Windows PowerShell (if face_landmasker.task is not present with the backend folder)
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile "backend/face_landmarker.task"
```

---

## How the desktop runners work

When the user clicks "Launch Recording Window" or "Launch Eye-Tracking Window"
in the web UI, the backend spawns a subprocess:

**Speech** → `neuroscan_speech_runner.py`
- Opens a small customtkinter window
- Records at 16kHz PCM (identical to TORGO training format)
- Runs `DysarthriaEngine.predict()` locally
- Posts result to `/dysarthria/predict_result`
- Web UI receives it automatically

**Eye tracking** → `neuroscan_eye_runner.py`
- Starts `LiveGazeCapture` (MediaPipe FaceLandmarker)
- Runs displacement-based calibration (~10s)
- Shows reading passage in fullscreen OpenCV window (~30s)
- Runs `DyslexiaEyeEngineV2.predict(arr)`
- Posts gaze array to `/dyslexia/predict_array`
- Web UI receives it automatically

---

## API routes

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Liveness probe |
| POST | /launch/dysarthria | Spawn speech runner |
| POST | /launch/dyslexia | Spawn eye-tracking runner |
| GET | /launch/status | Runner process status |
| POST | /launch/cancel/{module} | Kill runner |
| POST | /dysarthria/predict_result | Receive result from runner |
| POST | /dysarthria/predict_file | Direct WAV file inference |
| POST | /handwriting/score | Image → reversal score |
| POST | /dyslexia/predict_array | (N,4) gaze array → result |
| GET | /sessions | List all sessions |
| GET | /sessions/{id} | Get one session |
| DELETE | /sessions/{id} | Delete session |

---

## .env reference

```env
DYSARTHRIA_MODEL_PATH=models/dysarthria_cnn_bilstm.pt
DYSARTHRIA_WINDOW_SEC=6.79
DYSARTHRIA_OVERLAP_SEC=3.0
DYSARTHRIA_DEFAULT_GENDER=male

DYSLEXIA_MODEL_PATH=models/dyslexia_ensemble.joblib
DYSLEXIA_RFECV_PATH=models/dyslexia_rfecv.joblib
DYSLEXIA_META_PATH=models/dyslexia_feature_meta.json
DYSLEXIA_THRESHOLD=0.5

HANDWRITING_MODEL_PATH=models/handwriting_yolo.pt
```
