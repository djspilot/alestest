from manufacturing_pipeline.api import config


def test_api_default_disable_stages_cover_viewer_noise():
    assert "profile_router" in config.DEFAULT_DISABLE_STAGES
    assert "detect_holes_pre_unfold" in config.DEFAULT_DISABLE_STAGES
    assert "profile_router" in config.DISABLE_STAGES
    assert "detect_holes_pre_unfold" in config.DISABLE_STAGES


def test_api_valid_stage_keys_include_profile_router():
    assert "profile_router" in config.VALID_STAGE_KEYS
