"""LLM-as-judge metrics for the chat agent (DeepEval).

Reports the four standard RAG metrics against the live agent:

* ``FaithfulnessMetric``        — groundedness: is every claim supported by the rows?
* ``AnswerRelevancyMetric``     — does the answer address the question asked?
* ``ContextualPrecisionMetric`` — are the relevant rows ranked ahead of the rest?
* ``ContextualRecallMetric``    — do the retrieved rows cover the expected answer?

"Retrieval" here is SQL: the context is the rows DuckDB returned, one chunk per
row. Skipped unless ``RUN_LLM_JUDGE=1`` because every metric spends Groq tokens
(~4 judge calls per metric per case) and LLM judges are non-deterministic — this
is a measurement run, not a build gate.

    cd backend
    RUN_LLM_JUDGE=1 python -m pytest tests/test_llm_judge_metrics.py -s
    RUN_LLM_JUDGE=1 JUDGE_MODEL=llama-3.1-8b-instant python -m pytest tests/... -s
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

# DeepEval reads these at import time; keep the run local and quiet.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("ERROR_REPORTING", "NO")
os.environ.setdefault("DEEPEVAL_DISABLE_PROGRESS_BAR", "YES")

deepeval = pytest.importorskip("deepeval", reason="pip install deepeval")

from deepeval.metrics import (  # noqa: E402
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.models.base_model import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_JUDGE") != "1",
    reason="costs Groq tokens and is non-deterministic; set RUN_LLM_JUDGE=1 to measure",
)

# A weak judge produces noisy scores, so judging defaults to the largest model
# on the account rather than the 8B model the product itself runs on.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "llama-3.3-70b-versatile")


# --------------------------------------------------------------------------- #
# Groq as the judge
# --------------------------------------------------------------------------- #
class GroqJudge(DeepEvalBaseLLM):
    """DeepEval judge backed by Groq instead of OpenAI.

    DeepEval asks for structured output by passing a Pydantic ``schema``; we
    request JSON mode and validate the reply into that schema. Returning the
    model instance (not a string) is what lets DeepEval skip its own brittle
    JSON-repair path.
    """

    def __init__(self, model: str = JUDGE_MODEL) -> None:
        self._model_name = model
        super().__init__(model)

    def load_model(self):
        from groq import Groq

        from app.config import get_settings

        return Groq(api_key=get_settings().groq_api_key)

    def get_model_name(self) -> str:
        return f"Groq {self._model_name}"

    def generate(self, prompt: str, schema=None):
        kwargs = {"response_format": {"type": "json_object"}} if schema else {}
        response = self.model.chat.completions.create(
            model=self._model_name,
            temperature=0,  # a judge that varies run to run cannot be compared
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        text = response.choices[0].message.content or ""
        if schema is None:
            return text
        return schema.model_validate(json.loads(text))

    async def a_generate(self, prompt: str, schema=None):
        # The metrics run with async_mode=False, so sync generation is enough.
        return self.generate(prompt, schema=schema)


@pytest.fixture(scope="module")
def judge() -> GroqJudge:
    from app.config import get_settings

    if not get_settings().is_llm_ready:
        pytest.skip("no GROQ_API_KEY configured")
    return GroqJudge()


# --------------------------------------------------------------------------- #
# The agent under test, wired to the real model
# --------------------------------------------------------------------------- #
SALES = pd.DataFrame(
    {
        "region": ["North", "North", "South", "South", "East", "East",
                   "West", "West", "North", "South", "East", "West"],
        "product": ["Laptop", "Mouse", "Laptop", "Monitor", "Mouse", "Monitor",
                    "Laptop", "Mouse", "Monitor", "Mouse", "Laptop", "Monitor"],
        "revenue": [1200.0, 50.0, 1300.0, 400.0, 75.0, 450.0,
                    1100.0, 60.0, 500.0, 80.0, 1400.0, 425.0],
        "units": [2, 5, 1, 2, 3, 1, 2, 6, 1, 4, 3, 2],
        "order_date": ["2024-01-05", "2024-01-12", "2024-02-03", "2024-02-14",
                       "2024-03-02", "2024-03-19", "2024-04-04", "2024-04-21",
                       "2024-05-09", "2024-05-23", "2024-06-07", "2024-06-18"],
    }
)


@pytest.fixture(scope="module")
def live_chat():
    """A ChatAgent using the real Groq model, plus a profiled context.

    ``conftest.stub_llm`` disables the LLM for every test by design; judging the
    shipped behaviour means putting the real client back for this module only.
    """
    import app.core.llm.groq_client as groq_client
    from app.core.llm.groq_client import GroqLLM

    real = GroqLLM()
    if not real.available:
        pytest.skip("no GROQ_API_KEY configured")

    saved = (groq_client._llm, groq_client.get_llm)
    groq_client._llm = real
    groq_client.get_llm = lambda: real

    import app.agents.chat_agent as chat_module

    saved_agent_getter = chat_module.get_llm
    chat_module.get_llm = lambda: real
    try:
        from app.agents.base import AgentContext
        from app.agents.profiling_agent import ProfilingAgent

        ctx = AgentContext(dataset_id="judge", dataset_name="sales", df=SALES.copy())
        ProfilingAgent().run(ctx)
        yield chat_module.ChatAgent(), ctx
    finally:
        groq_client._llm, groq_client.get_llm = saved
        chat_module.get_llm = saved_agent_getter


# --------------------------------------------------------------------------- #
# Cases: question + the answer a correct agent should give
# --------------------------------------------------------------------------- #
# ``expected_output`` is required by the contextual metrics — it is what recall
# is measured *against*. Values below are computed from SALES by hand so the
# expectation is independent of the code under test.
CASES = [
    pytest.param(
        "What is the average revenue by region?",
        "Average revenue per region: East 641.67, South 593.33, North 583.33, "
        "West 528.33. East is the highest.",
        id="group_average",
    ),
    pytest.param(
        "What is the average revenue for Laptop?",
        "The average revenue for Laptop orders is 1250.",
        id="filtered_average",
    ),
    pytest.param(
        "Top 3 products by total revenue",
        "The top 3 products by total revenue are Laptop at 5000, Monitor at 1775 "
        "and Mouse at 265.",
        id="top_n",
    ),
    pytest.param(
        "How many rows are in this dataset?",
        "The dataset contains 12 rows.",
        id="row_count",
    ),
]


def _metrics(judge: GroqJudge) -> list:
    """One instance per case: DeepEval metrics carry per-run state."""
    common = {"model": judge, "async_mode": False, "include_reason": True}
    return [
        FaithfulnessMetric(threshold=0.9, **common),
        AnswerRelevancyMetric(threshold=0.8, **common),
        ContextualPrecisionMetric(threshold=0.7, **common),
        ContextualRecallMetric(threshold=0.7, **common),
    ]


@pytest.mark.parametrize("question,expected", CASES)
def test_chat_agent_llm_judge_metrics(question, expected, live_chat, judge, record_property):
    """Measure the four RAG metrics for one question and print the scores."""
    agent, ctx = live_chat
    answer = agent.ask(ctx, question)

    # One context chunk per returned row: the contextual metrics score how well
    # the retrieved set covers and ranks the answer, which a single blob hides.
    retrieval_context = [json.dumps(row, default=str) for row in answer.rows] or [
        "(no rows returned)"
    ]

    case = LLMTestCase(
        input=question,
        actual_output=answer.answer,
        expected_output=expected,
        retrieval_context=retrieval_context,
    )

    print(f"\n--- {question}")
    print(f"    SQL:    {answer.sql or '(none)'}")
    print(f"    answer: {answer.answer[:160]}")

    failures = []
    for metric in _metrics(judge):
        metric.measure(case)
        name = type(metric).__name__
        status = "PASS" if metric.score >= metric.threshold else "FAIL"
        print(f"    {name:<28} {metric.score:.2f} (>= {metric.threshold}) {status}")
        print(f"      reason: {str(metric.reason)[:200]}")
        record_property(name, metric.score)
        if status == "FAIL":
            failures.append(f"{name}={metric.score:.2f} < {metric.threshold}: {metric.reason}")

    assert not failures, "\n".join(failures)
