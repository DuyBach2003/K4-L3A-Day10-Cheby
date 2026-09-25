from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pandas as pd
import pytest

from core.config import load_settings
from core.utils import read_json
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records, parse_crossref_payload
from observability.quality import build_freshness_report, run_data_quality_checks
from pipelines.phase1 import dataset_fingerprint

RUN_DATE = datetime(2026, 9, 25, tzinfo=UTC)


@pytest.fixture(scope="module")
def settings(tmp_path_factory):
    base = load_settings()
    quality_dir = tmp_path_factory.mktemp("quality")
    return replace(base, paths=replace(base.paths, quality_dir=quality_dir))


@pytest.fixture(scope="module")
def clean_df(settings):
    return build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), RUN_DATE)


def test_parse_strips_jats_and_dedupes():
    item = {
        "DOI": "10.1/ABC",
        "title": ["  A   Title  "],
        "abstract": "<jats:p>Hello &amp; <jats:italic>world</jats:italic>.</jats:p>",
        "author": [{"given": "Minh", "family": "Nguyen"}],
        "subject": ["AI"],
        "published": {"date-parts": [[2026, 5]]},
        "URL": "https://doi.org/10.1/abc",
    }
    missing_abstract = {**item, "DOI": "10.1/other", "abstract": ""}
    records = parse_crossref_payload({"message": {"items": [item, item, missing_abstract]}})
    assert len(records) == 1
    record = records[0]
    assert record.paper_id == "10.1/abc"
    assert record.title == "A Title"
    assert record.summary == "Hello & world ."
    assert record.authors == ["Minh Nguyen"]
    assert record.published == "2026-05-01"


def test_snapshot_parses_to_raw_records(settings):
    payload = read_json(settings.paths.raw_api_response)
    records = parse_crossref_payload(payload)
    assert len(records) == 24
    assert [r.paper_id for r in records] == [r.paper_id for r in load_raw_records(settings.paths.raw_records_json)]


def test_clean_dataframe_schema(clean_df):
    assert len(clean_df) == 24
    assert clean_df["paper_id"].is_unique
    first = clean_df.iloc[0]
    for prefix in ("Title:", "Authors:", "Published:", "Categories:", "Summary:"):
        assert prefix in first["text_for_embedding"]
    expected_age = (RUN_DATE.date() - pd.Timestamp(first["published"]).date()).days
    assert first["age_days"] == expected_age
    assert clean_df["published"].is_monotonic_decreasing


def test_clean_dataframe_is_deterministic(settings, clean_df):
    again = build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), RUN_DATE)
    assert dataset_fingerprint(again) == dataset_fingerprint(clean_df)


def test_quality_gate_passes_on_clean_data(clean_df, settings):
    report = run_data_quality_checks(clean_df, settings, "pytest_clean")
    assert report["success"] is True
    assert report["freshness"]["is_fresh"] is True
    assert (settings.paths.quality_dir / "pytest_clean_quality_report.json").exists()


def test_corruption_is_detected(clean_df, settings, tmp_path):
    log_path = tmp_path / "corruption_log.json"
    corrupted = corrupt_clean_dataframe(clean_df, log_path)
    log = read_json(log_path)
    assert {item["corruption_type"] for item in log["corruptions"]} == {
        "drop_latest_records", "blank_summary", "inject_noise", "truncate_title", "stale_date", "duplicate_rows",
    }
    assert not corrupted["paper_id"].is_unique

    report = run_data_quality_checks(corrupted, settings, "pytest_corrupted")
    assert report["success"] is False
    failed = " ".join(report["failed_expectations"])
    assert "unique(paper_id)" in failed and "(summary)" in failed and "(title)" in failed

    freshness = build_freshness_report(corrupted, settings, tmp_path / "freshness.json")
    assert freshness["is_fresh"] is False


def test_corruption_is_seeded(clean_df, tmp_path):
    first = corrupt_clean_dataframe(clean_df, tmp_path / "a.json")
    second = corrupt_clean_dataframe(clean_df, tmp_path / "b.json")
    pd.testing.assert_frame_equal(first, second)


def test_build_test_set(clean_df, tmp_path):
    test_set = build_test_set(clean_df, tmp_path / "test_set.json")
    assert len(test_set) == 10
    assert {item["question_type"] for item in test_set} == {"summary", "authors", "date", "categories"}
    known = set(clean_df["paper_id"])
    assert all(doc_id in known for item in test_set for doc_id in item["ground_truth_doc_ids"])
    assert all(item["ground_truth"] for item in test_set)
