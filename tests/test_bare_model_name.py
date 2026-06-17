from bench_cli.resolver import bare_model_name, bare_name


def test_bare_model_name_strips_first_segment():
    assert bare_model_name("openai/thinking") == "thinking"
    assert bare_model_name("minimaxai/minimax-m3") == "minimax-m3"
    assert bare_model_name("nvidia/nemotron-3-ultra-550b-a55b") == "nemotron-3-ultra-550b-a55b"


def test_bare_model_name_no_slash_returns_whole():
    assert bare_model_name("nemotron-ultra-550b") == "nemotron-ultra-550b"


def test_bare_name_delegates_to_bare_model_name():
    # bare_name should now strip the first segment, not just the openai/ prefix
    assert bare_name("openai/thinking") == "thinking"
    assert bare_name("minimaxai/minimax-m3") == "minimax-m3"
