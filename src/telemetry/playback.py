import sys
import os
import argparse
import pandas as pd
import numpy as np
import json
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

from .data_manager import TelemetryData, TRACK_MAP
from .plotter import PlotterWindow, TrackMapWindow, SteeringWheelWindow
from .recorder import TelemetryRecorder

class PlaybackControls(QtWidgets.QWidget):
    seek_changed = QtCore.pyqtSignal(int)
    play_toggled = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        
        self.btn_play = QtWidgets.QPushButton("Play")
        self.btn_play.setCheckable(True)
        self.btn_play.toggled.connect(self._on_play_toggled)
        
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.seek_changed.emit)
        
        self.lbl_time = QtWidgets.QLabel("00:00 / 00:00")
        
        layout.addWidget(self.btn_play)
        layout.addWidget(self.slider)
        layout.addWidget(self.lbl_time)

    def _on_play_toggled(self, checked):
        self.btn_play.setText("Pause" if checked else "Play")
        self.play_toggled.emit(checked)

    def set_range(self, max_val):
        self.slider.setRange(0, max_val)

    def set_value(self, val):
        self.slider.blockSignals(True)
        self.slider.setValue(val)
        self.slider.blockSignals(False)

    def set_time_labels(self, current_sec, total_sec):
        cur = f"{int(current_sec // 60):02d}:{int(current_sec % 60):02d}"
        tot = f"{int(total_sec // 60):02d}:{int(total_sec % 60):02d}"
        self.lbl_time.setText(f"{cur} / {tot}")

class PlaybackManager(QtCore.QObject):
    playback_finished = QtCore.pyqtSignal()

    def __init__(self, telemetry_data, df, metadata):
        super().__init__()
        self.telemetry_data = telemetry_data
        # Ensure data is sorted by time for consistent playback
        self.df = df.sort_values('time').reset_index(drop=True)
        self.metadata = metadata
        self.current_idx = 0
        self.is_playing = False
        self.current_laps = {} # car_idx -> lap_num
        
        # Pre-populate all lap data for quick switching
        self.laps_data = {} # car_idx -> {lap_num: lap_data}
        self._cache_all_laps()
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(16) 
        
        self._initial_setup()

    def _cache_all_laps(self):
        """Cache all lap data from the recording."""
        for car_idx, car_df in self.df.groupby('car_idx'):
            car_idx = int(car_idx)
            if car_idx >= 22: continue
            self.laps_data[car_idx] = {}
            for lap_num, lap_df in car_df.groupby('lap'):
                self.laps_data[car_idx][int(lap_num)] = {
                    "distance": lap_df['distance'].tolist(),
                    "speed": lap_df['speed'].tolist(),
                    "rpm": lap_df['rpm'].tolist(),
                    "throttle": lap_df['throttle'].tolist(),
                    "brake": lap_df['brake'].tolist(),
                    "steer": lap_df['steer'].tolist(),
                    "time": lap_df['time'].tolist(),
                    "tyre_wear": [0]*len(lap_df), 
                    "ers_store": [0]*len(lap_df),
                    "pos_x": lap_df['pos_x'].tolist(),
                    "pos_z": lap_df['pos_z'].tolist()
                }

    def _initial_setup(self):
        """Set up initial state for plotting."""
        with self.telemetry_data.lock:
            self.telemetry_data.track_name = self.metadata.get("track", "Unknown")
            self.telemetry_data.session_type = self.metadata.get("session_type", 0)
            self.telemetry_data.player_idx = self.metadata.get("player_idx", 0)
            self.telemetry_data.rival_car_idx = self.metadata.get("rival_car_idx", 255)
            
            # Find and set the best lap for the player
            best_lap_time = float('inf')
            best_lap_data = None
            p_idx = self.telemetry_data.player_idx
            if p_idx in self.laps_data:
                for lap_data in self.laps_data[p_idx].values():
                    if len(lap_data["time"]) > 1:
                        lap_time = lap_data["time"][-1] - lap_data["time"][0]
                        if lap_time < best_lap_time:
                            best_lap_time = lap_time
                            best_lap_data = lap_data
            
            if best_lap_data:
                self.telemetry_data.best_lap_data = best_lap_data
                self.telemetry_data.best_lap_time = best_lap_time

            # Trigger initial lap data load
            self.update_telemetry_state()

    def _on_tick(self):
        if not self.is_playing:
            return
            
        if self.current_idx < len(self.df):
            current_time = self.df.iloc[self.current_idx]['time']
            # Process all updates for this point in time
            while self.current_idx < len(self.df) and self.df.iloc[self.current_idx]['time'] <= current_time:
                self.update_telemetry_state()
                self.current_idx += 1
        else:
            self.is_playing = False
            self.playback_finished.emit()

    def update_telemetry_state(self):
        if self.current_idx >= len(self.df):
            return
            
        row = self.df.iloc[self.current_idx]
        car_idx = int(row["car_idx"])
        lap_num = int(row["lap"])
        
        if car_idx >= 22:
            return
            
        with self.telemetry_data.lock:
            # Handle lap transitions for this car
            if car_idx not in self.current_laps or self.current_laps[car_idx] != lap_num:
                # If we were previously on a different lap, move it to history
                if car_idx in self.current_laps:
                    old_lap_data = self.telemetry_data.all_cars_data[car_idx]
                    if len(old_lap_data["distance"]) > 10:
                        self.telemetry_data.car_histories[car_idx].append({k: list(v) for k, v in old_lap_data.items()})

                # Load the new lap data into TelemetryData for plotting
                if car_idx in self.laps_data and lap_num in self.laps_data[car_idx]:
                    new_data = self.laps_data[car_idx][lap_num]
                    target = self.telemetry_data.all_cars_data[car_idx]
                    for k, v in new_data.items():
                        target[k] = v
                
                self.current_laps[car_idx] = lap_num
                if car_idx == self.telemetry_data.player_idx:
                    self.telemetry_data.current_lap_num = lap_num

            latch = self.telemetry_data.car_latches[car_idx]
            latch["speed_mph"] = row["speed"]
            latch["rpm"] = row["rpm"]
            latch["throttle"] = row["throttle"]
            latch["brake"] = row["brake"]
            latch["steer"] = row["steer"]
            latch["world_x"] = row["pos_x"]
            latch["world_z"] = row["pos_z"]
            latch["last_lap"] = lap_num
            
            if car_idx == self.telemetry_data.player_idx:
                self.telemetry_data.marker_dist = row["distance"]

    def seek(self, index):
        self.current_idx = max(0, min(index, len(self.df) - 1))
        self.update_telemetry_state()

def main():
    parser = argparse.ArgumentParser(description="F1 25 Telemetry Playback")
    parser.add_argument("file", help="Path to .parquet recording")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    
    # Load data
    recorder = TelemetryRecorder()
    df = recorder.read_recording(args.file)
    
    # Extract metadata from Parquet (if we saved it correctly)
    import pyarrow.parquet as pq
    table = pq.read_table(args.file)
    metadata = {}
    if b'telemetry_metadata' in table.schema.metadata:
        metadata = json.loads(table.schema.metadata[b'telemetry_metadata'].decode('utf-8'))
    
    telemetry_data = TelemetryData(max_laps=10)
    playback_mgr = PlaybackManager(telemetry_data, df, metadata)
    
    # Set up UI
    controls_window = QtWidgets.QMainWindow()
    controls_window.setWindowTitle(f"Playback: {os.path.basename(args.file)}")
    controls_window.resize(600, 100)
    
    controls = PlaybackControls(controls_window)
    controls_window.setCentralWidget(controls)
    controls.set_range(len(df) - 1)
    
    def on_play_toggled(playing):
        playback_mgr.is_playing = playing
        
    def on_playback_finished():
        controls.btn_play.setChecked(False)
        
    def on_seek(idx):
        playback_mgr.seek(idx)
        update_time_label()

    def update_time_label():
        row = df.iloc[playback_mgr.current_idx]
        total_time = df['time'].iloc[-1] - df['time'].iloc[0]
        current_time = row['time'] - df['time'].iloc[0]
        controls.set_time_labels(current_time, total_time)

    controls.play_toggled.connect(on_play_toggled)
    playback_mgr.playback_finished.connect(on_playback_finished)
    controls.seek_changed.connect(on_seek)
    
    # Update slider from manager
    def update_slider():
        if playback_mgr.is_playing:
            controls.set_value(playback_mgr.current_idx)
            update_time_label()
            
    timer = QtCore.QTimer()
    timer.timeout.connect(update_slider)
    timer.start(50)

    # Launch existing windows
    screens = app.screens()
    target_screen = screens[1] if len(screens) > 1 else screens[0]
    geom = target_screen.availableGeometry()
    width = geom.width() // 2
    height = geom.height()

    window = PlotterWindow(telemetry_data)
    window.setGeometry(geom.x(), geom.y(), width, height - 150)
    window.show()

    map_window = TrackMapWindow(telemetry_data)
    map_window.setGeometry(geom.x() + width, geom.y(), width, height - 150)
    map_window.show()
    
    steer_window = SteeringWheelWindow(telemetry_data)
    steer_window.setGeometry(geom.x() + geom.width() - 320, geom.y() + geom.height() - 420, 300, 300)
    steer_window.show()

    # Position controls at bottom
    controls_window.setGeometry(geom.x(), geom.y() + height - 150, geom.width(), 100)
    controls_window.show()
    
    # Connections
    map_window.request_toggle_tyre_wear.connect(window.toggle_tyre_wear)
    map_window.request_toggle_ers.connect(window.toggle_ers)
    window.marker_clicked.connect(telemetry_data.set_marker)
    map_window.marker_clicked.connect(telemetry_data.set_marker)
    window.view_range_changed.connect(map_window.focus_on_distance_range)
    map_window.request_reset_telemetry.connect(window.reset_zoom)
    
    update_time_label()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
