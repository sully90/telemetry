import threading
import json
import os
from datetime import datetime
from collections import deque

TRACK_MAP = {
    0: "Melbourne", 1: "Paul Ricard", 2: "Shanghai", 3: "Sakhir",
    4: "Catalunya", 5: "Monaco", 6: "Montreal", 7: "Silverstone",
    8: "Hockenheim", 9: "Hungaroring", 10: "Spa", 11: "Monza",
    12: "Singapore", 13: "Suzuka", 14: "Abu Dhabi", 15: "Texas",
    16: "Shanghai", 17: "Interlagos", 18: "Yas Marina", 19: "Austin",
    20: "Mexico City", 21: "Spielberg", 22: "Sakhir Short", 
    23: "Silverstone Short", 24: "Texas Short", 25: "Suzuka Short",
    26: "Hanoi", 27: "Zandvoort", 28: "Imola", 29: "Portimão",
    30: "Jeddah", 31: "Miami", 32: "Las Vegas", 33: "Losail"
}

TEAM_COLORS = {
    0: (39, 244, 210),   # Mercedes
    1: (232, 0, 32),     # Ferrari
    2: (54, 113, 198),   # Red Bull
    3: (100, 196, 255),  # Williams
    4: (34, 153, 113),   # Aston Martin
    5: (0, 147, 204),    # Alpine
    6: (102, 146, 255),  # RB
    7: (182, 186, 189),  # Haas
    8: (255, 128, 0),    # McLaren
    9: (82, 226, 82),    # Sauber
    41: (150, 150, 150), # Generic
    104: (255, 255, 255),# Custom
}

SESSION_RACE = [15, 16, 17]
SESSION_TIME_TRIAL = [18]

class TelemetryData:
    """Manages telemetry data for multiple laps and multiple cars."""
    def __init__(self, max_laps=5):
        self.max_laps = max_laps
        self.laps = deque(maxlen=max_laps)
        
        self.player_idx = 0
        self.current_lap_data = self._new_lap_dict()
        self.best_lap_data = None
        self.best_lap_time = float('inf')
        self.current_lap_num = -1
        
        self.all_cars_data = {i: self._new_lap_dict() for i in range(22)}
        self.all_cars_lap_nums = [-1] * 22
        self.all_cars_team_ids = [41] * 22
        
        self.session_type = 0
        self.track_name = "F1 25 Session"
        self.first_data_received = False
        
        # Recording state
        self.is_recording = False
        self.recording_log = []
        self.recording_filename = ""
        
        self.lock = threading.Lock()

    def _new_lap_dict(self):
        return {
            "distance": [], "speed": [], "rpm": [], "throttle": [], 
            "brake": [], "time": [], "tyre_wear": [], "ers_store": []
        }

    def toggle_recording(self):
        with self.lock:
            if not self.is_recording:
                # Start recording
                self.is_recording = True
                # AI-friendly metadata header
                self.recording_log = [{
                    "metadata": {
                        "description": "F1 25 Telemetry Data for AI Coaching",
                        "game": "F1 25",
                        "track": self.track_name,
                        "session_type": self.session_type,
                        "timestamp": datetime.now().isoformat(),
                        "units": {
                            "distance": "meters",
                            "speed": "km/h",
                            "throttle": "percentage (0-100)",
                            "brake": "percentage (0-100)",
                            "time": "seconds from start of lap"
                        },
                        "schema": {
                            "car_idx": "0-21 (0 is usually player in single player)",
                            "lap": "Current lap number",
                            "distance": "Distance around the track",
                            "speed": "Current vehicle speed",
                            "rpm": "Engine RPM",
                            "throttle": "Accelerator input",
                            "brake": "Brake input",
                            "time": "Time into the current lap"
                        }
                    }
                }]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                clean_track = self.track_name.replace(" ", "_")
                self.recording_filename = f"F125_{clean_track}_{timestamp}.json"
                print(f"REC: Started recording to {self.recording_filename}")
            else:
                # Stop and save
                self.is_recording = False
                if self.recording_log:
                    # Create directory if missing
                    if not os.path.exists("recordings"): os.makedirs("recordings")
                    filepath = os.path.join("recordings", self.recording_filename)
                    with open(filepath, 'w') as f:
                        json.dump(self.recording_log, f)
                    print(f"REC: Saved {len(self.recording_log)} samples to {filepath}")
                self.recording_log = []

    def update_session(self, track_id, session_type, player_idx):
        with self.lock:
            self.player_idx = player_idx
            new_track = TRACK_MAP.get(track_id, f"Track {track_id}")
            if new_track != self.track_name or session_type != self.session_type:
                self.track_name = new_track
                self.session_type = session_type
                # ... reset logic ...
                self.laps.clear()
                self.best_lap_data = None
                self.best_lap_time = float('inf')
                self.current_lap_data = self._new_lap_dict()
                self.all_cars_data = {i: self._new_lap_dict() for i in range(22)}
                self.all_cars_lap_nums = [-1] * 22

    def update_participants(self, participants):
        with self.lock:
            for i, team_id in participants.items():
                if i < 22: self.all_cars_team_ids[i] = team_id

    def update_status(self, car_idx, ers_store, ers_deployed):
        with self.lock:
            car_data = self.all_cars_data.get(car_idx)
            if car_data and len(car_data["distance"]) > len(car_data["ers_store"]):
                ers_pct = (ers_store / 4000000.0) * 100.0
                car_data["ers_store"].append(ers_pct)

    def update_damage(self, car_idx, tyres_wear):
        with self.lock:
            car_data = self.all_cars_data.get(car_idx)
            if car_data and len(car_data["distance"]) > len(car_data["tyre_wear"]):
                max_wear = max(tyres_wear)
                car_data["tyre_wear"].append(max_wear)

    def update_lap(self, car_idx, lap_num, distance, time_ms):
        if car_idx == self.player_idx and not self.first_data_received:
            self.first_data_received = True
            
        with self.lock:
            car_data = self.all_cars_data.get(car_idx)
            if not car_data: return

            last_lap = self.all_cars_lap_nums[car_idx]
            if last_lap != -1 and lap_num > last_lap:
                if car_idx == self.player_idx:
                    lap_time = car_data["time"][-1] if car_data["time"] else float('inf')
                    if len(car_data["distance"]) > 100:
                        if lap_time < self.best_lap_time:
                            self.best_lap_time = lap_time
                            self.best_lap_data = car_data.copy()
                        self.laps.append(car_data.copy())
                    self.current_lap_data = self._new_lap_dict()
                self.all_cars_data[car_idx] = self._new_lap_dict()
                car_data = self.all_cars_data[car_idx]

            self.all_cars_lap_nums[car_idx] = lap_num
            car_data["distance"].append(distance)
            car_data["time"].append(time_ms / 1000.0)
            if car_idx == self.player_idx:
                self.current_lap_num = lap_num
                self.current_lap_data = car_data

    def update_telemetry(self, car_idx, speed, rpm, throttle, brake):
        with self.lock:
            car_data = self.all_cars_data.get(car_idx)
            if car_data and len(car_data["distance"]) > len(car_data["speed"]):
                car_data["speed"].append(speed)
                car_data["rpm"].append(rpm)
                car_data["throttle"].append(throttle * 100.0)
                car_data["brake"].append(brake * 100.0)
                
                # Record sample for ANY car if we are recording
                if self.is_recording:
                    sample = {
                        "car_idx": car_idx, # Identify which car this is
                        "lap": self.all_cars_lap_nums[car_idx],
                        "distance": car_data["distance"][-1],
                        "speed": speed,
                        "rpm": rpm,
                        "throttle": throttle * 100.0,
                        "brake": brake * 100.0,
                        "time": car_data["time"][-1]
                    }
                    self.recording_log.append(sample)
