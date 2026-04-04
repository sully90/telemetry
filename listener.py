import socket
import struct
import threading
from PyQt5 import QtCore

# F1 25 Packet Header (29 bytes)
HEADER_FORMAT = "<HBBBBBQfIIBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Packet IDs
PACKET_ID_SESSION = 1
PACKET_ID_LAP_DATA = 2
PACKET_ID_PARTICIPANTS = 4
PACKET_ID_CAR_TELEMETRY = 6
PACKET_ID_CAR_STATUS = 7
PACKET_ID_CAR_DAMAGE = 10

class TelemetryListener(QtCore.QObject):
    """UDP listener for raw F1 25 packets, handling multiple cars."""
    session_received = QtCore.pyqtSignal(int, int, int) # track_id, session_type, player_idx
    participants_received = QtCore.pyqtSignal(dict) # car_idx -> team_id
    damage_received = QtCore.pyqtSignal(int, list) # car_idx, tyres_wear
    status_received = QtCore.pyqtSignal(int, float, float) # car_idx, ers_store, ers_deployed
    lap_received = QtCore.pyqtSignal(int, int, float, int) # car_idx, lap_num, distance, time_ms
    telemetry_received = QtCore.pyqtSignal(int, float, int, float, float) # car_idx, speed, rpm, throttle, brake
    
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
                player_idx = header[10]

                if packet_id == PACKET_ID_SESSION:
                    # F1 25 Offsets confirmed via raw byte analysis:
                    # track_id is at offset 31, session_type is at offset 35
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
                    # CarStatusData entry is 55 bytes in F1 25
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
                            time_ms = struct.unpack("<I", data[offset+4:offset+8])[0]
                            dist = struct.unpack("<f", data[offset+20:offset+24])[0]
                            lap = struct.unpack("<B", data[offset+33:offset+34])[0]
                            self.lap_received.emit(i, lap, dist, time_ms)

                elif packet_id == PACKET_ID_CAR_TELEMETRY:
                    entry_size = 60
                    for i in range(22):
                        offset = HEADER_SIZE + (i * entry_size)
                        if len(data) >= offset + 60:
                            speed = struct.unpack("<H", data[offset:offset+2])[0]
                            throttle = struct.unpack("<f", data[offset+2:offset+6])[0]
                            brake = struct.unpack("<f", data[offset+10:offset+14])[0]
                            rpm = struct.unpack("<H", data[offset+16:offset+18])[0]
                            self.telemetry_received.emit(i, float(speed), int(rpm), throttle, brake)

            except socket.timeout:
                continue
            except Exception:
                pass

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False
