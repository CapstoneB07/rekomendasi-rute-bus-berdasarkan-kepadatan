from services.sensitivity_plan import build_sensitivity_requests, extract_summary_row


def _catalog_row(**overrides):
    row = {
        "scenario_type": "C",
        "origin": "A",
        "destination": "C",
        "time_period": "08h00",
        "density_delta": 0.7,
        "candidate_count": 2,
    }
    row.update(overrides)
    return row


def test_build_sensitivity_requests_selects_two_per_type_and_sweeps():
    rows = [
        _catalog_row(scenario_type="C", origin="C1", density_delta=0.7),
        _catalog_row(scenario_type="C", origin="C2", density_delta=0.6),
        _catalog_row(scenario_type="C", origin="C3", density_delta=0.9),
        _catalog_row(scenario_type="B", origin="B1", density_delta=0.2),
    ]

    requests = build_sensitivity_requests(rows, replications=500)

    c_requests = [r for r in requests if r["scenario_type"] == "C"]
    assert len(c_requests) == 2 * 4, "2 OD pairs × 4 weight sweeps"

    labels = {r["label"] for r in c_requests}
    assert any("C3" in label for label in labels), "highest delta pair must be selected"
    assert all(r["request_body"]["replications"] == 500 for r in requests)


def test_extract_summary_row_reads_paired_comparison():
    plan = {
        "weight_label": "w060",
        "scenario_type": "C",
        "origin": "A",
        "destination": "C",
        "time_period": "08h00",
    }
    result = {
        "routing_sensitivity": {
            "scenarios": [{
                "replications": [{"replication_index": 0}],
                "paired_comparison": {
                    "route_change_rate": 0.78,
                    "mean_density_delta": 0.32,
                    "median_density_delta": 0.31,
                    "p05_density_delta": 0.10,
                    "p95_density_delta": 0.55,
                    "mean_extra_time_seconds": 246.0,
                    "improvement_rate": 0.75,
                },
                "baseline_density_mean": 0.9,
                "recommended_density_mean": 0.58,
            }]
        }
    }

    row = extract_summary_row(plan, result)

    assert row["divergence_rate"] == 0.78
    assert row["mean_extra_time_minutes"] == 4.1
    assert row["replications"] == 1
