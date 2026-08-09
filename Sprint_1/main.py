"""
EMG Logger - Sprint 1
======================
Doc du lieu EMG 6 kenh qua Serial (ESP32-S3) va luu thanh CSV theo
protocol da dong bang cua du an:

    SEQ,TIME_US,CH1,CH2,CH3,CH4,CH5,CH6

Tinh nang Sprint 1:
    - Chon COM port + baudrate (mac dinh 921600)
    - Nhap Subject ID / Session ID / Donning position / Gesture / Trial
    - Nut START: tu dong chay timeline 1 trial (8s):
          Rest(2s) -> Cue(1s) -> Hold(3s) -> Relax(2s)
      va ghi CSV lien tuc trong suot 8s, kem marker thoi gian
      (cue_on_us, hold_start_us, hold_end_us) luu vao metadata.json
    - Nut STOP: huy trial dang chay giua chung (ghi chu "aborted")
    - Hien thi real-time: sample count, sampling rate uoc tinh
    - Tu tao cau truc thu muc:
          Dataset/Subject_XX/Session_YY_posZ/raw/S{subj}_Se{sess}_{gesture}_T{trial}.csv
    - Tu cap nhat metadata.json cho tung session

Khong lam: khong ve realtime plot (PyQtGraph) - de danh cho sprint sau.
"""

import sys
import os
import json
import time
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QLineEdit, QSpinBox, QTextEdit,
    QGroupBox, QMessageBox, QProgressBar
)

import serial
import serial.tools.list_ports

BAUDRATE = 921600
DATASET_ROOT = "Dataset"

GESTURES = [
    "rest",
    "power_grip",
    "hand_open",
    "wrist_flexion",
    "wrist_extension",
    "pinch",
    "lateral_pinch",
    "pronation_supination",
]

# Timeline (ms) - moc thoi gian TUYET DOI tinh tu luc bam Start
T_REST_END = 2000       # 0 -> 2s   : Rest
T_CUE_END = 3000        # 2 -> 3s   : Cue ("Get ready")   -> marker CUE_ON tai 2s
T_HOLD_END = 6000        # 3 -> 6s   : Hold (giu gesture)  -> marker HOLD_START tai 3s
T_TRIAL_END = 8000       # 6 -> 8s   : Relax               -> marker HOLD_END tai 6s


class SerialReaderThread(QThread):
    """Doc lien tuc tu Serial, khong block UI. Parse dung protocol:
    SEQ,TIME_US,CH1,CH2,CH3,CH4,CH5,CH6
    """
    sample_received = Signal(int, int, int, int, int, int, int, int, str)  # ..., raw_line
    error_occurred = Signal(str)

    def __init__(self, port, baudrate=BAUDRATE):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self._running = False
        self._ser = None

    def run(self):
        try:
            self._ser = serial.Serial(self.port, self.baudrate, timeout=1)
        except Exception as e:
            self.error_occurred.emit(f"Khong mo duoc port {self.port}: {e}")
            return

        self._running = True
        # xa bo dong loi dau tien co the bi cat nua chung
        self._ser.readline()

        while self._running:
            try:
                raw = self._ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) != 8:
                    # dong khong dung protocol (nhieu, debug string lac vao...) -> bo qua
                    continue
                seq, t_us, c1, c2, c3, c4, c5, c6 = (int(x) for x in parts)
                self.sample_received.emit(seq, t_us, c1, c2, c3, c4, c5, c6, line)
            except ValueError:
                continue
            except Exception as e:
                self.error_occurred.emit(f"Loi doc serial: {e}")
                break

    def stop(self):
        self._running = False
        self.wait(1500)
        if self._ser and self._ser.is_open:
            self._ser.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EMG Logger - Sprint 1")
        self.resize(760, 640)

        self.reader_thread = None
        self.csv_file = None
        self.recording = False
        self.trial_active = False
        self.trial_start_ms = None
        self.latest_time_us = None
        self.markers = {}
        self.sample_count_total = 0
        self.sample_count_trial = 0
        self._rate_window_count = 0
        self._rate_window_start = None

        self.state_timer = QTimer(self)
        self.state_timer.setInterval(50)
        self.state_timer.timeout.connect(self._tick)

        self.rate_timer = QTimer(self)
        self.rate_timer.setInterval(1000)
        self.rate_timer.timeout.connect(self._update_rate)

        self._build_ui()
        self._refresh_ports()

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Serial connection group ---
        conn_group = QGroupBox("Ket noi Serial")
        conn_layout = QHBoxLayout(conn_group)
        self.port_combo = QComboBox()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_ports)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.port_combo, 1)
        conn_layout.addWidget(refresh_btn)
        conn_layout.addWidget(QLabel(f"Baud: {BAUDRATE}"))
        conn_layout.addWidget(self.connect_btn)
        layout.addWidget(conn_group)

        # --- Session/trial labeling group ---
        label_group = QGroupBox("Thong tin ghi")
        grid = QGridLayout(label_group)

        self.subject_edit = QLineEdit("S01")
        self.session_edit = QLineEdit("Se01")
        self.position_edit = QLineEdit("A")
        self.gesture_combo = QComboBox()
        self.gesture_combo.addItems(GESTURES)
        self.trial_spin = QSpinBox()
        self.trial_spin.setRange(1, 999)
        self.trial_spin.setValue(1)

        grid.addWidget(QLabel("Subject ID:"), 0, 0)
        grid.addWidget(self.subject_edit, 0, 1)
        grid.addWidget(QLabel("Session ID:"), 0, 2)
        grid.addWidget(self.session_edit, 0, 3)
        grid.addWidget(QLabel("Donning pos:"), 1, 0)
        grid.addWidget(self.position_edit, 1, 1)
        grid.addWidget(QLabel("Gesture:"), 1, 2)
        grid.addWidget(self.gesture_combo, 1, 3)
        grid.addWidget(QLabel("Trial #:"), 2, 0)
        grid.addWidget(self.trial_spin, 2, 1)
        layout.addWidget(label_group)

        # --- Trial control group ---
        trial_group = QGroupBox("Trial (8s: Rest 2s -> Cue 1s -> Hold 3s -> Relax 2s)")
        trial_layout = QVBoxLayout(trial_group)

        self.state_label = QLabel("IDLE")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 12px;"
        )
        self.progress = QProgressBar()
        self.progress.setRange(0, T_TRIAL_END)
        self.progress.setValue(0)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("START")
        self.start_btn.setStyleSheet("font-size: 16px; padding: 8px;")
        self.start_btn.clicked.connect(self._start_trial)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setStyleSheet("font-size: 16px; padding: 8px;")
        self.stop_btn.clicked.connect(self._abort_trial)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)

        trial_layout.addWidget(self.state_label)
        trial_layout.addWidget(self.progress)
        trial_layout.addLayout(btn_row)
        layout.addWidget(trial_group)

        # --- Status group ---
        status_group = QGroupBox("Trang thai")
        status_layout = QHBoxLayout(status_group)
        self.sample_count_label = QLabel("Samples: 0")
        self.rate_label = QLabel("Rate: -- Hz")
        self.file_label = QLabel("File: --")
        status_layout.addWidget(self.sample_count_label)
        status_layout.addWidget(self.rate_label)
        status_layout.addWidget(self.file_label, 1)
        layout.addWidget(status_group)

        # --- Log ---
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit, 1)

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_edit.append(f"[{ts}] {msg}")

    # ---------------- Serial connect ----------------
    def _refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.port_combo.addItem(f"{p.device} - {p.description}", p.device)
        if not ports:
            self._log("Khong tim thay COM port nao.")

    def _toggle_connection(self):
        if self.reader_thread is None:
            port = self.port_combo.currentData()
            if not port:
                QMessageBox.warning(self, "Loi", "Chua chon COM port.")
                return
            self.reader_thread = SerialReaderThread(port, BAUDRATE)
            self.reader_thread.sample_received.connect(self._on_sample)
            self.reader_thread.error_occurred.connect(self._on_serial_error)
            self.reader_thread.start()
            self.connect_btn.setText("Disconnect")
            self.rate_timer.start()
            self._log(f"Da ket noi {port} @ {BAUDRATE} baud.")
        else:
            self._disconnect()

    def _disconnect(self):
        if self.reader_thread:
            self.reader_thread.stop()
            self.reader_thread = None
        self.rate_timer.stop()
        self.connect_btn.setText("Connect")
        self._log("Da ngat ket noi.")

    def _on_serial_error(self, msg):
        self._log(f"LOI: {msg}")
        QMessageBox.critical(self, "Loi Serial", msg)
        self._disconnect()

    # ---------------- Sample handling ----------------
    def _on_sample(self, seq, t_us, c1, c2, c3, c4, c5, c6, raw_line):
        self.latest_time_us = t_us
        self.sample_count_total += 1
        self._rate_window_count += 1

        if self.recording and self.csv_file:
            self.csv_file.write(raw_line + "\n")
            self.sample_count_trial += 1

        self.sample_count_label.setText(
            f"Samples: {self.sample_count_total} (trial: {self.sample_count_trial})"
        )

    def _update_rate(self):
        self.rate_label.setText(f"Rate: {self._rate_window_count} Hz")
        self._rate_window_count = 0

    # ---------------- Trial state machine ----------------
    def _start_trial(self):
        if self.reader_thread is None:
            QMessageBox.warning(self, "Loi", "Chua ket noi Serial.")
            return
        if self.trial_active:
            return

        subject = self.subject_edit.text().strip()
        session = self.session_edit.text().strip()
        position = self.position_edit.text().strip()
        gesture = self.gesture_combo.currentText()
        trial_num = self.trial_spin.value()

        if not subject or not session:
            QMessageBox.warning(self, "Loi", "Thieu Subject ID / Session ID.")
            return

        session_dir = os.path.join(
            DATASET_ROOT, subject, f"{session}_pos{position}"
        )
        raw_dir = os.path.join(session_dir, "raw")
        os.makedirs(raw_dir, exist_ok=True)

        filename = f"{subject}_{session}_{gesture}_T{trial_num:02d}.csv"
        filepath = os.path.join(raw_dir, filename)

        if os.path.exists(filepath):
            resp = QMessageBox.question(
                self, "File da ton tai",
                f"{filename} da ton tai. Ghi de?",
                QMessageBox.Yes | QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return

        self.csv_file = open(filepath, "w", newline="")
        self.current_filepath = filepath
        self.current_session_dir = session_dir
        self.current_meta = {
            "subject_id": subject,
            "session_id": session,
            "donning_position": position,
            "gesture": gesture,
            "trial": trial_num,
            "file": os.path.relpath(filepath, session_dir).replace("\\", "/"),
        }

        self.markers = {}
        self.sample_count_trial = 0
        self.recording = True
        self.trial_active = True
        self.trial_start_ms = time.monotonic() * 1000.0
        self._current_state = "rest"

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.file_label.setText(f"File: {filepath}")
        self.state_label.setText("REST")
        self.state_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 12px; background:#cfd8dc;"
        )
        self._log(f"Bat dau trial: {filename}")
        self.state_timer.start()

    def _tick(self):
        elapsed = time.monotonic() * 1000.0 - self.trial_start_ms
        elapsed = min(elapsed, T_TRIAL_END)
        self.progress.setValue(int(elapsed))

        new_state = self._current_state
        if elapsed < T_REST_END:
            new_state = "rest"
        elif elapsed < T_CUE_END:
            new_state = "cue"
        elif elapsed < T_HOLD_END:
            new_state = "hold"
        elif elapsed < T_TRIAL_END:
            new_state = "relax"
        else:
            self._finish_trial()
            return

        if new_state != self._current_state:
            self._on_state_change(new_state)
            self._current_state = new_state

    def _on_state_change(self, new_state):
        colors = {
            "cue": "#fff59d",
            "hold": "#ef9a9a",
            "relax": "#c8e6c9",
        }
        labels = {"cue": "GET READY", "hold": "HOLD", "relax": "RELAX"}
        if new_state in labels:
            self.state_label.setText(labels[new_state])
            self.state_label.setStyleSheet(
                f"font-size: 28px; font-weight: bold; padding: 12px; "
                f"background:{colors[new_state]};"
            )

        # ghi marker theo TIME_US thuc te tu ESP32, khong dung wall-clock
        if new_state == "cue":
            self.markers["cue_on_us"] = self.latest_time_us
        elif new_state == "hold":
            self.markers["hold_start_us"] = self.latest_time_us
        elif new_state == "relax":
            self.markers["hold_end_us"] = self.latest_time_us

    def _finish_trial(self):
        self.state_timer.stop()
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        self.recording = False
        self.trial_active = False

        self.current_meta.update(self.markers)
        self.current_meta["sample_count"] = self.sample_count_trial
        self.current_meta["status"] = "complete"
        self._append_metadata(self.current_session_dir, self.current_meta)

        self.state_label.setText("DONE")
        self.state_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 12px; background:#90caf9;"
        )
        self.progress.setValue(T_TRIAL_END)
        self._log(
            f"Hoan tat trial ({self.sample_count_trial} samples) -> "
            f"{self.current_filepath}"
        )

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # tu tang trial number cho lan sau
        self.trial_spin.setValue(self.trial_spin.value() + 1)

    def _abort_trial(self):
        if not self.trial_active:
            return
        self.state_timer.stop()
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        self.recording = False
        self.trial_active = False

        self.current_meta.update(self.markers)
        self.current_meta["sample_count"] = self.sample_count_trial
        self.current_meta["status"] = "aborted"
        self._append_metadata(self.current_session_dir, self.current_meta)

        self.state_label.setText("ABORTED")
        self.state_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 12px; background:#ff8a65;"
        )
        self._log(f"Trial bi huy giua chung -> {self.current_filepath}")

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    # ---------------- metadata.json ----------------
    def _append_metadata(self, session_dir, trial_meta):
        meta_path = os.path.join(session_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}
        else:
            data = {}

        data.setdefault("subject_id", trial_meta["subject_id"])
        data.setdefault("session_id", trial_meta["session_id"])
        data.setdefault("donning_position", trial_meta["donning_position"])
        data.setdefault("sampling_rate_hz", 500)
        data.setdefault("baseline_calibration", {})
        data.setdefault("trials", [])
        data["date"] = datetime.now().strftime("%Y-%m-%d")

        data["trials"].append({
            "file": trial_meta["file"],
            "gesture": trial_meta["gesture"],
            "trial": trial_meta["trial"],
            "cue_on_us": trial_meta.get("cue_on_us"),
            "hold_start_us": trial_meta.get("hold_start_us"),
            "hold_end_us": trial_meta.get("hold_end_us"),
            "sample_count": trial_meta.get("sample_count"),
            "status": trial_meta.get("status"),
        })

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def closeEvent(self, event):
        if self.trial_active:
            self._abort_trial()
        self._disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
