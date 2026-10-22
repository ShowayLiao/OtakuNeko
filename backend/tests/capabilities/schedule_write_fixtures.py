"""Synthetic external payloads; real calendar converters and SQL stay active."""

from datetime import datetime, timezone


def calendar_payload(source_id: int = 799) -> list[dict]:
    return [
        {
            "weekday": {"id": day},
            "items": [
                {
                    "id": source_id,
                    "name": "Synthetic calendar anime",
                    "name_cn": "Synthetic calendar",
                    "type": 2,
                    "summary": "Synthetic calendar summary",
                    "air_weekday": day,
                    "images": {},
                    "rating": {},
                    "collection": {},
                }
            ]
            if day == 2
            else [],
        }
        for day in range(1, 8)
    ]


def metadata_payload(source_id: int = 799) -> dict:
    begin = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "items": [
            {
                "title": "Synthetic calendar anime",
                "begin": begin,
                "sites": [
                    {"site": "bangumi", "id": str(source_id)},
                    {"site": "bilibili", "begin": begin},
                ],
            }
        ]
    }
