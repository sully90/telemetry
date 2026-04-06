import os
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

class TelemetryRecorder:
    def __init__(self, output_dir: str = "recordings"):
        self.output_dir = output_dir
        self.is_recording = False
        self.recording_log: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def start_recording(self, track_name: str, units: Dict[str, str]):
        self.is_recording = True
        self.recording_log = []
        self.metadata = {
            "game": "F1 25",
            "track": track_name,
            "timestamp": datetime.now().isoformat(),
            "units": units
        }
        print(f"REC: Started recording for track: {track_name}")

    def add_sample(self, sample: Dict[str, Any]):
        if self.is_recording:
            self.recording_log.append(sample)

    def stop_recording(self) -> str:
        if not self.is_recording:
            return ""

        self.is_recording = False
        if not self.recording_log:
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        track_name = self.metadata.get("track", "Unknown").replace(" ", "_")
        filename = f"F125_{track_name}_{timestamp}.parquet"
        filepath = os.path.join(self.output_dir, filename)

        df = pd.DataFrame(self.recording_log)
        
        # Convert to pyarrow table to add custom metadata
        import pyarrow as pa
        import pyarrow.parquet as pq
        import json

        table = pa.Table.from_pandas(df)
        
        # Add metadata as a JSON string in the 'metadata' key
        existing_metadata = table.schema.metadata or {}
        new_metadata = {
            **existing_metadata,
            b"telemetry_metadata": json.dumps(self.metadata).encode('utf-8')
        }
        table = table.replace_schema_metadata(new_metadata)
        
        pq.write_table(table, filepath)
        print(f"REC: Saved recording to {filepath} ({len(df)} samples)")
        
        self.recording_log = []
        return filepath

    def read_recording(self, filepath: str) -> pd.DataFrame:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Recording file not found: {filepath}")
        return pd.read_parquet(filepath, engine='pyarrow')
