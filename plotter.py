import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
from data_manager import TEAM_COLORS, SESSION_RACE, SESSION_TIME_TRIAL

class PlotterWindow(QtWidgets.QMainWindow):
    def __init__(self, telemetry_data):
        super().__init__()
        self.telemetry_data = telemetry_data
        self.setWindowTitle("F1 25 Real-Time Telemetry Plotter")
        self.resize(1200, 1000)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)
        self.win = pg.GraphicsLayoutWidget(show=True)
        layout.addWidget(self.win)

        # Create subplots
        self.p_speed = self.win.addPlot(title="Speed (mph)")
        self.win.nextRow()
        self.p_delta = self.win.addPlot(title="Time Delta vs Reference (seconds)")
        self.win.nextRow()
        self.p_throttle = self.win.addPlot(title="Pedals (Throttle/Brake %)")
        self.win.nextRow()
        self.p_tyre = self.win.addPlot(title="Max Tyre Wear (%)")
        self.win.nextRow()
        self.p_ers = self.win.addPlot(title="ERS Battery Store (%)")
        self.p_ers.setYRange(0, 100)

        # Link X-axes
        self.p_delta.setXLink(self.p_speed); self.p_throttle.setXLink(self.p_speed)
        self.p_tyre.setXLink(self.p_speed); self.p_ers.setXLink(self.p_speed)

        # Visibility
        self.show_tyre_wear = False; self.show_ers = False
        self.p_tyre.hide(); self.p_ers.hide()

        # Curves
        self.history_speed_curves = []; self.history_throttle_curves = []
        self.history_brake_curves = []; self.history_tyre_curves = []; self.history_ers_curves = []

        # Opponents / Race Mode
        self.opp_speed_curves = {i: self.p_speed.plot(pen=pg.mkPen((100, 100, 100, 50), width=1)) for i in range(22)}
        self.opp_throttle_curves = {i: self.p_throttle.plot(pen=pg.mkPen((0, 150, 0, 50), width=1)) for i in range(22)}
        self.opp_brake_curves = {i: self.p_throttle.plot(pen=pg.mkPen((150, 0, 0, 50), width=1)) for i in range(22)}
        self.opp_tyre_curves = {i: self.p_tyre.plot(pen=pg.mkPen((150, 150, 150, 50), width=1)) for i in range(22)}
        self.opp_ers_curves = {i: self.p_ers.plot(pen=pg.mkPen((100, 100, 200, 50), width=1)) for i in range(22)}
        for d in [self.opp_speed_curves, self.opp_throttle_curves, self.opp_brake_curves, self.opp_tyre_curves, self.opp_ers_curves]:
            for c in d.values(): c.setZValue(2)

        # Best Lap (Cyan Dash)
        self.best_speed_curve = self.p_speed.plot(pen=pg.mkPen('c', width=1, style=QtCore.Qt.DashLine)); self.best_speed_curve.setZValue(50)
        self.best_throttle_curve = self.p_throttle.plot(pen=pg.mkPen('c', width=1, style=QtCore.Qt.DashLine)); self.best_throttle_curve.setZValue(50)
        self.best_brake_curve = self.p_throttle.plot(pen=pg.mkPen('c', width=1, style=QtCore.Qt.DashLine)); self.best_brake_curve.setZValue(50)
        self.best_tyre_curve = self.p_tyre.plot(pen=pg.mkPen('c', width=1, style=QtCore.Qt.DashLine)); self.best_tyre_curve.setZValue(50)
        self.best_ers_curve = self.p_ers.plot(pen=pg.mkPen('c', width=1, style=QtCore.Qt.DashLine)); self.best_ers_curve.setZValue(50)

        # Rival Ghost (Purple Dash) - New
        self.rival_speed_curve = self.p_speed.plot(pen=pg.mkPen((200, 0, 255), width=1, style=QtCore.Qt.DashLine)); self.rival_speed_curve.setZValue(51)
        self.rival_throttle_curve = self.p_throttle.plot(pen=pg.mkPen((200, 0, 255), width=1, style=QtCore.Qt.DashLine)); self.rival_throttle_curve.setZValue(51)
        self.rival_brake_curve = self.p_throttle.plot(pen=pg.mkPen((200, 0, 255), width=1, style=QtCore.Qt.DashLine)); self.rival_brake_curve.setZValue(51)

        # Delta
        self.delta_curve = self.p_delta.plot(pen=pg.mkPen('y', width=2))
        self.p_delta.addLine(y=0, pen=pg.mkPen('w', style=QtCore.Qt.DotLine))

        # Current Lap (Solid)
        self.curr_speed_curve = self.p_speed.plot(pen=pg.mkPen('w', width=3)); self.curr_speed_curve.setZValue(100)
        self.curr_throttle_curve = self.p_throttle.plot(pen=pg.mkPen('g', width=3)); self.curr_throttle_curve.setZValue(100)
        self.curr_brake_curve = self.p_throttle.plot(pen=pg.mkPen('r', width=3)); self.curr_brake_curve.setZValue(100)
        self.curr_tyre_curve = self.p_tyre.plot(pen=pg.mkPen('m', width=3)); self.curr_tyre_curve.setZValue(100)
        self.curr_ers_curve = self.p_ers.plot(pen=pg.mkPen('b', width=3)); self.curr_ers_curve.setZValue(100)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(50)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_T:
            self.show_tyre_wear = not self.show_tyre_wear
            if self.show_tyre_wear: self.p_tyre.show()
            else: self.p_tyre.hide()
        elif event.key() == QtCore.Qt.Key_E:
            self.show_ers = not self.show_ers
            if self.show_ers: self.p_ers.show()
            else: self.p_ers.hide()
        elif event.key() == QtCore.Qt.Key_R:
            self.telemetry_data.toggle_recording()
        super().keyPressEvent(event)

    def update_plots(self):
        with self.telemetry_data.lock:
            player_idx = self.telemetry_data.player_idx
            rival_idx = self.telemetry_data.rival_car_idx
            session_type = self.telemetry_data.session_type
            is_race = session_type in SESSION_RACE
            is_tt = session_type in SESSION_TIME_TRIAL
            is_recording = self.telemetry_data.is_recording
            
            track_name = self.telemetry_data.track_name
            mode_str = "RACE MODE" if is_race else "TIME TRIAL" if is_tt else "PRACTICE"
            rec_str = " [RECORDING]" if is_recording else ""
            self.setWindowTitle(f"F1 25 Telemetry - {track_name} [{mode_str}]{rec_str} (T:Tyre, E:Energy, R:Record)")

            # Update Opponents / Rival Ghost
            for i in range(22):
                car_data = self.telemetry_data.all_cars_data[i]
                if i == player_idx or not car_data["distance"]:
                    self.opp_speed_curves[i].hide(); self.opp_throttle_curves[i].hide()
                    self.opp_brake_curves[i].hide(); self.opp_tyre_curves[i].hide(); self.opp_ers_curves[i].hide()
                    if i == rival_idx: 
                        self.rival_speed_curve.hide(); self.rival_throttle_curve.hide(); self.rival_brake_curve.hide()
                    continue
                
                # Special handling for Rival Ghost in TT
                if is_tt and i == rival_idx:
                    n = min(len(car_data["distance"]), len(car_data["speed"]))
                    self.rival_speed_curve.setData(car_data["distance"][:n], car_data["speed"][:n]); self.rival_speed_curve.show()
                    self.rival_throttle_curve.setData(car_data["distance"][:n], car_data["throttle"][:n]); self.rival_throttle_curve.show()
                    self.rival_brake_curve.setData(car_data["distance"][:n], car_data["brake"][:n]); self.rival_brake_curve.show()
                    self.opp_speed_curves[i].hide() # Don't show faint opponent curve for rival
                elif is_race:
                    team_id = self.telemetry_data.all_cars_team_ids[i]
                    color = TEAM_COLORS.get(team_id, (150, 150, 150))
                    n = min(len(car_data["distance"]), len(car_data["speed"]), len(car_data["throttle"]), len(car_data["brake"]))
                    self.opp_speed_curves[i].setPen(pg.mkPen((*color, 80), width=1)); self.opp_speed_curves[i].setData(car_data["distance"][:n], car_data["speed"][:n]); self.opp_speed_curves[i].show()
                    self.opp_throttle_curves[i].setPen(pg.mkPen((*color, 80), width=1)); self.opp_throttle_curves[i].setData(car_data["distance"][:n], car_data["throttle"][:n]); self.opp_throttle_curves[i].show()
                    self.opp_brake_curves[i].setPen(pg.mkPen((*color, 80), width=1)); self.opp_brake_curves[i].setData(car_data["distance"][:n], car_data["brake"][:n]); self.opp_brake_curves[i].show()
                    if self.show_tyre_wear and car_data["tyre_wear"]:
                        nt = min(len(car_data["distance"]), len(car_data["tyre_wear"]))
                        self.opp_tyre_curves[i].setPen(pg.mkPen((*color, 80), width=1)); self.opp_tyre_curves[i].setData(car_data["distance"][:nt], car_data["tyre_wear"][:nt]); self.opp_tyre_curves[i].show()
                    if self.show_ers and car_data["ers_store"]:
                        ne = min(len(car_data["distance"]), len(car_data["ers_store"]))
                        self.opp_ers_curves[i].setPen(pg.mkPen((*color, 80), width=1)); self.opp_ers_curves[i].setData(car_data["distance"][:ne], car_data["ers_store"][:ne]); self.opp_ers_curves[i].show()
                else:
                    self.opp_speed_curves[i].hide()

            # Update Session Best (Cyan)
            best = self.telemetry_data.best_lap_data
            if best and best["distance"] and (is_tt or not is_race):
                n = min(len(best["distance"]), len(best["speed"]))
                self.best_speed_curve.setData(best["distance"][:n], best["speed"][:n]); self.best_speed_curve.show()
                self.best_throttle_curve.setData(best["distance"][:n], best["throttle"][:n]); self.best_throttle_curve.show()
                self.best_brake_curve.setData(best["distance"][:n], best["brake"][:n]); self.best_brake_curve.show()
                if self.show_tyre_wear and best["tyre_wear"]:
                    nt = min(len(best["distance"]), len(best["tyre_wear"]))
                    self.best_tyre_curve.setData(best["distance"][:nt], best["tyre_wear"][:nt]); self.best_tyre_curve.show()
                if self.show_ers and best["ers_store"]:
                    ne = min(len(best["distance"]), len(best["ers_store"]))
                    self.best_ers_curve.setData(best["distance"][:ne], best["ers_store"][:ne]); self.best_ers_curve.show()
            else:
                self.best_speed_curve.hide(); self.best_tyre_curve.hide(); self.best_ers_curve.hide()

            # Update Current Lap & Delta
            current = self.telemetry_data.current_lap_data
            if current["distance"] and current["speed"]:
                n = min(len(current["distance"]), len(current["speed"]), len(current["throttle"]), len(current["brake"]), len(current["time"]))
                curr_dist = np.array(current["distance"][:n]); curr_time = np.array(current["time"][:n])
                self.curr_speed_curve.setData(curr_dist, current["speed"][:n])
                self.curr_throttle_curve.setData(curr_dist, current["throttle"][:n])
                self.curr_brake_curve.setData(curr_dist, current["brake"][:n])
                if self.show_tyre_wear and current["tyre_wear"]:
                    nt = min(len(current["distance"]), len(current["tyre_wear"])); self.curr_tyre_curve.setData(current["distance"][:nt], current["tyre_wear"][:nt]); self.curr_tyre_curve.show()
                if self.show_ers and current["ers_store"]:
                    ne = min(len(current["distance"]), len(current["ers_store"])); self.curr_ers_curve.setData(current["distance"][:ne], current["ers_store"][:ne]); self.curr_ers_curve.show()
                
                # Delta logic: Prefer Rival Ghost if in TT and available, otherwise Session Best
                ref_lap = None
                if is_tt and rival_idx != 255: ref_lap = self.telemetry_data.all_cars_data[rival_idx]
                elif is_tt or not is_race: ref_lap = best
                
                if ref_lap and len(ref_lap["distance"]) > 10:
                    ref_time = np.array(ref_lap["time"])
                    ref_time_rel = ref_time - ref_time[0]
                    curr_time_rel = curr_time - curr_time[0]
                    
                    best_time_interp = np.interp(curr_dist, ref_lap["distance"], ref_time_rel)
                    delta = curr_time_rel - best_time_interp
                    ref_name = "Rival" if ref_lap == self.telemetry_data.all_cars_data.get(rival_idx) else "Best"
                    self.p_delta.setTitle(f"Time Delta vs {ref_name} (seconds)")
                    self.delta_curve.setData(curr_dist, delta); self.p_delta.show()
                else: self.p_delta.hide()

            # Update Player History
            laps = list(self.telemetry_data.laps)
            num_history = len(laps)
            while len(self.history_speed_curves) < num_history:
                s = self.p_speed.plot(); s.setZValue(1); self.history_speed_curves.append(s)
                t = self.p_throttle.plot(); t.setZValue(1); self.history_throttle_curves.append(t)
                b = self.p_throttle.plot(); b.setZValue(1); self.history_brake_curves.append(b)
                y = self.p_tyre.plot(); y.setZValue(1); self.history_tyre_curves.append(y)
                e = self.p_ers.plot(); e.setZValue(1); self.history_ers_curves.append(e)
            for i, lap in enumerate(laps):
                age = num_history - i; alpha = int(max(20, 255 * (1.0 - (age / (self.telemetry_data.max_laps + 1)))))
                n = min(len(lap["distance"]), len(lap["speed"]), len(lap["throttle"]), len(lap["brake"]))
                self.history_speed_curves[i].setData(lap["distance"][:n], lap["speed"][:n]); self.history_speed_curves[i].setPen(pg.mkPen((200, 200, 200, alpha), width=1)); self.history_speed_curves[i].show()
                self.history_throttle_curves[i].setData(lap["distance"][:n], lap["throttle"][:n]); self.history_throttle_curves[i].setPen(pg.mkPen((0, 255, 0, alpha), width=1)); self.history_throttle_curves[i].show()
                self.history_brake_curves[i].setData(lap["distance"][:n], lap["brake"][:n]); self.history_brake_curves[i].setPen(pg.mkPen((255, 0, 0, alpha), width=1)); self.history_brake_curves[i].show()
                if self.show_tyre_wear and lap["tyre_wear"]:
                    nt = min(len(lap["distance"]), len(lap["tyre_wear"])); self.history_tyre_curves[i].setData(lap["distance"][:nt], lap["tyre_wear"][:nt]); self.history_tyre_curves[i].setPen(pg.mkPen((255, 0, 255, alpha), width=1)); self.history_tyre_curves[i].show()
                if self.show_ers and lap["ers_store"]:
                    ne = min(len(lap["distance"]), len(lap["ers_store"])); self.history_ers_curves[i].setData(lap["distance"][:ne], lap["ers_store"][:ne]); self.history_ers_curves[i].setPen(pg.mkPen((0, 0, 255, alpha), width=1)); self.history_ers_curves[i].show()
