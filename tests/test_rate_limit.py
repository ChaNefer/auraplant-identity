from identity_core.rate_limit import SlidingWindowLimiter


def test_sliding_window_blocks_sixth_hit():
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60)
    key = "ip:1.2.3.4"
    for _ in range(5):
        assert limiter.hit(key) is True
    assert limiter.hit(key) is False
