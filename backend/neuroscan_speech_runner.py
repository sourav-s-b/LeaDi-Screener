"""
neuroscan_speech_runner.py
==========================
Minimal speech recording + inference window.
Launched automatically by the NeuroScan web backend when user clicks
"Start Recording" on the speech test page.

  python neuroscan_speech_runner.py --model models/best_cnn_bilstm.pt --api http://localhost:8000 --gender male

When recording is complete and inference finishes, posts result to
  POST {api}/dysarthria/predict_result
then closes the window.

Requires: pip install customtkinter sounddevice soundfile
Engine:   dysarthria_engine.py (must be in same folder or on PYTHONPATH)
"""

import argparse
import os
import sys
import time
import threading
import json
from pathlib import Path

import numpy as np

try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import messagebox
    _CTK_OK = True
except ImportError:
    _CTK_OK = False

try:
    import sounddevice as sd
    import soundfile as sf
    _AUDIO_OK = True
except ImportError:
    _AUDIO_OK = False

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _MPL_OK = True
except ImportError:
    _MPL_OK = False

# ── colour palette (matches main app) ─────────────────────────────────────────
C = {
    "bg":      "#0d0f14",
    "surface": "#141820",
    "surface2":"#1c2230",
    "border":  "#2a3348",
    "accent":  "#4f8ef7",
    "danger":  "#ef4444",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "text":    "#e2e8f0",
    "dim":     "#64748b",
}

SR         = 16000
RECORD_SEC = 12.0


# ── Waveform widget ───────────────────────────────────────────────────────────
class WaveBar(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C["surface2"], corner_radius=8, **kw)
        if not _MPL_OK:
            return
        self.fig  = Figure(figsize=(5, 1.2), facecolor=C["surface2"])
        self.ax   = self.fig.add_subplot(111)
        self.ax.set_facecolor(C["surface2"])
        self.ax.axis("off")
        self.fig.tight_layout(pad=0)
        self.cv   = FigureCanvasTkAgg(self.fig, master=self)
        self.cv.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
        self._d   = np.zeros(200)

    def update(self, data: np.ndarray):
        if not _MPL_OK:
            return
        if len(data) > 200:
            data = data[::len(data)//200][:200]
        self._d = np.pad(data, (0, max(0, 200-len(data))))
        self.ax.clear(); self.ax.set_facecolor(C["surface2"]); self.ax.axis("off")
        x = np.linspace(0, 1, len(self._d))
        self.ax.fill_between(x, self._d, -self._d, color=C["accent"], alpha=0.7)
        self.ax.set_ylim(-1, 1)
        self.fig.tight_layout(pad=0); self.cv.draw()

    def clear(self):
        self.update(np.zeros(200))


# ── Main window ───────────────────────────────────────────────────────────────
class SpeechRunner(ctk.CTk):
    def __init__(self, model_path: str, api_url: str, gender: str):
        super().__init__()
        self.model_path = model_path
        self.api_url    = api_url
        self.gender     = gender

        self.engine     = None
        self.recording  = False
        self.audio_buf  = []
        self.stream     = None
        self._anim_id   = None
        self._start_t   = 0.0
        self._last_wav  = None
        self._playing   = False

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("NeuroScan — Speech Test")
        self.geometry("520x480")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])

        self._build()
        self._load_engine()

    def _build(self):
        pad = {"padx": 28, "pady": 0}

        # Title
        ctk.CTkLabel(self, text="Speech Recording",
                     font=("DM Sans", 22, "bold"), text_color=C["text"]
                     ).pack(pady=(28, 2), **{"padx": 28})
        ctk.CTkLabel(self, text="Speak clearly for up to 12 seconds, then stop.",
                     font=("DM Sans", 11), text_color=C["dim"]
                     ).pack(**{"padx": 28})

        # Prompt
        self._prompt_frame = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        self._prompt_frame.pack(fill="x", padx=28, pady=(16, 0))
        ctk.CTkLabel(self._prompt_frame,
                     text='Say: "The quick brown fox jumps over the lazy dog."',
                     font=("DM Sans", 11, "italic"), text_color=C["dim"],
                     wraplength=440).pack(padx=16, pady=10)

        # Waveform
        self.wave = WaveBar(self, height=70)
        self.wave.pack(fill="x", padx=28, pady=(14, 0))

        # Timer + status
        self.timer_lbl = ctk.CTkLabel(self, text="0.0s",
                                       font=("DM Sans", 30, "bold"), text_color=C["dim"])
        self.timer_lbl.pack(pady=(8, 0))
        self.status_lbl = ctk.CTkLabel(self, text="Loading model…",
                                        font=("DM Sans", 11), text_color=C["dim"])
        self.status_lbl.pack(pady=(2, 10))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack()

        self.rec_btn = ctk.CTkButton(
            btn_frame, text="⏺  Record", width=160, height=46,
            fg_color=C["danger"], hover_color="#dc2626",
            font=("DM Sans", 14, "bold"), corner_radius=23,
            command=self._toggle_record, state="disabled"
        )
        self.rec_btn.pack(side="left", padx=6)

        self.play_btn = ctk.CTkButton(
            btn_frame, text="▶  Playback", width=130, height=46,
            fg_color=C["surface2"], hover_color=C["border"],
            font=("DM Sans", 13), corner_radius=23,
            command=self._play, state="disabled"
        )
        self.play_btn.pack(side="left", padx=6)

        # Result label
        self.result_lbl = ctk.CTkLabel(self, text="",
                                        font=("DM Sans", 13, "bold"), text_color=C["text"])
        self.result_lbl.pack(pady=(14, 0))

    # ── Engine loading ─────────────────────────────────────────────────────────
    def _load_engine(self):
        def _worker():
            try:
                # Add parent dirs to path so imports work from any CWD
                here = Path(__file__).parent
                for d in [here, here.parent, here / "app" / "services"]:
                    p = str(d)
                    if p not in sys.path:
                        sys.path.insert(0, p)

                from dysarthria_engine import DysarthriaEngine
                self.engine = DysarthriaEngine(
                    model_path=self.model_path,
                    gender=self.gender,
                )
                self.after(0, lambda: self._set_status("Ready — press Record", C["success"]))
                self.after(0, lambda: self.rec_btn.configure(state="normal"))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"Model error: {e}", C["danger"]))
        threading.Thread(target=_worker, daemon=True).start()

    # ── Recording ──────────────────────────────────────────────────────────────
    def _toggle_record(self):
        if self.recording:
            self._stop()
        else:
            self._start()

    def _start(self):
        if not _AUDIO_OK:
            messagebox.showerror("Error", "pip install sounddevice soundfile")
            return
        self.recording = True
        self.audio_buf = []
        self._start_t  = time.time()
        self.wave.clear()
        self.result_lbl.configure(text="")
        self.play_btn.configure(state="disabled")
        self.rec_btn.configure(text="⏹  Stop", fg_color=C["warning"], hover_color="#d97706")
        self._set_status("Recording…", C["danger"])

        self.stream = sd.InputStream(
            samplerate=SR, channels=1, dtype="float32",
            callback=self._cb, blocksize=1600
        )
        self.stream.start()
        self._tick()

    def _cb(self, indata, frames, time_info, status):
        self.audio_buf.append(indata[:, 0].copy())

    def _tick(self):
        if not self.recording:
            return
        elapsed = time.time() - self._start_t
        self.timer_lbl.configure(text=f"{elapsed:.1f}s")
        if self.audio_buf:
            recent = np.concatenate(self.audio_buf[-8:])
            self.wave.update(recent / (np.abs(recent).max() + 1e-9))
        if elapsed >= RECORD_SEC:
            self._stop()
            return
        self._anim_id = self.after(80, self._tick)

    def _stop(self):
        self.recording = False
        if self._anim_id:
            self.after_cancel(self._anim_id)
        audio_data = list(self.audio_buf)
        try:
            if self.stream:
                self.stream.abort()
                self.stream.close()
        except Exception:
            pass
        self.stream = None
        self.rec_btn.configure(text="⏺  Record", fg_color=C["danger"], hover_color="#dc2626")

        if not audio_data:
            self._set_status("No audio captured", C["danger"])
            return

        self._set_status("Analysing…", C["warning"])

        def _process():
            try:
                audio = np.concatenate(audio_data)
                tmp   = os.path.abspath("_neuroscan_speech_tmp.wav")
                sf.write(tmp, audio, SR)
                self._last_wav = tmp
                self.after(0, lambda: self.play_btn.configure(state="normal"))
                self.after(0, lambda: self._run_inference(tmp))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"Error: {e}", C["danger"]))
        threading.Thread(target=_process, daemon=True).start()

    # ── Inference ──────────────────────────────────────────────────────────────
    def _run_inference(self, wav_path: str):
        def _worker():
            try:
                self.engine.gender = 0 if self.gender == "male" else 1
                pred = self.engine.predict(wav_path)
                self.after(0, lambda: self._show_result(pred))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"Inference error: {e}", C["danger"]))
        threading.Thread(target=_worker, daemon=True).start()

    def _show_result(self, pred):
        if pred.error:
            self._set_status(f"Error: {pred.error}", C["danger"])
            return

        color = C["danger"] if pred.label == "dysarthria" else C["success"]
        label = pred.label.replace("_", " ").title()
        self.result_lbl.configure(
            text=f"{label}   {pred.risk:.1%} risk   conf {pred.confidence:.0%}",
            text_color=color
        )
        self._set_status("Analysis complete — sending to dashboard…", C["success"])

        # Post to NeuroScan API
        threading.Thread(target=self._post_result, args=(pred,), daemon=True).start()

    def _post_result(self, pred):
        try:
            import requests
            payload = {
                "risk":       pred.risk,
                "label":      pred.label,
                "confidence": pred.confidence,
                "n_chunks":   pred.n_chunks,
                "chunk_risks":list(pred.chunk_risks),
                "wav_path":   str(getattr(pred, "wav_path", "")),
            }
            r = requests.post(f"{self.api_url}/dysarthria/predict_result",
                              json=payload, timeout=10)
            r.raise_for_status()
            self.after(0, lambda: self._set_status(
                "✓ Result sent to dashboard — you can close this window.", C["success"]))
            self.after(3000, self.destroy)
        except Exception as e:
            self.after(0, lambda: self._set_status(
                f"Could not post to API: {e}", C["warning"]))

    # ── Playback ───────────────────────────────────────────────────────────────
    def _play(self):
        if not self._last_wav or not _AUDIO_OK:
            return
        if self._playing:
            sd.stop()
            self._playing = False
            self.play_btn.configure(text="▶  Playback")
            return

        def _do():
            try:
                data, sr_ = sf.read(self._last_wav, dtype="float32")
                self._playing = True
                self.after(0, lambda: self.play_btn.configure(text="⏹  Stop"))
                sd.play(data, sr_)
                sd.wait()
            except Exception:
                pass
            finally:
                self._playing = False
                self.after(0, lambda: self.play_btn.configure(text="▶  Playback"))
        threading.Thread(target=_do, daemon=True).start()

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _set_status(self, msg: str, color: str = None):
        kw = {"text": msg}
        if color:
            kw["text_color"] = color
        self.status_lbl.configure(**kw)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model",  default="models/dysarthria_cnn_bilstm.pt")
    ap.add_argument("--api",    default="http://localhost:8000")
    ap.add_argument("--gender", default="male", choices=["male","female"])
    args = ap.parse_args()

    if not _CTK_OK:
        print("[ERROR] pip install customtkinter")
        sys.exit(1)
    if not _AUDIO_OK:
        print("[ERROR] pip install sounddevice soundfile")
        sys.exit(1)

    app = SpeechRunner(
        model_path = args.model,
        api_url    = args.api,
        gender     = args.gender,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
