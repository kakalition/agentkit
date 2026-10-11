from agentkit.guardrails import is_loopback, warn_if_exposed


def test_is_loopback():
    assert is_loopback("127.0.0.1") is True
    assert is_loopback("localhost") is True
    assert is_loopback(None) is True
    assert is_loopback("0.0.0.0") is False
    assert is_loopback("10.0.0.1") is False


def test_warn_if_exposed(capsys):
    warn_if_exposed("0.0.0.0", "svc")
    assert "WARNING" in capsys.readouterr().err
    warn_if_exposed("127.0.0.1", "svc")
    assert capsys.readouterr().err == ""
