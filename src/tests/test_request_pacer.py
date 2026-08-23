from src.infrastructure.request_pacer import RequestPacer


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _pacer(clock: FakeClock, interval: float = 12.0) -> RequestPacer:
    return RequestPacer(interval, sleep=clock.sleep, monotonic=clock.monotonic)


class TestRequestPacer:
    def test_初回は待たない(self) -> None:
        clock = FakeClock()

        _pacer(clock).wait()

        assert clock.slept == []

    def test_経過時間を差し引いた分だけ待つ(self) -> None:
        clock = FakeClock()
        pacer = _pacer(clock)

        pacer.wait()
        clock.advance(5.0)
        pacer.wait()

        assert clock.slept == [7.0]

    def test_間隔以上経過していれば待たない(self) -> None:
        clock = FakeClock()
        pacer = _pacer(clock)

        pacer.wait()
        clock.advance(20.0)
        pacer.wait()

        assert clock.slept == []

    def test_間隔がゼロなら待たない(self) -> None:
        clock = FakeClock()
        pacer = _pacer(clock, interval=0)

        pacer.wait()
        pacer.wait()

        assert clock.slept == []

    def test_連続呼び出しでも一定間隔を保つ(self) -> None:
        clock = FakeClock()
        pacer = _pacer(clock)

        for _ in range(3):
            pacer.wait()
            clock.advance(2.0)

        assert clock.slept == [10.0, 10.0]

    def test_外部で待たされた時間も間隔に数える(self) -> None:
        clock = FakeClock()
        pacer = _pacer(clock)

        pacer.wait()
        clock.advance(300.0)
        pacer.wait()

        assert clock.slept == []
