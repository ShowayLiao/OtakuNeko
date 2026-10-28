"""Final-result acceptance independent of successful tool execution."""

import pytest

from app.evaluation.scoring import score_deterministic
from app.evaluation.types import EvalCase, ExecutionResult


def case_with_answer(answer):
    return EvalCase.model_validate(
        {
            "id": "final-result",
            "category": "routing",
            "input_messages": [{"role": "user", "content": "Return the final result."}],
            "user_fixture": {"user_id": 950},
            "assertions": {},
            "fixtures": {"events": [{"type": "message_chunk", "content": "unused"}]},
            "deterministic": {"final_answer": answer},
        }
    )


def score_answer(answer, text):
    score = score_deterministic(
        case_with_answer(answer), ExecutionResult(route="chat", text=text)
    )
    assert score is not None
    return score


def test_completed_run_with_wrong_final_result_fails():
    score = score_answer(
        {"expected_json": {"count": 0, "title": "Frieren"}},
        '{"count":1,"title":"Frieren"}',
    )
    assert not score.task_success
    assert not next(
        item for item in score.dimensions if item.dimension == "final_answer"
    ).passed


def test_exact_json_ignores_object_key_order():
    assert score_answer(
        {"expected_json": {"count": 0, "title": "Frieren"}},
        '{"title":"Frieren","count":0}',
    ).task_success


@pytest.mark.parametrize(
    "text", ["not JSON", '{"count":true}', '{"count":0,"extra":1}', '{"count":NaN}']
)
def test_invalid_or_different_json_fails(text):
    assert not score_answer({"expected_json": {"count": 0}}, text).task_success


def test_json_boolean_is_not_a_number():
    assert not score_answer(
        {"expected_json": {"count": 1}}, '{"count":true}'
    ).task_success


def test_required_and_forbidden_text_check_the_final_answer():
    contract = {"required_text": ["evidence"], "forbidden_text": ["invented"]}
    assert score_answer(contract, "The evidence supports this.").task_success
    assert not score_answer(contract, "Tool executed successfully.").task_success
    assert not score_answer(contract, "invented evidence").task_success


def test_failure_detail_does_not_echo_answer_payload():
    score = score_answer(
        {"expected_json": {"count": 0}}, '{"secret_sentinel": "do-not-export"}'
    )
    detail = next(
        item.detail for item in score.dimensions if item.dimension == "final_answer"
    )
    assert "do-not-export" not in detail
    assert "secret_sentinel" not in detail


def test_old_contract_has_no_new_dimension():
    case = case_with_answer({"required_text": ["x"]})
    case.deterministic.final_answer = None
    score = score_deterministic(case, ExecutionResult(route="chat", text=""))
    assert score is not None and score.task_success
    assert "final_answer" not in [item.dimension for item in score.dimensions]


def test_duplicate_json_keys_do_not_hide_an_incorrect_value():
    assert not score_answer(
        {"expected_json": {"count": 0}}, '{"count":1,"count":0}'
    ).task_success
