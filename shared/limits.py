"""Ground-side limits from the organiser workbook (data/raw/challenge2/challenge-2-operational-constraints.xlsx).

The workbook wins over CLAUDE.md where they differ (confirmed with the user). All
values are SYNTHETIC planning limits per the organisers and must be labelled so.
"""
from dataclasses import dataclass
from pathlib import Path

import openpyxl

WORKBOOK_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "raw" / "challenge2" / "challenge-2-operational-constraints.xlsx"
)

# fuel_and_crew sheet: "Ground crew shift | 8 hours; overtime costs 1.5x after that"
GROUND_CREW_SHIFT_MIN = 8 * 60
OVERTIME_MULTIPLIER = 1.5
# fuel_and_crew sheet: "Gate change notice | At least 20 minutes before arrival"
GATE_CHANGE_NOTICE_MIN = 20
# ASSUMPTION (not in workbook): longest a landed aircraft may wait for its gate.
MAX_GATE_WAIT_MIN = 30
# ASSUMPTION (not in workbook): walking minutes for connecting pax between gates.
WALK_SAME_TERMINAL_MIN = 5
WALK_OTHER_TERMINAL_MIN = 15


@dataclass(frozen=True)
class AirportLimits:
    iata: str
    size_class: str
    gates: int
    min_turnaround_min: int
    spare_gates: int
    source: str


# Loads one airport's gate/turnaround limits from the workbook's airport_capacity sheet.
# Args: iata - airport code, e.g. "DFW"; path - workbook path.
# Returns: AirportLimits for that airport.
# Raises: KeyError if the airport is not in the sheet.
def load_airport_limits(iata: str, path: Path = WORKBOOK_PATH) -> AirportLimits:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        header = None
        for row in wb["airport_capacity"].iter_rows(values_only=True):
            if row and row[0] == "IATA_CODE":
                header = {name: i for i, name in enumerate(row)}
            elif header and row[0] == iata:
                return AirportLimits(
                    iata=iata,
                    size_class=row[header["size_class"]],
                    gates=int(row[header["gates"]]),
                    min_turnaround_min=int(row[header["min_turnaround_min"]]),
                    spare_gates=int(row[header["spare_gates_at_any_time"]]),
                    source="organiser workbook, airport_capacity (SYNTHETIC)",
                )
    finally:
        wb.close()
    raise KeyError(f"{iata} not in airport_capacity")
