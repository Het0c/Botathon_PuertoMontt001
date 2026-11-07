import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas import BukRecord


MOTOR_ROOT = Path(__file__).parents[1] / "motor-calculo"


def test_existing_blue_prism_contract_is_accepted() -> None:
    payload = json.loads((MOTOR_ROOT / "data" / "persona_137732.json").read_text(encoding="utf-8"))

    record = BukRecord.model_validate(payload)

    assert record.source_record_id == "BUK-137732-2026"
    assert record.reg_sic == "D - SIC"
    assert record.contrato.weekly_hours == 40
    assert record.meses["02"].vacation_days == 15
    assert record.meses["03"].sick_leave_days == pytest.approx(1.25)


def test_backend_rejects_rows_not_marked_for_sic() -> None:
    payload = json.loads((MOTOR_ROOT / "data" / "persona_137732.json").read_text(encoding="utf-8"))
    payload["regSic"] = "NO APLICA"

    with pytest.raises(ValidationError):
        BukRecord.model_validate(payload)
