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
        self.df = df
        self.metadata = metadata
        self.current_idx = 0
        self.is_playing = False
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._on_tick)
        # We'll aim for ~60fps playback if possible, but the data frequency might vary
        self.timer.start(16) 
        
        self._populate_full_session()

    def _populate_full_session(self):
        """Pre-populate TelemetryData with all lap data for plotting."""
        with self.telemetry_data.lock:
            # Set track name
            self.telemetry_data.track_name = self.metadata.get("track", "Unknown")
            
            # Group by car_idx to avoid mixing data from different cars
            for car_idx, car_df in self.df.groupby('car_idx'):
                car_idx = int(car_idx)
                if car_idx >= 22: continue
                
                laps = sorted(car_df['lap'].unique())
                for i, lap_num in enumerate(laps):
                    lap_df = car_df[car_df['lap'] == lap_num]
                    
                    # Last lap in the file for this car is considered the "current" active one
                    if i == len(laps) - 1:
                        target = self.telemetry_data.all_cars_data[car_idx]
                    else:
                        # Add to history
                        hist_data = {
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
                        self.telemetry_data.car_histories[car_idx].append(hist_data)
                        continue

                    # Populate the active lap data
                    target["distance"] = lap_df['distance'].tolist()
                    target["speed"] = lap_df['speed'].tolist()
                    target["rpm"] = lap_df['rpm'].tolist()
                    target["throttle"] = lap_df['throttle'].tolist()
                    target["brake"] = lap_df['brake'].tolist()
                    target["steer"] = lap_df['steer'].tolist()
                    target["time"] = lap_df['time'].tolist()
                    target["pos_x"] = lap_df['pos_x'].tolist()
                    target["pos_z"] = lap_df['pos_z'].tolist()
                    
                    if car_idx == self.telemetry_data.player_idx:
                        self.telemetry_data.current_lap_num = lap_num

    def _on_tick(self):
        if not self.is_playing:
            return
            
        if self.current_idx < len(self.df):
            # Process all rows for the current timestamp (to update all cars at once)
            current_time = self.df.iloc[self.current_idx]['time']
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
        if car_idx >= 22:
            return
            
        with self.telemetry_data.lock:
            latch = self.telemetry_data.car_latches[car_idx]
            latch["speed_mph"] = row["speed"]
            latch["rpm"] = row["rpm"]
            latch["throttle"] = row["throttle"]
            latch["brake"] = row["brake"]
            latch["steer"] = row["steer"]
            latch["world_x"] = row["pos_x"]
            latch["world_z"] = row["pos_z"]
            latch["last_lap"] = row["lap"]
            
            # Update the global marker if this is the player car
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
