import logging

from agentkit.logging import (
    RedactingJsonFormatter,
    get_request_id,
    redact,
    request_context,
    setup_logging,
)


def test_redact_secrets_and_amounts():
    text = "key sk-abcdef123456 paid $1,234.56 and 42.00 total"
    out = redact(text)
    assert "sk-abcdef123456" not in out
    assert "$1,234.56" not in out
    assert "[redacted]" in out
    assert "[amount]" in out


def test_request_context_sets_and_clears():
    assert get_request_id() is None
    with request_context("abc123") as rid:
        assert rid == "abc123"
        assert get_request_id() == "abc123"
    assert get_request_id() is None


def test_json_formatter_includes_request_id_and_redacts():
    formatter = RedactingJsonFormatter()
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "spent $5.00", None, None)
    with request_context("rid-1"):
        payload = formatter.format(record)
    assert '"request_id": "rid-1"' in payload
    assert "$5.00" not in payload


def test_setup_logging_json(capsys):
    class S:
        log_level = "INFO"
        log_json = True

    setup_logging(S())
    logging.getLogger("agentkit.test").info("hello $9.99")
    err = capsys.readouterr().err
    assert '"level": "INFO"' in err
    assert "$9.99" not in err
