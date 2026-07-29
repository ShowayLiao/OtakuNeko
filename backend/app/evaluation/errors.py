"""Safe error summaries for reports and CI output."""


def safe_error(exc: BaseException, code: str) -> str:
    """Return a stable error type/code without exception payloads."""
    return f"{type(exc).__name__}: {code}"
