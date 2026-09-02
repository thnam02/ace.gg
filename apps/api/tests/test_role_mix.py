from app.metrics.cir.role_mix import build_role_mix


def test_role_mix_highlights_cir_main_and_keeps_real_offroles() -> None:
    mix = build_role_mix(
        {"Controller": 600, "Sentinel": 400, "Duelist": 40, "Unknown": 20},
        "Controller",
    )
    assert [item.role for item in mix] == ["Controller", "Sentinel"]
    assert mix[0].is_main is True
    assert mix[1].is_main is False
    assert round(mix[0].share, 2) == 0.58
    assert round(mix[1].share, 2) == 0.38


def test_role_mix_keeps_cir_main_even_without_map_counts() -> None:
    mix = build_role_mix({}, "Initiator")
    assert len(mix) == 1
    assert mix[0].role == "Initiator"
    assert mix[0].is_main is True
    assert mix[0].rounds == 0
