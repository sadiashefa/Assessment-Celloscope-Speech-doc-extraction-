from pydantic import BaseModel


class LabMeta(BaseModel):
    patient_name: str
    age: str
    sex: str
    report_date: str
    lab_name: str
    reference_no: str


class LabResult(BaseModel):
    test_name: str
    value: float
    comparator: str | None
    unit: str
    reference_range: str
    flag: str | None
    raw_line: str  # verbatim — requirement 5, never dropped


class ExtractResponse(BaseModel):
    meta: LabMeta
    results: list[LabResult]
