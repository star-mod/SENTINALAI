from collections import OrderedDict
import requests

from sentinel_ai.detectors.base import Detection
from sentinel_ai import pipeline


def make_detection():
    return Detection(
        incident_type="fall_collapse",
        camera_id="cam_01",
        confidence=0.91,
        severity="high",
        timestamp="2026-10-16T10:00:00+00:00",
        track_ids=[4],
        verification={"window_seconds": 2.5, "frames_confirmed": 22, "frames_required": 15},
        description="Temporal fall candidate",
    )


def test_build_incident_payload_maps_detection_and_existing_evidence_urls():
    payload = pipeline.build_incident_payload(
        detection=make_detection(),
        camera_name="Central Plaza",
        location={"lat": 12.97, "lng": 77.59, "label": "Central Plaza"},
        snapshot_url="/media/snapshots/inc_cam_01_12345.jpg",
        clip_url="/media/clips/inc_cam_01_12345.mp4",
        event_id="evt_test_frame_123",
    )

    assert payload == {
        "camera_id": "cam_01",
        "camera_name": "Central Plaza",
        "location": {"lat": 12.97, "lng": 77.59, "label": "Central Plaza"},
        "type": "fall_collapse",
        "confidence": 0.91,
        "severity": "high",
        "timestamp": "2026-10-16T10:00:00+00:00",
        "snapshot_url": "/media/snapshots/inc_cam_01_12345.jpg",
        "clip_url": "/media/clips/inc_cam_01_12345.mp4",
        "event_id": "evt_test_frame_123",
        "notes": "Temporal fall candidate",
        "verification": {"window_seconds": 2.5, "frames_confirmed": 22, "frames_required": 15},
    }


def test_send_incident_to_n8n_posts_contract_and_auth_header(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            captured["checked_status"] = True

    def fake_post(url, *, json, headers, timeout):
        captured.update(url=url, payload=json, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(pipeline.requests, "post", fake_post)
    payload = pipeline.build_incident_payload(
        make_detection(),
        "Central Plaza",
        {"lat": 12.97, "lng": 77.59, "label": "Central Plaza"},
        "/media/snapshots/inc_1.jpg",
        "/media/clips/inc_1.mp4",
        "evt_test_frame_123",
    )

    delivered = pipeline.send_incident_to_n8n(payload, "https://example.test/hook", "test-secret")

    assert delivered is True
    assert captured["url"] == "https://example.test/hook"
    assert captured["payload"] == payload
    assert captured["headers"] == {"X-Webhook-Secret": "test-secret"}
    assert captured["timeout"] == pipeline.N8N_WEBHOOK_TIMEOUT_SECONDS
    assert captured["checked_status"] is True


def test_send_incident_to_n8n_reports_http_failure_without_raising(monkeypatch, caplog):
    def fake_post(*args, **kwargs):
        raise requests.Timeout("test timeout")

    monkeypatch.setattr(pipeline.requests, "post", fake_post)
    payload = {"camera_id": "cam_01", "type": "fall_collapse"}

    delivered = pipeline.send_incident_to_n8n(payload, "https://example.test/hook", "test-secret")

    assert delivered is False
    assert "N8N webhook delivery failed" in caplog.text
    assert "test-secret" not in caplog.text
    assert "test timeout" not in caplog.text


def test_send_incident_to_n8n_does_not_send_without_secret(monkeypatch, caplog):
    def unexpected_post(*args, **kwargs):
        raise AssertionError("HTTP request must not be sent without the webhook secret")

    monkeypatch.setattr(pipeline.requests, "post", unexpected_post)
    delivered = pipeline.send_incident_to_n8n(
        {"camera_id": "cam_01", "type": "fall_collapse"},
        "https://example.test/hook",
        None,
    )

    assert delivered is False
    assert "N8N_WEBHOOK_SECRET is not configured" in caplog.text


def test_send_incident_to_n8n_does_not_send_without_url(monkeypatch, caplog):
    def unexpected_post(*args, **kwargs):
        raise AssertionError("HTTP request must not be sent without an explicit webhook URL")

    monkeypatch.setattr(pipeline.requests, "post", unexpected_post)
    delivered = pipeline.send_incident_to_n8n(
        {"camera_id": "cam_01", "type": "fall_collapse"},
        None,
        "test-secret",
    )

    assert delivered is False
    assert "N8N_WEBHOOK_URL is not configured" in caplog.text


def test_local_video_event_id_is_stable_for_replayed_frame(tmp_path):
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"test fixture")
    first = pipeline.build_event_id("cam_01", "fall_collapse", str(source), 145)
    replay = pipeline.build_event_id("cam_01", "fall_collapse", str(source), 145)
    other_frame = pipeline.build_event_id("cam_01", "fall_collapse", str(source), 146)
    other_type = pipeline.build_event_id("cam_01", "physical_altercation", str(source), 145)

    assert first == replay
    assert first != other_frame
    assert first != other_type


def test_live_source_event_ids_are_fresh():
    first = pipeline.build_event_id("cam_01", "fall_collapse", "rtsp://camera/live", 145)
    second = pipeline.build_event_id("cam_01", "fall_collapse", "rtsp://camera/live", 145)

    assert first != second


def test_dispatched_event_cache_suppresses_replay_and_stays_bounded(monkeypatch):
    cache = OrderedDict()
    assert pipeline.claim_event_id(cache, "evt_replayed") is True
    assert pipeline.claim_event_id(cache, "evt_replayed") is False

    monkeypatch.setattr(pipeline, "EVENT_ID_CACHE_SIZE", 2)
    pipeline.claim_event_id(cache, "evt_second")
    pipeline.claim_event_id(cache, "evt_third")
    assert len(cache) == 2
    assert "evt_replayed" not in cache


def test_webhook_delivery_is_single_attempt_on_transient_failure(monkeypatch):
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise requests.Timeout("test")

    monkeypatch.setattr(pipeline.requests, "post", fail_once)
    delivered = pipeline.send_incident_to_n8n(
        {"event_id": "evt_retry_case", "camera_id": "cam_01", "type": "fall_collapse"},
        "https://example.test/hook",
        "test-secret",
    )

    assert delivered is False
    assert calls == 1
