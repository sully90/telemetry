import sys
import argparse
from PyQt5 import QtWidgets

from data_manager import TelemetryData
from listener import TelemetryListener
from plotter import PlotterWindow

# Configuration
DEFAULT_UDP_PORT = 20778

def main():
    parser = argparse.ArgumentParser(description="F1 25 Real-Time Telemetry Plotter")
    parser.add_argument("--laps", type=int, default=5, help="Number of previous laps to show")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT, help="UDP Listening Port")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    
    telemetry_data = TelemetryData(max_laps=args.laps)
    
    listener = TelemetryListener(args.port)
    # Signal Connections
    listener.session_received.connect(telemetry_data.update_session)
    listener.participants_received.connect(telemetry_data.update_participants)
    listener.damage_received.connect(telemetry_data.update_damage)
    listener.status_received.connect(telemetry_data.update_status)
    listener.motion_received.connect(telemetry_data.update_motion)
    listener.lap_received.connect(telemetry_data.update_lap)
    listener.telemetry_received.connect(telemetry_data.update_telemetry)
    listener.tt_indices_received.connect(telemetry_data.update_tt_indices)
    listener.start()
    
    window = PlotterWindow(telemetry_data)
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
