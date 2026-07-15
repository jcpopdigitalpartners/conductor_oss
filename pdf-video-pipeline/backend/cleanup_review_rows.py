from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def database_path() -> Path:
    configured = os.getenv("DATABASE_PATH", "./data/pdf_video_pipeline.sqlite3")
    return Path(configured).resolve()


def load_reviews(connection: sqlite3.Connection) -> list[dict[str, str | None]]:
    rows = connection.execute("SELECT review_id, payload_json FROM reviews").fetchall()
    reviews: list[dict[str, str | None]] = []
    for review_id, payload_json in rows:
        payload = json.loads(payload_json)
        creative_brief = payload.get("creative_brief") or {}
        reviews.append(
            {
                "review_id": review_id,
                "requested_by": payload.get("requested_by"),
                "summary": creative_brief.get("summary"),
            }
        )
    return reviews


def cleanup_reviews() -> None:
    db_path = database_path()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_name(f"{db_path.stem}.cleanup-{timestamp}{db_path.suffix}")
    shutil.copy2(db_path, backup_path)

    connection = sqlite3.connect(db_path)
    try:
        reviews = load_reviews(connection)
        non_conductor_summaries = {
            review["summary"] for review in reviews if review["requested_by"] != "conductor"
        }
        review_ids_to_delete = [
            review["review_id"]
            for review in reviews
            if review["requested_by"] == "review-ui-test"
            or (
                review["requested_by"] == "conductor"
                and review["summary"] in non_conductor_summaries
            )
        ]

        connection.executemany(
            "DELETE FROM reviews WHERE review_id = ?",
            [(review_id,) for review_id in review_ids_to_delete if review_id is not None],
        )
        connection.commit()

        remaining = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    finally:
        connection.close()

    print(f"backup={backup_path}")
    print(f"deleted={len(review_ids_to_delete)}")
    print(f"remaining={remaining}")


if __name__ == "__main__":
    cleanup_reviews()
