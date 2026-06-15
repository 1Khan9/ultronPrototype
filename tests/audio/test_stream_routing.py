"""Routing-matrix regression tests for the stream output fan-out.

Verifies the architectural guarantees the stream setup relies on, WITHOUT a
live device or the full pipeline:

* normal speech tees to BOTH the EVERYTHING mirror (broadcast) AND the waveform
  overlay -- never to the team device;
* the relay/team path plays ONLY to the device it is handed (the team device);
* the EVERYTHING mirror emits every clip it is given to its configured device.
"""
from __future__ import annotations

import numpy as np

import kenning.audio.broadcast as bc
import kenning.audio.waveform as wf
from kenning.tts import kokoro_engine as ke
from kenning.audio.relay_speech import play_to_device


def _pcm(n=2400):
    return (np.sin(np.linspace(0, 40, n)) * 10000).astype(np.int16)


def test_normal_speech_tees_to_everything_and_waveform(monkeypatch):
    """kokoro _broadcast_submit fans out to broadcast + waveform, never team."""
    seen = {"broadcast": 0, "waveform": 0}

    monkeypatch.setattr(bc, "submit", lambda pcm, sr: seen.__setitem__(
        "broadcast", seen["broadcast"] + 1))
    monkeypatch.setattr(wf, "submit", lambda pcm, sr: seen.__setitem__(
        "waveform", seen["waveform"] + 1))

    ke._broadcast_submit(_pcm(), 24000)
    assert seen == {"broadcast": 1, "waveform": 1}


def test_tee_is_fail_open(monkeypatch):
    """A raising tee must never propagate into the playback path."""
    def boom(pcm, sr):
        raise RuntimeError("device exploded")

    monkeypatch.setattr(bc, "submit", boom)
    monkeypatch.setattr(wf, "submit", boom)
    ke._broadcast_submit(_pcm(), 24000)      # must not raise


def test_everything_mirror_emits_to_configured_device():
    """BroadcastSink streams whatever it is given to its configured device."""
    writes = []

    class FakeStream:
        def start(self):
            pass

        def write(self, block):
            writes.append(np.asarray(block).copy())

        def stop(self):
            pass

        def close(self):
            pass

    sink = bc.BroadcastSink(
        resolver=lambda spec, kind: 99,                       # pretend device idx
        stream_factory=lambda **kw: FakeStream(),
    )
    sink.configure("Voicemeeter AUX Input")
    # BOTH a private-style and a team-style clip go to the EVERYTHING device.
    sink.submit(_pcm(1200), 24000)
    sink.submit(_pcm(1800), 24000)
    import time
    for _ in range(50):
        if len(writes) >= 2:
            break
        time.sleep(0.02)
    sink.close()
    assert writes, "everything mirror wrote nothing"
    assert writes[0].ndim == 2 and writes[0].shape[1] == 2   # mono -> stereo


def test_team_path_plays_only_to_given_device():
    """relay play_to_device opens exactly the device index it is handed."""
    opened = {}

    class FakeStream:
        def start(self):
            opened["started"] = True

        def write(self, data):
            arr = np.asarray(data)
            opened["wrote"] = len(arr)
            opened["write_shape"] = arr.shape

        def stop(self):
            pass

        def close(self):
            pass

    def factory(**kw):
        opened["device"] = kw.get("device")
        opened["channels"] = kw.get("channels")
        return FakeStream()

    secs = play_to_device(_pcm(4800), 24000, 19, stream_factory=factory)
    assert opened["device"] == 19            # the team device, and only that
    assert opened.get("started") and opened.get("wrote")
    assert secs > 0
    # Relay must feed the VoiceMeeter strip as STEREO -- a mono (1-channel)
    # write makes WASAPI auto-convert up-mix 1->2 channels on top of the
    # 24k->48k resample, which statics/distorts on the B1 VAIO endpoint.
    assert opened["channels"] == 2
    assert opened["write_shape"][1] == 2     # mono PCM was widened to stereo
