"""Portable JSON structure for AudioBridge's interval annotations."""

from pathlib import Path


def annotation_document(rows, tier_names, app_version):
    """Build a self-contained, versioned document without exposing local paths."""
    media_ids = {}
    media = []
    tiers = [{"id": f"tier_{index + 1}", "name": name} for index, name in enumerate(tier_names)]
    tier_ids = {tier["name"]: tier["id"] for tier in tiers}
    annotations = []

    for index, row in enumerate(rows, 1):
        source = str(Path(row["file"]).resolve())
        if source not in media_ids:
            media_id = f"media_{len(media_ids) + 1}"
            media_ids[source] = media_id
            item = {"id": media_id, "file_name": Path(source).name}
            if row.get("duration_seconds") is not None:
                item["duration_seconds"] = round(float(row["duration_seconds"]), 6)
            media.append(item)
        tier_name = row["tier"]
        if tier_name not in tier_ids:
            tier_ids[tier_name] = f"tier_{len(tier_ids) + 1}"
            tiers.append({"id": tier_ids[tier_name], "name": tier_name})
        start = float(row["start_seconds"])
        end = float(row["end_seconds"])
        if start < 0 or end <= start:
            raise ValueError("Annotation intervals must have a non-negative start and a later end.")
        annotations.append(
            {
                "id": f"annotation_{index}",
                "media_id": media_ids[source],
                "tier_id": tier_ids[tier_name],
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "text": row["label"],
            }
        )

    return {
        "format": "AudioBridge segment annotations",
        "schema_version": 1,
        "app_version": app_version,
        "time_unit": "seconds",
        "interval_convention": "start inclusive, end exclusive",
        "media": media,
        "tiers": tiers,
        "annotations": annotations,
    }
