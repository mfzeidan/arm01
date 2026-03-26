"""Grid-to-joint-angle calibration lookup with bilinear interpolation."""

import json
import re
from pathlib import Path

import numpy as np

CALIBRATION_FILE = Path(__file__).parent / "calibration_data.json"


def parse_coord(coord: str) -> tuple[int, int]:
    """Parse a grid coordinate like 'B3' into (col_index, row_index).

    Letters are columns (A=0, B=1, ...), numbers are rows (1=0, 2=1, ...).
    """
    match = re.match(r"^([A-Z])(\d+)$", coord.upper())
    if not match:
        raise ValueError(f"Invalid grid coordinate: {coord}")
    col = ord(match.group(1)) - ord("A")
    row = int(match.group(2)) - 1
    return col, row


class GridCalibration:
    """Lookup table mapping grid coordinates to joint angles."""

    def __init__(self, path: Path = CALIBRATION_FILE):
        self.path = path
        self.points: dict[str, list[float]] = {}
        self.metadata: dict = {}
        if path.exists():
            self.load()

    def load(self):
        with open(self.path) as f:
            data = json.load(f)
        self.metadata = data.get("metadata", {})
        self.points = data.get("points", {})

    def save(self):
        data = {"metadata": self.metadata, "points": self.points}
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def set_point(self, coord: str, joint_angles: list[float]):
        """Record joint angles for a grid coordinate."""
        self.points[coord.upper()] = joint_angles

    def get_joint_angles(self, coord: str) -> list[float]:
        """Get joint angles for a coordinate, interpolating if needed."""
        coord = coord.upper()
        if coord in self.points:
            return self.points[coord]

        # Bilinear interpolation from surrounding calibrated points
        col, row = parse_coord(coord)
        return self._interpolate(col, row)

    def _interpolate(self, col: int, row: int) -> list[float]:
        """Bilinear interpolation from the nearest calibrated points."""
        # Find all calibrated points with their (col, row) indices
        calibrated = []
        for coord_str, angles in self.points.items():
            c, r = parse_coord(coord_str)
            calibrated.append((c, r, angles))

        if len(calibrated) < 3:
            raise ValueError(
                f"Need at least 3 calibration points for interpolation, have {len(calibrated)}"
            )

        # Find the 4 nearest neighbors (or fewer at edges)
        calibrated.sort(key=lambda p: (p[0] - col) ** 2 + (p[1] - row) ** 2)
        nearest = calibrated[:4]

        # Inverse-distance weighted interpolation
        result = np.zeros(6)
        total_weight = 0.0
        for c, r, angles in nearest:
            dist = ((c - col) ** 2 + (r - row) ** 2) ** 0.5
            if dist < 0.01:
                return angles
            weight = 1.0 / dist
            result += weight * np.array(angles)
            total_weight += weight

        return (result / total_weight).tolist()

    @property
    def is_calibrated(self) -> bool:
        return len(self.points) >= 3
