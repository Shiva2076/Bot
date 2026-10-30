from runtime_environment import RuntimeEnvironment


def test_vercel_disables_background_workers():
    runtime = RuntimeEnvironment({"VERCEL": "1"})
    assert runtime.is_vercel is True
    assert runtime.should_start_background_workers is False


def test_non_vercel_enables_background_workers():
    runtime = RuntimeEnvironment({})
    assert runtime.is_vercel is False
    assert runtime.should_start_background_workers is True
