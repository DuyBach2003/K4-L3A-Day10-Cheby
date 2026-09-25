from __future__ import annotations

from typing import Any

from core.utils import now_utc, write_text

HEADLINE_METRICS = [
    ("retrieval_hit_rate", "Retrieval Hit Rate"),
    ("mean_token_f1", "Mean Token F1"),
    ("judge_accuracy", "Judge Accuracy"),
    ("mean_judge_score", "Mean Judge Score (1-5)"),
]


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "✅ True" if value else "❌ False"
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "—"
    return str(value)


def _delta(value: Any, reference: Any) -> str:
    if not isinstance(value, (int, float)) or not isinstance(reference, (int, float)) or isinstance(value, bool):
        return "—"
    return f"{value - reference:+.4f}"


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows]
    return lines


def _quality_lines(quality: dict[str, Any]) -> list[str]:
    rows = [
        [
            item["expectation"],
            item.get("column") or "(table)",
            item["success"],
            item.get("observed_value") if item.get("observed_value") is not None else item.get("unexpected_count"),
        ]
        for item in quality.get("expectations", [])
    ]
    lines = [
        f"- Engine: `{quality.get('engine', 'great_expectations')}` (ephemeral context, `add_pandas` + whole-dataframe batch)",
        f"- Suite result: **{_fmt(quality.get('success'))}** "
        f"({quality.get('successful_expectations')}/{quality.get('evaluated_expectations')} expectations passed)",
        "",
    ]
    return lines + _table(["Expectation", "Column", "Success", "Observed / unexpected"], rows)


def _freshness_lines(freshness: dict[str, Any]) -> list[str]:
    return _table(
        ["Field", "Value"],
        [
            ["Threshold (days)", freshness.get("threshold_days")],
            ["Latest published", freshness.get("latest_published")],
            ["Oldest published", freshness.get("oldest_published")],
            ["Stale rows / total", f"{freshness.get('stale_rows')} / {freshness.get('total_rows')}"],
            ["Stale ratio (max allowed)", f"{freshness.get('stale_ratio', 0):.2%} ({freshness.get('max_stale_ratio', 0.25):.0%})"],
            ["is_fresh", freshness.get("is_fresh")],
        ],
    )


def _question_type_rows(metrics_by_state: list[tuple[str, dict[str, Any]]], metric: str) -> list[list[Any]]:
    types = sorted({key for _, metrics in metrics_by_state for key in (metrics.get("by_question_type") or {})})
    return [
        [question_type] + [(metrics.get("by_question_type") or {}).get(question_type, {}).get(metric) for _, metrics in metrics_by_state]
        for question_type in types
    ]


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the baseline (phase 1) markdown report."""
    lines = [
        "# Phase 1 Report — Baseline Pipeline",
        "",
        f"_Generated at {now_utc().isoformat()}_",
        "",
        "## 1. Source & lineage",
        "",
        *_table(["Field", "Value"], [[key, value] for key, value in source_summary.items()]),
        "",
        "## 2. Retrieval & answer quality (baseline)",
        "",
        *_table(["Metric", "Value"], [[label, metrics.get(key)] for key, label in HEADLINE_METRICS] + [["Samples", metrics.get("samples")], ["Judge mode", metrics.get("judge_mode")]]),
        "",
        "### Per question type",
        "",
        *_table(["Question type", "Hit rate", "Token F1", "Judge accuracy"], [
            [question_type, values.get("retrieval_hit_rate"), values.get("mean_token_f1"), values.get("judge_accuracy")]
            for question_type, values in (metrics.get("by_question_type") or {}).items()
        ]),
        "",
        "## 3. Data quality gate (Great Expectations 1.x)",
        "",
        *_quality_lines(quality),
        "",
        "## 4. Freshness SLA",
        "",
        *_freshness_lines(freshness),
        "",
        "## 5. Verdict",
        "",
        f"- Quality gate: **{'PASSED' if quality.get('success') else 'FAILED'}** — "
        + ("clean data was allowed into the `papers-baseline` collection." if quality.get("success") else "data was blocked before indexing."),
        f"- Freshness: **{'FRESH' if freshness.get('is_fresh') else 'STALE'}** "
        f"({freshness.get('stale_rows')}/{freshness.get('total_rows')} rows older than {freshness.get('threshold_days')} days).",
        f"- Baseline hit rate {_fmt(metrics.get('retrieval_hit_rate'))}, token F1 {_fmt(metrics.get('mean_token_f1'))}: "
        "these numbers are the reference for the corruption experiment.",
        "",
    ]
    write_text(report_path, "\n".join(lines))


def _analysis_lines(
    baseline: dict[str, Any],
    corrupted: dict[str, Any],
    repaired: dict[str, Any],
    corrupted_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_quality: dict[str, Any],
    repaired_freshness: dict[str, Any],
    dataset_check: dict[str, Any] | None,
) -> list[str]:
    lines: list[str] = []
    for key, label in HEADLINE_METRICS:
        base, bad, fixed = baseline.get(key), corrupted.get(key), repaired.get(key)
        if not all(isinstance(value, (int, float)) for value in (base, bad, fixed)):
            continue
        change = (bad - base) / base if base else 0.0
        lines.append(
            f"- **{label}**: {base:.4f} → {bad:.4f} ({change:+.1%} relative change) → {fixed:.4f} after repair "
            f"({'fully recovered' if abs(fixed - base) < 1e-9 else 'partially recovered' if fixed > bad else 'not recovered'})."
        )

    by_type_base = baseline.get("by_question_type") or {}
    by_type_bad = corrupted.get("by_question_type") or {}
    worst = sorted(
        (
            (by_type_base[question_type]["mean_token_f1"] - by_type_bad[question_type]["mean_token_f1"], question_type)
            for question_type in by_type_base
            if question_type in by_type_bad
        ),
        reverse=True,
    )
    if worst and worst[0][0] > 0:
        lines.append(f"- Largest token-F1 drop by question type: `{worst[0][1]}` (−{worst[0][0]:.4f}).")

    failed = corrupted_quality.get("failed_expectations") or []
    lines.append(
        f"- The GX gate flagged the corrupted batch with {len(failed)} failed expectation(s): "
        + (", ".join(f"`{name}`" for name in failed) if failed else "none")
        + "."
    )
    lines.append(
        f"- Freshness SLA on corrupted data: stale ratio {corrupted_freshness.get('stale_ratio', 0):.2%} → "
        f"`is_fresh={corrupted_freshness.get('is_fresh')}`; latest paper moved to {corrupted_freshness.get('latest_published')} "
        "because the newest records were dropped."
    )
    lines.append(
        f"- Repaired data re-passed the gate (`success={repaired_quality.get('success')}`, "
        f"`is_fresh={repaired_freshness.get('is_fresh')}`)."
    )
    if dataset_check:
        lines.append(
            f"- Idempotency: repaired dataset fingerprint `{dataset_check.get('repaired_fingerprint', '')[:12]}` "
            f"{'matches' if dataset_check.get('matches_baseline') else 'does NOT match'} the baseline fingerprint "
            f"`{dataset_check.get('baseline_fingerprint', '')[:12]}`; a second rebuild from raw gave "
            f"{'the same' if dataset_check.get('rebuild_is_deterministic') else 'a DIFFERENT'} fingerprint."
        )
    return lines


def _silent_failure_lines(corrupted_answers: list[dict[str, Any]] | None) -> list[str]:
    if not corrupted_answers:
        return []
    wrong = [item for item in corrupted_answers if item["token_f1"] < 1.0 or not item["retrieval_hit"]]
    answered = sum(1 for item in corrupted_answers if str(item["answer"]).strip())
    rows = [
        [
            item["id"],
            item["question_type"],
            item["retrieval_hit"],
            item["ground_truth"][:70],
            str(item["answer"])[:70] or "(empty)",
            round(float(item["token_f1"]), 4),
        ]
        for item in wrong
    ]
    return [
        "### Why this is a silent failure",
        "",
        f"On the corrupted index the QA path returned an answer for {answered}/{len(corrupted_answers)} questions and raised "
        f"no error, yet {len(wrong)} answers were wrong or degraded. Nothing in the serving path signalled a problem; "
        "only the GX gate and the freshness SLA did.",
        "",
        *_table(["ID", "Type", "Hit", "Ground truth", "Corrupted answer", "Token F1"], rows),
        "",
    ]


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    corruption_log: dict[str, Any] | None = None,
    dataset_check: dict[str, Any] | None = None,
    baseline_quality: dict[str, Any] | None = None,
    corrupted_answers: list[dict[str, Any]] | None = None,
) -> None:
    """Write the Baseline vs Corrupted vs Repaired comparison report."""
    states = [("Baseline", baseline_metrics), ("Corrupted", corrupted_metrics), ("Repaired", repaired_metrics)]
    metric_rows = [
        [label, baseline_metrics.get(key), corrupted_metrics.get(key), repaired_metrics.get(key),
         _delta(corrupted_metrics.get(key), baseline_metrics.get(key)), _delta(repaired_metrics.get(key), baseline_metrics.get(key))]
        for key, label in HEADLINE_METRICS
    ]
    metric_rows.append(["Samples", baseline_metrics.get("samples"), corrupted_metrics.get("samples"), repaired_metrics.get("samples"), "—", "—"])

    baseline_quality = baseline_quality or {}
    signal_rows = [
        ["Rows validated", baseline_quality.get("row_count"), corrupted_quality.get("row_count"), repaired_quality.get("row_count")],
        ["GX suite success", baseline_quality.get("success"), corrupted_quality.get("success"), repaired_quality.get("success")],
        [
            "Expectations passed",
            f"{baseline_quality.get('successful_expectations', '—')}/{baseline_quality.get('evaluated_expectations', '—')}",
            f"{corrupted_quality.get('successful_expectations')}/{corrupted_quality.get('evaluated_expectations')}",
            f"{repaired_quality.get('successful_expectations')}/{repaired_quality.get('evaluated_expectations')}",
        ],
        ["Latest published", (baseline_quality.get("freshness") or {}).get("latest_published"), corrupted_freshness.get("latest_published"), repaired_freshness.get("latest_published")],
        ["Stale ratio", (baseline_quality.get("freshness") or {}).get("stale_ratio"), corrupted_freshness.get("stale_ratio"), repaired_freshness.get("stale_ratio")],
        ["is_fresh", (baseline_quality.get("freshness") or {}).get("is_fresh"), corrupted_freshness.get("is_fresh"), repaired_freshness.get("is_fresh")],
    ]

    expectation_rows = []
    corrupted_by_name = {(item["expectation"], item.get("column")): item for item in corrupted_quality.get("expectations", [])}
    for item in repaired_quality.get("expectations", []):
        bad = corrupted_by_name.get((item["expectation"], item.get("column")), {})
        expectation_rows.append([item["expectation"], item.get("column") or "(table)", bad.get("success"), bad.get("unexpected_count"), item["success"]])

    lines = [
        "# Corruption Report — Baseline vs Corrupted vs Repaired",
        "",
        f"_Generated at {now_utc().isoformat()}_ — all three states are evaluated on the same `data/eval/test_set.json`.",
        "",
        "## 1. Headline metrics (3 states)",
        "",
        *_table(["Metric", "Baseline", "Corrupted", "Repaired", "Δ Corrupted", "Δ Repaired"], metric_rows),
        "",
        "### Token F1 by question type",
        "",
        *_table(["Question type", "Baseline", "Corrupted", "Repaired"], _question_type_rows(states, "mean_token_f1")),
        "",
        "### Retrieval hit rate by question type",
        "",
        *_table(["Question type", "Baseline", "Corrupted", "Repaired"], _question_type_rows(states, "retrieval_hit_rate")),
        "",
        "## 2. Observability signals",
        "",
        *_table(["Signal", "Baseline", "Corrupted", "Repaired"], signal_rows),
        "",
        "### Expectation-level detail",
        "",
        *_table(["Expectation", "Column", "Corrupted success", "Corrupted unexpected", "Repaired success"], expectation_rows),
        "",
    ]

    if corruption_log:
        lines += [
            "## 3. Injected corruptions",
            "",
            f"Seed `{corruption_log.get('seed')}` — {corruption_log.get('input_rows')} clean rows → {corruption_log.get('output_rows')} corrupted rows.",
            "",
            *_table(
                ["#", "Corruption", "Rows", "Description"],
                [[number, item["corruption_type"], item["affected_rows"], item["description"]] for number, item in enumerate(corruption_log.get("corruptions", []), start=1)],
            ),
            "",
        ]

    lines += [
        "## 4. Analysis",
        "",
        *_analysis_lines(
            baseline_metrics, corrupted_metrics, repaired_metrics,
            corrupted_quality, corrupted_freshness, repaired_quality, repaired_freshness, dataset_check,
        ),
        "",
        *_silent_failure_lines(corrupted_answers),
        "### How the repair works",
        "",
        "Repair never patches the corrupted table. It rebuilds the clean dataset from the immutable raw snapshot "
        "(`data/raw/crossref_records.json`) with the same cleaning code, re-validates it with the GX gate and re-indexes "
        "it into a separate `papers-repaired` collection. Because the input and the transformation are both deterministic, "
        "running the repair any number of times yields the same dataset.",
        "",
    ]
    write_text(report_path, "\n".join(lines))
