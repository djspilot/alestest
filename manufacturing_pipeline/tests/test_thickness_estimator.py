from manufacturing_pipeline.analysis.thickness_estimator import (
    ThicknessCandidate,
    ThicknessEstimate,
    select_best_thickness_candidate,
)


def test_select_best_candidate_prefers_consensus_bucket():
    candidates = [
        ThicknessCandidate("planar_opposites", 1.0, 0.62, 1.0),
        ThicknessCandidate("cylindrical_pairs", 5.0, 0.87, 2.2),
        ThicknessCandidate("bbox_min_dim", 5.0, 0.42, 0.45),
        ThicknessCandidate("volume_planar_area", 12.5, 0.28, 0.25),
    ]

    bucket_mm, selected, bucket_votes = select_best_thickness_candidate(candidates)

    assert bucket_mm == 5.0
    assert selected is not None
    assert selected.method == "cylindrical_pairs"
    assert bucket_votes[5.0] > bucket_votes[1.0]
    assert bucket_votes[5.0] > bucket_votes[12.5]


def test_select_best_candidate_prefers_highest_confidence_within_bucket():
    candidates = [
        ThicknessCandidate("bbox_min_dim", 5.0, 0.40, 0.4),
        ThicknessCandidate("cylindrical_pairs", 5.1, 0.82, 1.8),
    ]

    bucket_mm, selected, _ = select_best_thickness_candidate(candidates)

    assert bucket_mm == 5.0
    assert selected is not None
    assert selected.method == "cylindrical_pairs"


def test_thickness_estimate_should_override_small_wrong_value():
    estimate = ThicknessEstimate(
        thickness_mm=5.0,
        method="cylindrical_pairs",
        confidence=0.86,
        candidates=(),
        bucket_votes={5.0: 2.4},
    )

    assert estimate.should_override(1.0)
    assert not estimate.should_override(5.0)
    assert not estimate.should_override(4.9)