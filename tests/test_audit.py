from anonymizer.audit import build_audit_report
from anonymizer.copybook.model import Field
from anonymizer.pipeline import FieldPlan, RunResult

NAME = Field(name="CUST-NAME", level=5, offset=0, length=10)
TYPE = Field(name="REC-TYPE", level=5, offset=10, length=1)


def test_report_contents():
    result = RunResult(records_written=100, real_records=40,
                       synthetic_records=60, sample=[])
    plans = [FieldPlan(field=NAME, rule="person_name", enabled=True),
             FieldPlan(field=TYPE, rule="keep", enabled=False)]
    report = build_audit_report(result, plans, seed="topsecret",
                                input_name="in.dat", output_name="out.dat")
    assert "CUST-NAME" in report and "Fake person name" in report
    assert "REC-TYPE" in report and "not masked" in report
    assert "100" in report and "60" in report
    assert "topsecret" not in report            # seed never leaks
    assert "Seed fingerprint" in report
