from xon.workstation import budget


def test_parse_budget():
    assert budget.parse_budget("30m") == 0.5
    assert budget.parse_budget("8h") == 8
    assert budget.parse_budget("2d") == 48
    assert budget.hours_from_dollars(40, 2.0) == 20


def test_size_run_scales_and_refuses():
    bench = {"tokens_per_s": 15000.0, "flops_per_s": 6 * 1.5e6 * 15000.0, "params": 1.5e6, "device": "cpu", "steps": 100}
    small = budget.size_run(0.5, "A", bench=bench)
    big = budget.size_run(8, "A", bench=bench)
    assert small["fits"] and big["params"] > small["params"] and big["tokens"] > small["tokens"]
    assert 15 <= small["tokens_per_param"] <= 21
    tiny = budget.size_run(0.0005, "B", bench=bench)
    assert not tiny["fits"] and "budget too small" in tiny["reason"]
