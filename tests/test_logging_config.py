"""JSON log lines for the container console (util/logging_config.py)."""
import json
import logging

from util.logging_config import JsonFormatter, scrub, use_json_logs


def _record(msg, *args, exc_info=None):
    return logging.LogRecord("SCMarketBot", logging.INFO, __file__, 10, msg, args, exc_info)


def test_command_used_stays_one_json_line_with_same_text():
    line = JsonFormatter().format(_record("command_used name=%s guild=%s", "listing create", 123))
    assert "\n" not in line
    entry = json.loads(line)
    assert entry["msg"] == "command_used name=listing create guild=123"
    assert entry["level"] == "info"
    assert entry["ts"].endswith("Z")


def test_exception_traceback_is_inside_the_line():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        line = JsonFormatter().format(_record("failed", exc_info=sys.exc_info()))
    assert "\n" not in line
    err = json.loads(line)["error"]
    assert err["name"] == "ValueError"
    assert "Traceback" in err["stack"] and "boom" in err["stack"]


def test_scrubs_tokens():
    assert scrub("Authorization: Bearer abc.def") == "Authorization: Bearer [REDACTED]"
    assert scrub("x?code=123&state=y") == "x?code=[REDACTED]&state=y"
    assert scrub("jwt eyJa.eyJb.c") == "jwt [REDACTED]"


def test_log_format_env_overrides(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    assert use_json_logs() is False
    monkeypatch.setenv("LOG_FORMAT", "json")
    assert use_json_logs() is True
