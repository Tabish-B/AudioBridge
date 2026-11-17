# AudioBridge annotation JSON

AudioBridge exports a UTF-8 JSON document with a `schema_version`. Times are decimal seconds, and intervals use start-inclusive, end-exclusive bounds. Each segment refers to a media item and a tier by ID. Media records store the file name and duration, not local folder paths.

```json
{
  "format": "AudioBridge segment annotations",
  "schema_version": 1,
  "app_version": "4.0.0",
  "time_unit": "seconds",
  "interval_convention": "start inclusive, end exclusive",
  "media": [
    {"id": "media_1", "file_name": "interview.wav", "duration_seconds": 84.5}
  ],
  "tiers": [
    {"id": "tier_1", "name": "Transcript"}
  ],
  "annotations": [
    {
      "id": "annotation_1",
      "media_id": "media_1",
      "tier_id": "tier_1",
      "start_seconds": 1.25,
      "end_seconds": 2.8,
      "text": "example words"
    }
  ]
}
```

Version 1 supports independent tiers and overlapping intervals. It doesn't encode tier parent/child constraints, participants, controlled vocabularies, or word-level alignment. The JSON is AudioBridge's own interchange format and isn't intended to be opened as an ELAN `.eaf` file.
