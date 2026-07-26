"""Keep secrets out of the logs.

uvicorn's access log writes the full request line, query string included. Two
things in this app travel in a URL and are worth something to whoever can read
the logs (Railway operators, any future log shipper, a leaked dashboard):

  • /admin/growth?secret=…      the investor-map GROWTH_SECRET
  • /auth/tg-login/poll/{nonce} a live login nonce — for its 120s TTL it is the
                               bearer capability that collects a user's tokens

Neither should be recoverable from a log line. This installs a logging filter
that rewrites those values to *** before anything is emitted, on the record
itself (not the formatter), so every handler and log shipper sees the redacted
form.
"""
import logging
import re

# `secret=`, `token=`, `password=`, `api_key=`/`api-key=` in a query string, and
# the nonce path segment of the login poll endpoint.
_QUERY_SECRET = re.compile(
    r"((?:^|[?&])(?:secret|token|password|api[_-]?key|bot_secret)=)[^&\s\"']+",
    re.IGNORECASE,
)
_LOGIN_NONCE = re.compile(r"(/auth/tg-login/poll/)[^/\s\"'?]+", re.IGNORECASE)

_REDACTED = "***"


def redact(text: str) -> str:
    text = _QUERY_SECRET.sub(rf"\1{_REDACTED}", text)
    return _LOGIN_NONCE.sub(rf"\1{_REDACTED}", text)


class RedactSecretsFilter(logging.Filter):
    """Scrubs secret-bearing URLs from a record before it is formatted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        # uvicorn.access passes the request line through record.args, so the
        # message template alone is never enough — walk the args too.
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                k: (redact(v) if isinstance(v, str) else v) for k, v in record.args.items()
            }
        return True


def install_log_redaction() -> None:
    """Attach the filter to the app's and uvicorn's loggers and their handlers.

    Called from the FastAPI lifespan: uvicorn configures its own loggers before
    application startup, so by then there is something to attach to. Idempotent.
    """
    filt = RedactSecretsFilter()
    loggers = [logging.getLogger()] + [
        logging.getLogger(name)
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "rezerv")
    ]
    for lg in loggers:
        if not any(isinstance(f, RedactSecretsFilter) for f in lg.filters):
            lg.addFilter(filt)
        for handler in lg.handlers:
            if not any(isinstance(f, RedactSecretsFilter) for f in handler.filters):
                handler.addFilter(filt)
