"""Contracts and safe view projection for Media's three read actions."""

from copy import deepcopy
import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

READ_ACTIONS = frozenset({"library_status", "list_rss_feeds", "list_rss_rules"})
INPUT_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


_STRING = {"type": "string"}
_RULE_FIELDS = {
    "addPaused": {"type": ["boolean", "null"]},
    "affectedFeeds": {"type": "array", "items": _STRING},
    "assignedCategory": _STRING,
    "enabled": {"type": "boolean"},
    "episodeFilter": _STRING,
    "ignoreDays": {"type": "integer"},
    "lastMatch": {"type": ["string", "null"]},
    "mustContain": _STRING,
    "mustNotContain": _STRING,
    "previouslyMatchedEpisodes": {"type": "array", "items": _STRING},
    "priority": {"type": "integer"},
    "savePath": _STRING,
    "smartFilter": {"type": "boolean"},
    "torrentContentLayout": {"type": ["string", "null"]},
    "useRegex": {"type": "boolean"},
}


def output_schema(action: str) -> dict[str, Any]:
    if action == "library_status":
        return _object(
            {
                "configured": {"type": "boolean"},
                "provider": {"type": ["string", "null"], "enum": ["qbittorrent", None]},
            },
            ["configured", "provider"],
        )
    if action == "list_rss_feeds":
        return deepcopy(
            _object(
                {
                    "feeds": {
                        "type": "object",
                        "additionalProperties": _object(
                            {"uid": _STRING, "url": _STRING}, ["uid", "url"]
                        ),
                    },
                    "configured": {"type": "boolean"},
                },
                ["feeds", "configured"],
            )
        )
    return deepcopy(
        _object(
            {
                "rules": {
                    "type": "object",
                    "additionalProperties": _object(
                        _RULE_FIELDS, ["enabled", "mustContain"]
                    ),
                }
            },
            ["rules"],
        )
    )


_SECRET_QUERY_KEYS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "passkey",
        "password",
        "secret",
        "key",
        "credential",
        "credentials",
    }
)


class ReadOutputError(ValueError):
    """A provider view cannot be safely serialized for a read caller."""


def safe_url(value: str) -> str:
    """Preserve normal feed URLs while removing embedded authentication."""
    try:
        parts = urlsplit(value)
        query = parse_qsl(parts.query, keep_blank_values=True)
        safe_query = [
            (
                key,
                "[REDACTED]"
                if key.lower().replace("-", "_") in _SECRET_QUERY_KEYS
                else item,
            )
            for key, item in query
        ]
        # Fragments are not sent to a feed server; authentication fragments
        # must not become model-visible observations either.
        fragment = parse_qsl(parts.fragment, keep_blank_values=True)
        safe_fragment = [
            (
                key,
                "[REDACTED]"
                if key.lower().replace("-", "_") in _SECRET_QUERY_KEYS
                else item,
            )
            for key, item in fragment
        ]
        authority = parts.netloc.rsplit("@", 1)[-1]
        if (
            authority == parts.netloc
            and safe_query == query
            and safe_fragment == fragment
        ):
            return value
        return urlunsplit(
            (
                parts.scheme,
                authority,
                parts.path,
                urlencode(safe_query) if safe_query != query else parts.query,
                urlencode(safe_fragment)
                if safe_fragment != fragment
                else parts.fragment,
            )
        )
    except ValueError:
        return "[REDACTED]"


def safe_read_output(action: str, result: dict[str, Any]) -> dict[str, Any]:
    """Copy only the read view; the provider's resources remain untouched."""
    try:
        # Do not stringify arbitrary objects or nonfinite upstream values.
        json.dumps(result, allow_nan=False)
        value = deepcopy(result)
        if action == "list_rss_feeds":
            for feed in value.get("feeds", {}).values():
                feed["url"] = safe_url(feed["url"])
        elif action == "list_rss_rules":
            value["rules"] = {
                name: {key: item for key, item in rule.items() if key in _RULE_FIELDS}
                for name, rule in value.get("rules", {}).items()
            }
            for rule in value["rules"].values():
                if "affectedFeeds" in rule:
                    rule["affectedFeeds"] = [
                        safe_url(url) for url in rule["affectedFeeds"]
                    ]
        return value
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise ReadOutputError("Invalid media read output") from exc
