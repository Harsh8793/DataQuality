"""End-to-end DQ validation tests from the user's point of view.

Two questions this file answers:

1. **Are the counts right?** A golden 24-row frame with hand-counted defects is
   run through the real pipeline and every issue count is asserted against a
   number derived by hand, not by re-running the engine.

2. **Do the counts agree with themselves?** The Quality tab renders
   ``{issue.count} affected →`` on the issue card, then opens a modal that
   loads ``/quality/issues/{id}/affected`` and prints
   ``Showing first N of {total_rows} affected rows``. A user reads those two
   numbers side by side, so they must match. That invariant is asserted for
   every row-level issue the golden dataset produces.

The custom-validation ("Add validation with AI") section is exercised over the
real HTTP API for its whole lifecycle: propose → approve → score → drill-down →
ignore → re-include → delete.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from app.core.engines.affected import affected_mask
from app.core.engines.fixer import apply_fix
from app.core.engines.profiler import Profiler
from app.core.engines.quality_checks import QualityEngine
from app.schemas.quality import COLUMN_LEVEL_CHECKS

# --------------------------------------------------------------------------- #
# The golden dataset
# --------------------------------------------------------------------------- #
# 22 base rows, then rows 20 and 21 are appended again verbatim so exactly two
# rows are full duplicates. Every defect below is placed in rows 0-19 so the
# duplication step never changes a count by accident.
_BASE_ROWS = 22
_DUPLICATED = [20, 21]


def _base_frame() -> pd.DataFrame:
    dates = [f"2024-01-{d:02d}" for d in range(1, _BASE_ROWS + 1)]
    dates[5] = "not a date"      # unparseable
    dates[11] = "31/31/2024"     # parseable shape, impossible date

    emails = [f"a{i}@x.com" for i in range(_BASE_ROWS)]
    emails[1] = "bad@@"          # malformed
    emails[5] = "nope"           # malformed
    emails[11] = "x@@y"          # malformed
    emails[3] = None             # missing
    emails[8] = None             # missing

    notes = ["gamma"] * _BASE_ROWS
    notes[0] = "  alpha"         # leading whitespace
    notes[1] = "beta  "          # trailing whitespace
    notes[2] = "   "             # blank AND whitespace

    # 5 numeric-looking values among 17 words -> a text-majority mixed column.
    quantity = ["one", "two", "three", "four"] * 5 + ["one", "two"]
    for i in range(5):
        quantity[i] = str(i + 1)

    revenue: list[float | None] = [100.0 + 10 * i for i in range(20)]
    revenue.append(None)         # missing
    revenue.append(-50.0)        # negative

    return pd.DataFrame({
        "customer_id": list(range(1, _BASE_ROWS + 1)),
        "email": emails,
        "state": (
            ["Texas"] * 8 + ["texas"] * 2 + ["TEXAS"]
            + ["Ohio"] * 7 + ["ohio"] * 2 + ["Utah"] * 2
        ),
        "order_date": dates,
        "quantity": quantity,
        "revenue": revenue,
        "notes": notes,
        "region": ["APAC"] * _BASE_ROWS,
        "tier": [["A", "B", "C"][i % 3] for i in range(_BASE_ROWS)],
        "tier_copy": [["A", "B", "C"][i % 3] for i in range(_BASE_ROWS)],
    })


@pytest.fixture(scope="module")
def golden_frame() -> pd.DataFrame:
    base = _base_frame()
    return pd.concat([base, base.iloc[_DUPLICATED]], ignore_index=True)


# Hand-counted truth for the 24-row golden frame. Each entry is
# (check_key, column, expected_count) with the derivation in the comment.
EXPECTED_COUNTS: list[tuple[str, str | None, int]] = [
    ("missing_values", "email", 2),        # rows 3, 8
    ("missing_values", "revenue", 2),      # row 20 and its duplicate (row 22)
    ("blank_strings", "notes", 1),         # row 2 is "   "
    ("whitespace", "notes", 3),            # rows 0, 1 and the blank row 2
    ("invalid_email", "email", 3),         # rows 1, 5, 11
    ("invalid_date", "order_date", 2),     # rows 5, 11
    ("negative_values", "revenue", 2),     # row 21 and its duplicate (row 23)
    ("duplicate_rows", None, 2),           # rows 22, 23 repeat rows 20, 21
    ("duplicate_ids", "customer_id", 2),   # ids 21 and 22 each appear twice
    ("constant_column", "region", 1),      # one offending column
    ("duplicate_columns", "tier_copy", 1), # one offending column
    ("case_inconsistency", "state", 5),    # texas x2 + TEXAS + ohio x2 differ from canonical
    ("mixed_types", "quantity", 5),        # 5 stray numbers in a text-majority column
]

# Duplicate checks count the redundant copies (what a fix removes) while the
# drill-down lists whole duplicate groups so they can be compared. The numbers
# differ by design; the modal explains it rather than the engine flattening it.
GROUP_LISTING_CHECKS = {"duplicate_rows", "duplicate_ids"}


def _run(frame: pd.DataFrame):
    profile = Profiler().profile(frame)
    return QualityEngine().run(frame, profile), profile


def _find(findings, check_key: str, column: str | None):
    hits = [f for f in findings if f.check_key == check_key and f.column_name == column]
    assert len(hits) == 1, (
        f"expected exactly one {check_key} finding on {column}, got {len(hits)}"
    )
    return hits[0]


# --------------------------------------------------------------------------- #
# 1. Detection counts match a hand count
# --------------------------------------------------------------------------- #
class TestGoldenCounts:
    def test_frame_is_shaped_as_the_hand_count_assumes(self, golden_frame) -> None:
        """Guards the fixture itself — every count below depends on this shape."""
        assert len(golden_frame) == 24
        assert golden_frame["email"].isna().sum() == 2
        assert golden_frame["revenue"].isna().sum() == 2
        assert int(golden_frame.duplicated().sum()) == 2

    @pytest.mark.parametrize(("check_key", "column", "expected"), EXPECTED_COUNTS)
    def test_check_reports_the_hand_counted_number(
        self, golden_frame, check_key: str, column: str | None, expected: int
    ) -> None:
        findings, _ = _run(golden_frame)
        assert _find(findings, check_key, column).count == expected

    def test_no_unexpected_checks_fire(self, golden_frame) -> None:
        """A false positive is as much a wrong count as a wrong number."""
        findings, _ = _run(golden_frame)
        fired = {(f.check_key, f.column_name) for f in findings}
        expected = {(k, c) for k, c, _ in EXPECTED_COUNTS}
        # Outliers on revenue are IQR-derived rather than hand-countable, so
        # they're allowed but not required.
        unexpected = fired - expected - {("outliers", "revenue")}
        assert not unexpected, f"unexpected findings: {sorted(unexpected)}"

    def test_every_expected_check_actually_fires(self, golden_frame) -> None:
        findings, _ = _run(golden_frame)
        fired = {(f.check_key, f.column_name) for f in findings}
        missing = {(k, c) for k, c, _ in EXPECTED_COUNTS} - fired
        assert not missing, f"checks that failed to fire: {sorted(missing)}"


# --------------------------------------------------------------------------- #
# 2. The drill-down agrees with the badge
# --------------------------------------------------------------------------- #
class TestCountConsistency:
    """``N affected →`` on the card must equal the row count in the modal.

    ``affected_mask`` is what ``/quality/issues/{id}/affected`` uses to build
    ``total_rows``. If it disagrees with the finding's ``count``, the user sees
    two different numbers for one issue.
    """

    @pytest.mark.parametrize(
        ("check_key", "column"),
        [
            (k, c) for k, c, _ in EXPECTED_COUNTS
            if k not in COLUMN_LEVEL_CHECKS and k not in GROUP_LISTING_CHECKS
        ],
    )
    def test_affected_row_count_matches_issue_count(
        self, golden_frame, check_key: str, column: str | None
    ) -> None:
        finding = _find(_run(golden_frame)[0], check_key, column)
        drilldown = int(affected_mask(golden_frame, check_key, column).sum())
        assert drilldown == finding.count, (
            f"{check_key} on {column}: card says {finding.count} affected, "
            f"drill-down returns {drilldown} rows"
        )

    @pytest.mark.parametrize("check_key", sorted(GROUP_LISTING_CHECKS))
    def test_duplicate_drilldown_lists_whole_groups(self, golden_frame, check_key: str) -> None:
        """Duplicates are the one documented exception: the count is the
        redundant copies, the drill-down is the full group (originals too)."""
        column = "customer_id" if check_key == "duplicate_ids" else None
        finding = _find(_run(golden_frame)[0], check_key, column)
        drilldown = int(affected_mask(golden_frame, check_key, column).sum())
        assert finding.count == 2
        assert drilldown == 4, "both copies of each duplicate pair should be listed"

    @pytest.mark.parametrize(
        ("check_key", "column"),
        [(k, c) for k, c, _ in EXPECTED_COUNTS if k not in COLUMN_LEVEL_CHECKS],
    )
    def test_the_fix_touches_exactly_the_rows_the_card_promised(
        self, golden_frame, check_key: str, column: str | None
    ) -> None:
        """Third number the user sees: 'Standardized casing of N values' in the
        solved card. It must agree with the count they clicked Fix on."""
        from app.core.engines.fixer import FIXABLE_CHECKS

        if check_key not in FIXABLE_CHECKS:
            pytest.skip(f"{check_key} has no automated fix")
        finding = _find(_run(golden_frame)[0], check_key, column)
        assert apply_fix(golden_frame, check_key, column).rows_affected == finding.count


# --------------------------------------------------------------------------- #
# 2b. The real demo dataset
# --------------------------------------------------------------------------- #
SALES_CSV = Path(__file__).parents[2] / "sample_sales_500.csv"

# Verified against sample_sales_500.csv by recomputing each count from raw
# pandas independently of the engine. Pinned so a change to any check has to be
# a deliberate decision about the dataset everyone demos on.
SALES_COUNTS: dict[tuple[str, str | None], int] = {
    ("missing_values", "notes"): 214,
    ("missing_values", "revenue"): 42,
    ("blank_strings", "notes"): 90,
    ("whitespace", "Full Name"): 157,
    ("whitespace", "notes"): 90,
    ("invalid_email", "email"): 94,
    ("invalid_phone", "phone"): 93,
    ("invalid_date", "order_date"): 87,
    ("case_inconsistency", "Full Name"): 132,
    ("case_inconsistency", "country"): 72,
    ("case_inconsistency", "gender"): 243,
    ("mixed_types", "phone"): 96,
    ("mixed_types", "quantity"): 80,
    ("duplicate_rows", None): 12,
    ("duplicate_ids", "customer_id"): 12,
    ("constant_column", "region"): 1,
    ("outliers", "revenue"): 13,
}


@pytest.fixture(scope="module")
def sales_frame() -> pd.DataFrame:
    if not SALES_CSV.exists():
        pytest.skip(f"{SALES_CSV.name} is not present")
    from app.agents.upload_agent import UploadAgent
    from app.services.dataset_service import DatasetService

    loaded = UploadAgent().load(SALES_CSV.read_bytes(), "csv").df
    return DatasetService._normalize_columns(loaded)


class TestSampleSalesDataset:
    """Counts on the 500-row demo dataset, verified against raw pandas."""

    def test_shape(self, sales_frame) -> None:
        assert sales_frame.shape == (500, 13)

    def test_every_count_is_pinned(self, sales_frame) -> None:
        findings, _ = _run(sales_frame)
        actual = {(f.check_key, f.column_name): f.count for f in findings}
        assert actual == SALES_COUNTS

    @pytest.mark.parametrize(
        ("check_key", "column"),
        [k for k in SALES_COUNTS
         if k[0] not in COLUMN_LEVEL_CHECKS and k[0] not in GROUP_LISTING_CHECKS],
    )
    def test_drilldown_agrees(self, sales_frame, check_key: str, column: str | None) -> None:
        expected = SALES_COUNTS[(check_key, column)]
        assert int(affected_mask(sales_frame, check_key, column).sum()) == expected

    @pytest.mark.parametrize(
        ("check_key", "column"),
        [k for k in SALES_COUNTS if k[0] not in GROUP_LISTING_CHECKS],
    )
    def test_fix_reports_the_same_number(
        self, sales_frame, check_key: str, column: str | None
    ) -> None:
        from app.core.engines.fixer import FIXABLE_CHECKS

        if check_key not in FIXABLE_CHECKS:
            pytest.skip(f"{check_key} has no automated fix")
        assert apply_fix(sales_frame, check_key, column).rows_affected == SALES_COUNTS[
            (check_key, column)
        ]


class TestFixStaysInsideItsIssue:
    """A fix must resolve the issue the user clicked — and nothing else."""

    def test_fixing_blanks_leaves_genuine_nulls_alone(self) -> None:
        """``notes`` on the sample sales data has 214 nulls and 90 blanks as two
        separate issues. Fixing the blanks used to impute all 304, silently
        resolving — or overriding an explicit 'Ignore' on — the other card."""
        frame = pd.DataFrame({"notes": ["VIP", "   ", "", None, None, "VIP"]})
        result = apply_fix(frame, "blank_strings", "notes")
        assert result.rows_affected == 2, "only the two blank cells are this issue"
        assert result.df["notes"].isna().sum() == 2, "the real nulls must survive"
        assert not (result.df["notes"].dropna().astype(str).str.strip() == "").any()

    def test_blank_fix_does_not_impute_a_blank(self) -> None:
        """The blanks are nulled before the mode is taken, so a column that is
        mostly blank can't 'fix' itself by filling blanks with a blank."""
        frame = pd.DataFrame({"notes": ["   "] * 5 + ["VIP", "VIP"]})
        result = apply_fix(frame, "blank_strings", "notes")
        assert result.rows_affected == 5
        assert result.df["notes"].tolist() == ["VIP"] * 7

    def test_dropping_a_column_reports_one_change_not_one_per_row(self) -> None:
        """``rows_affected`` feeds 'showing N of M changes' in the diff modal,
        and a dropped column produces exactly one change record."""
        frame = pd.DataFrame({"same": ["x"] * 30, "n": range(30)})
        result = apply_fix(frame, "constant_column", "same")
        assert result.rows_affected == 1
        assert "same" not in result.df.columns
        assert len(result.df) == 30, "dropping a column must not drop rows"


# --------------------------------------------------------------------------- #
# 3. Custom validations ("Add validation with AI") over the real API
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def golden_csv(golden_frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    golden_frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode()


@pytest.fixture(scope="module")
def uploaded(client, auth_headers, golden_csv: bytes):
    """Upload the golden dataset once and analyze it."""
    res = client.post(
        "/api/v1/datasets",
        headers=auth_headers,
        files={"file": ("golden.csv", io.BytesIO(golden_csv), "text/csv")},
    )
    assert res.status_code == 200, res.text
    dataset_id = res.json()["data"]["id"]
    report = client.get(f"/api/v1/datasets/{dataset_id}/quality", headers=auth_headers)
    assert report.status_code == 200, report.text
    yield dataset_id, report.json()["data"]
    client.delete(f"/api/v1/datasets/{dataset_id}", headers=auth_headers)


class TestQualityTabOverApi:
    def test_report_counts_survive_the_round_trip(self, uploaded) -> None:
        """Upload → parquet → analysis → JSON must not change any count."""
        _, report = uploaded
        by_key = {(i["check_key"], i["column_name"]): i["count"] for i in report["issues"]}
        for check_key, column, expected in EXPECTED_COUNTS:
            assert by_key.get((check_key, column)) == expected, (
                f"{check_key} on {column}: API returned {by_key.get((check_key, column))}, "
                f"expected {expected}"
            )

    def test_total_issues_matches_the_issue_list(self, uploaded) -> None:
        """The 'All severities (N)' dropdown reads ``total_issues`` while the
        list below it renders ``issues`` — they must be the same length."""
        _, report = uploaded
        assert report["total_issues"] == len(report["issues"])

    def test_affected_endpoint_agrees_with_every_issue_card(
        self, client, auth_headers, uploaded
    ) -> None:
        dataset_id, report = uploaded
        mismatches = []
        for issue in report["issues"]:
            if issue["column_level"] or issue["custom"]:
                continue
            if issue["check_key"] in GROUP_LISTING_CHECKS:
                continue  # covered by test_duplicate_drilldown_lists_whole_groups
            res = client.get(
                f"/api/v1/datasets/{dataset_id}/quality/issues/{issue['id']}/affected",
                headers=auth_headers,
            )
            assert res.status_code == 200, res.text
            total = res.json()["data"]["total_rows"]
            if total != issue["count"]:
                mismatches.append(
                    f"{issue['check_key']}/{issue['column_name']}: "
                    f"card={issue['count']} modal={total}"
                )
        assert not mismatches, "issue count disagrees with drill-down:\n" + "\n".join(mismatches)


class TestAddValidationSection:
    """The full 'Add validation with AI' lifecycle a user clicks through.

    The LLM is stubbed off by ``conftest.stub_llm``, so this exercises the
    deterministic rule parser — which is the path a user hits whenever Groq is
    unavailable, and the one whose counts must still be right.
    """

    def test_proposal_row_count_matches_the_data(self, client, auth_headers, uploaded) -> None:
        """The 'N of M rows flagged' badge on the proposal card."""
        dataset_id, _ = uploaded
        res = client.post(
            f"/api/v1/datasets/{dataset_id}/quality/validations/propose",
            headers=auth_headers,
            json={"prompt": "flag rows where revenue is less than 0"},
        )
        assert res.status_code == 200, res.text
        proposal = res.json()["data"]
        assert proposal["total_rows"] == 24
        # Same two rows the built-in negative_values check finds.
        assert proposal["matched_rows"] == 2
        assert len(proposal["sample_rows"]) == 2

    def test_proposal_without_a_usable_column_is_rejected(
        self, client, auth_headers, uploaded
    ) -> None:
        dataset_id, _ = uploaded
        res = client.post(
            f"/api/v1/datasets/{dataset_id}/quality/validations/propose",
            headers=auth_headers,
            json={"prompt": "make the data better please"},
        )
        assert res.status_code == 400, res.text

    def test_approved_validation_lifecycle(self, client, auth_headers, uploaded) -> None:
        """propose → approve → appears with the same count → drill-down agrees
        → ignoring restores the score → deleting removes it entirely."""
        dataset_id, before = uploaded
        base_url = f"/api/v1/datasets/{dataset_id}/quality/validations"

        propose = client.post(
            f"{base_url}/propose",
            headers=auth_headers,
            json={"prompt": "flag rows where revenue is less than 0"},
        )
        proposal = propose.json()["data"]
        matched = proposal["matched_rows"]

        added = client.post(base_url, headers=auth_headers, json={
            "name": proposal["name"],
            "description": proposal["description"],
            "dimension": proposal["dimension"],
            "severity": proposal["severity"],
            "condition": proposal["condition"],
        })
        assert added.status_code == 200, added.text
        payload = added.json()["data"]
        validation_id = payload["validations"][0]["id"]
        report = payload["report"]

        # It shows up as a custom issue carrying the previewed count.
        custom = [i for i in report["issues"] if i["custom"]]
        assert len(custom) == 1, "the approved rule should appear as one issue"
        issue = custom[0]
        assert issue["check_key"] == f"custom_{validation_id}"
        assert issue["count"] == matched, (
            f"proposal previewed {matched} rows but the issue card says {issue['count']}"
        )
        assert issue["problem"] == proposal["name"]

        # ...and it is enforced: an extra finding drags the score down.
        assert report["total_issues"] == before["total_issues"] + 1
        assert report["overall_score"] < before["overall_score"]

        # The drill-down returns exactly the rows the badge promised.
        affected = client.get(
            f"/api/v1/datasets/{dataset_id}/quality/issues/{issue['id']}/affected",
            headers=auth_headers,
        )
        assert affected.status_code == 200, affected.text
        assert affected.json()["data"]["total_rows"] == matched

        # Ignoring it keeps it visible but takes it back out of the score.
        ignored = client.post(
            f"/api/v1/datasets/{dataset_id}/quality/exclusions",
            headers=auth_headers,
            json={"check_key": issue["check_key"], "column_name": issue["column_name"]},
        )
        assert ignored.status_code == 200, ignored.text
        ignored_report = ignored.json()["data"]["report"]
        still_there = [i for i in ignored_report["issues"] if i["check_key"] == issue["check_key"]]
        assert still_there and still_there[0]["excluded"] is True
        assert still_there[0]["fixable"] is False
        assert ignored_report["overall_score"] == pytest.approx(before["overall_score"])

        # Re-including it drops the score again.
        reincluded = client.post(
            f"/api/v1/datasets/{dataset_id}/quality/exclusions/remove",
            headers=auth_headers,
            json={"check_key": issue["check_key"], "column_name": issue["column_name"]},
        )
        assert reincluded.status_code == 200, reincluded.text
        assert reincluded.json()["data"]["report"]["overall_score"] < before["overall_score"]

        # Deleting the rule removes the issue and restores the original score.
        deleted = client.delete(f"{base_url}/{validation_id}", headers=auth_headers)
        assert deleted.status_code == 200, deleted.text
        final = deleted.json()["data"]["report"]
        assert not [i for i in final["issues"] if i["custom"]]
        assert final["total_issues"] == before["total_issues"]
        assert final["overall_score"] == pytest.approx(before["overall_score"])

    def test_a_rule_matching_nothing_is_not_added_as_an_issue(
        self, client, auth_headers, uploaded
    ) -> None:
        """A rule that flags zero rows must not appear as a zero-count issue."""
        dataset_id, before = uploaded
        base_url = f"/api/v1/datasets/{dataset_id}/quality/validations"
        added = client.post(base_url, headers=auth_headers, json={
            "name": "Revenue below -1000",
            "description": "Never true for this dataset.",
            "dimension": "validity",
            "severity": "high",
            "condition": 'TRY_CAST("revenue" AS DOUBLE) < -1000',
        })
        assert added.status_code == 200, added.text
        payload = added.json()["data"]
        new_id = max(v["id"] for v in payload["validations"])
        try:
            report = payload["report"]
            assert not [i for i in report["issues"] if i["check_key"] == f"custom_{new_id}"]
            assert report["overall_score"] == pytest.approx(before["overall_score"])
        finally:
            client.delete(f"{base_url}/{new_id}", headers=auth_headers)

    def test_invalid_sql_condition_is_rejected(self, client, auth_headers, uploaded) -> None:
        dataset_id, _ = uploaded
        res = client.post(
            f"/api/v1/datasets/{dataset_id}/quality/validations",
            headers=auth_headers,
            json={
                "name": "Broken", "description": "", "dimension": "validity",
                "severity": "high", "condition": '"no_such_column" > 1',
            },
        )
        assert res.status_code == 400, res.text

    def test_write_sql_in_a_condition_is_blocked(self, client, auth_headers, uploaded) -> None:
        dataset_id, _ = uploaded
        res = client.post(
            f"/api/v1/datasets/{dataset_id}/quality/validations",
            headers=auth_headers,
            json={
                "name": "Malicious", "description": "", "dimension": "validity",
                "severity": "high", "condition": '1=1; DROP TABLE dataset',
            },
        )
        assert res.status_code == 400, res.text
