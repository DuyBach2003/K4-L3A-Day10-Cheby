from __future__ import annotations

from typing import Any
import logging

import great_expectations as gx
from great_expectations.data_context.types.base import ProgressBarsConfig
import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MAX_SUMMARY_CHARS = 20000
MIN_TITLE_CHARS = 8
MAX_STALE_RATIO = 0.25
REQUIRED_NOT_NULL_COLUMNS = ("paper_id", "title", "text_for_embedding")

logging.getLogger("great_expectations").setLevel(logging.ERROR)


def _build_expectations() -> list[Any]:
    expectations: list[Any] = [
        gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
    ]
    expectations += [gx.expectations.ExpectColumnValuesToNotBeNull(column=column) for column in REQUIRED_NOT_NULL_COLUMNS]
    expectations += [
        gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"),
        gx.expectations.ExpectColumnValueLengthsToBeBetween(
            column="summary", min_value=MIN_SUMMARY_CHARS, max_value=MAX_SUMMARY_CHARS
        ),
        # Extra guard: catches truncated titles that would break exact-title lookup.
        gx.expectations.ExpectColumnValueLengthsToBeBetween(column="title", min_value=MIN_TITLE_CHARS),
    ]
    return expectations


def _summarize_result(result: Any) -> dict[str, Any]:
    config = result.expectation_config
    kwargs = {key: value for key, value in dict(config.kwargs).items() if key != "batch_id"}
    details = result.result or {}
    return {
        "expectation": config.type,
        "column": kwargs.get("column"),
        "kwargs": kwargs,
        "success": bool(result.success),
        "observed_value": details.get("observed_value"),
        "unexpected_count": details.get("unexpected_count"),
        "unexpected_percent": details.get("unexpected_percent"),
        "partial_unexpected_list": [str(value) for value in (details.get("partial_unexpected_list") or [])][:10],
    }


def _freshness_payload(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    threshold = settings.freshness_threshold_days
    total_rows = int(len(df))
    published = pd.to_datetime(df["published"], errors="coerce") if total_rows else pd.Series(dtype="datetime64[ns]")
    ages = pd.to_numeric(df["age_days"], errors="coerce") if total_rows else pd.Series(dtype=float)
    stale_mask = ages > threshold
    stale_rows = int(stale_mask.sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    return {
        "checked_at": now_utc().isoformat(),
        "threshold_days": threshold,
        "max_stale_ratio": MAX_STALE_RATIO,
        "latest_published": published.max().date().isoformat() if published.notna().any() else None,
        "oldest_published": published.min().date().isoformat() if published.notna().any() else None,
        "latest_age_days": int(ages.min()) if ages.notna().any() else None,
        "median_age_days": float(ages.median()) if ages.notna().any() else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "stale_paper_ids": sorted(df.loc[stale_mask, "paper_id"].astype(str).unique().tolist()) if total_rows else [],
        "is_fresh": stale_ratio <= MAX_STALE_RATIO,
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Quality gate built with the GX 1.x fluent API (ephemeral context, whole-dataframe batch).

    `success` is the GX suite verdict; freshness is reported alongside as an SLA signal.
    The report is written to `data/quality/<report_name>_quality_report.json`.
    """
    context = gx.get_context(mode="ephemeral")
    context.variables.progress_bars = ProgressBarsConfig(globally=False)
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(gx.ExpectationSuite(name=f"papers_{report_name}_suite"))
    for expectation in _build_expectations():
        suite.add_expectation(expectation)
    validation = batch.validate(suite)

    expectation_results = [_summarize_result(result) for result in validation.results]
    freshness = _freshness_payload(df, settings)
    report = {
        "report_name": report_name,
        "engine": f"great_expectations {gx.__version__}",
        "validated_at": now_utc().isoformat(),
        "row_count": int(len(df)),
        "success": bool(validation.success),
        "evaluated_expectations": len(expectation_results),
        "successful_expectations": sum(1 for item in expectation_results if item["success"]),
        "failed_expectations": [item["expectation"] + (f"({item['column']})" if item["column"] else "") for item in expectation_results if not item["success"]],
        "expectations": expectation_results,
        "freshness": freshness,
        "gate_passed": bool(validation.success) and freshness["is_fresh"],
    }
    write_json(settings.paths.quality_dir / f"{report_name}_quality_report.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Freshness SLA: data is stale when more than 25% of rows are older than the threshold."""
    payload = _freshness_payload(df, settings)
    write_json(report_path, payload)
    return payload
