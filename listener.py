import socket
import struct
import threading
from PyQt5 import QtCore

# F1 25 Packet Header (29 bytes)
HEADER_FORMAT = "<HBBBBBQfIIBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Packet IDs
PACKET_ID_MOTION = 0
PACKET_ID_SESSION = 1
PACKET_ID_LAP_DATA = 2
PACKET_ID_PARTICIPANTS = 4
PACKET_ID_CAR_TELEMETRY = 6
PACKET_ID_CAR_STATUS = 7
PACKET_ID_CAR_DAMAGE = 10

class TelemetryListener(QtCore.QObject):
    """UDP listener for raw F1 25 packets, handling multiple cars and ghosts."""
    session_received = QtCore.pyqtSignal(int, int, int) 
    participants_received = QtCore.pyqtSignal(dict) 
    damage_received = QtCore.pyqtSignal(int, list) 
    status_received = QtCore.pyqtSignal(int, float, float) 
    lap_received = QtCore.pyqtSignal(int, int, float, int, float, int) # car_idx, lap, dist, time_ms, session_time, frame_id
    telemetry_received = QtCore.pyqtSignal(int, float, int, float, float, float, float, int) # car_idx, speed, rpm, throttle, brake, steer, session_time, frame_id
    motion_received = QtCore.pyqtSignal(int, float, float, float, float, float, float, float, int) # idx, x, y, z, vx, vy, vz, session_time, frame_id
    tt_indices_received = QtCore.pyqtSignal(int, int) 
    
    def __init__(self, port):
        super().__init__()
        self.port = port
        self._running = True

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', self.port))
        sock.settimeout(1.0)
        print(f"Listening for RAW F1 25 telemetry on port {self.port}...")

        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                if len(data) < HEADER_SIZE:
                    continue

                header = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
                packet_id = header[5]
                session_time = header[7]
                frame_id = header[8]
                player_idx = header[10]

                if packet_id == PACKET_ID_MOTION:
                    entry_size = 60
                    for i in range(22):
                        offset = HEADER_SIZE + (i * entry_size)
                        if len(data) >= offset + 24:
                            x = struct.unpack("<f", data[offset:offset+4])[0]
                            y = struct.unpack("<f", data[offset+4:offset+8])[0]
                            z = struct.unpack("<f", data[offset+8:offset+12])[0]
                            vx = struct.unpack("<f", data[offset+12:offset+16])[0]
                            vy = struct.unpack("<f", data[offset+16:offset+20])[0]
                            vz = struct.unpack("<f", data[offset+20:offset+24])[0]
                            self.motion_received.emit(i, x, y, z, vx, vy, vz, session_time, frame_id)

                elif packet_id == PACKET_ID_SESSION:
                    if len(data) >= 36:
                        track_id = struct.unpack("<b", data[31:32])[0]
                        session_type = struct.unpack("<B", data[35:36])[0]
                        self.session_received.emit(track_id, session_type, player_idx)

                elif packet_id == PACKET_ID_PARTICIPANTS:
                    entry_size = 56 
                    participants = {}
                    for i in range(22):
                        offset = HEADER_SIZE + (i * entry_size)
                        if len(data) >= offset + 4:
                            team_id = struct.unpack("<B", data[offset+3:offset+4])[0]
                            participants[i] = team_id
                    self.participants_received.emit(participants)

                elif packet_id == PACKET_ID_CAR_STATUS:
                    entry_size = 55
                    for i in range(22):
                        offset = HEADER_SIZE + (i * entry_size)
                        if len(data) >= offset + 46:
                            ers_store = struct.unpack("<f", data[offset+29:offset+33])[0]
                            ers_deployed = struct.unpack("<f", data[offset+42:offset+46])[0]
                            self.status_received.emit(i, ers_store, ers_deployed)

                elif packet_id == PACKET_ID_CAR_DAMAGE:
                    entry_size = 46
                    for i in range(22):
                        offset = HEADER_SIZE + (i * entry_size)
                        if len(data) >= offset + 16:
                            tyres_wear = list(struct.unpack("<ffff", data[offset:offset+16]))
                            self.damage_received.emit(i, tyres_wear)

                elif packet_id == PACKET_ID_LAP_DATA:
                    entry_size = 57 
                    for i in range(22):
                        offset = HEADER_SIZE + (i * entry_size)
                        if len(data) >= offset + 57:
                            # F1 25 LapData: dist=20, lap=33
                            time_ms = struct.unpack("<I", data[offset+4:offset+8])[0]
                            dist = struct.unpack("<f", data[offset+20:offset+24])[0]
                            lap = struct.unpack("<B", data[offset+33:offset+34])[0]
                            self.lap_received.emit(i, lap, dist, time_ms, session_time, frame_id)
                    
                    if len(data) >= 1285:
                        pb_idx = struct.unpack("<B", data[1283:1284])[0]
                        rival_idx = struct.unpack("<B", data[1284:1285])[0]
                        self.tt_indices_received.emit(pb_idx, rival_idx)

                elif packet_id == PACKET_ID_CAR_TELEMETRY:
                    entry_size = 60
                    for i in range(22):
                        offset = HEADER_SIZE + (i * entry_size)
                        if len(data) >= offset + 60:
                            # F1 25 Telemetry: speed=0, throttle=2, steer=6, brake=10, rpm=16
                            speed = struct.unpack("<H", data[offset:offset+2])[0]
                            throttle = struct.unpack("<f", data[offset+2:offset+6])[0]
                            steer = struct.unpack("<f", data[offset+6:offset+10])[0]
                            brake = struct.unpack("<f", data[offset+10:offset+14])[0]
                            rpm = struct.unpack("<H", data[offset+16:offset+18])[0]
                            self.telemetry_received.emit(i, float(speed), int(rpm), throttle, brake, steer, session_time, frame_id)

            except socket.timeout:
                continue
            except Exception:
                pass

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False
