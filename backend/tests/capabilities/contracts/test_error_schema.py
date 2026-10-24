"""A failed action does not owe the fields of its success payload."""

from app.capabilities.types import ActionDescriptor
from app.harness.normalizer import ResultNormalizer


def test_declared_success_fields_do_not_replace_failure_category():
    descriptor = ActionDescriptor(
        name="contract",
        description="success and failure have different envelopes",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"statistics": {"type": "object"}},
            "required": ["statistics"],
        },
    )
    result = ResultNormalizer().normalize(
        {"success": False, "error_type": "internal", "error": "private sentinel"},
        descriptor=descriptor,
        run_id="run",
        decision_id="decision",
        invocation_id="invocation",
        trace_id="trace",
    )
    assert result.status == "failed"
    assert result.error_code == "internal"
    assert "private sentinel" not in str(result.safe_output)
