import threading
import unittest
from unittest.mock import patch

import numpy as np

import live_transcription
from live_transcription import (LONG_SEGMENT_SAMPLES, MAX_SEGMENT_SAMPLES, PAUSE_SAMPLES, SAMPLE_RATE,
                                TAIL_SAMPLES, LiveTranscription, find_segment_end)


def speech(*regions):
    return [{"start": start, "end": end} for start, end in regions]


class FindSegmentEndTests(unittest.TestCase):
    def find(self, length, regions):
        audio = np.zeros(length, dtype=np.float32)
        with patch("live_transcription.get_speech_timestamps", return_value=speech(*regions)):
            return find_segment_end(audio)

    def test_pause_ends_the_phrase_and_keeps_its_final_sound(self):
        self.assertEqual(self.find(50000, [(1000, 30000)]), 30000 + TAIL_SAMPLES)

    def test_speaker_still_talking_is_not_cut(self):
        self.assertIsNone(self.find(50000, [(1000, 50000)]))

    def test_pause_shorter_than_the_limit_is_not_a_cut(self):
        self.assertIsNone(self.find(50000, [(1000, 50000 - PAUSE_SAMPLES + 1)]))

    def test_pause_inside_a_phrase_cuts_after_the_last_speech(self):
        self.assertEqual(self.find(50000, [(0, 8000), (12000, 30000)]), 30000 + TAIL_SAMPLES)

    def test_silence_alone_produces_no_segment(self):
        self.assertIsNone(self.find(50000, []))

    def test_too_little_audio_skips_the_detector(self):
        with patch("live_transcription.get_speech_timestamps") as detector:
            self.assertIsNone(find_segment_end(np.zeros(PAUSE_SAMPLES - 1, dtype=np.float32)))
        detector.assert_not_called()

    def test_long_segment_ends_at_the_last_breath(self):
        length = LONG_SEGMENT_SAMPLES + 1000
        self.assertEqual(self.find(length, [(0, 90000), (94000, length)]), 92000)

    def test_breath_does_not_end_a_short_segment(self):
        self.assertIsNone(self.find(LONG_SEGMENT_SAMPLES - 1000, [(0, 90000), (94000, LONG_SEGMENT_SAMPLES - 1000)]))

    def test_speech_without_breaths_is_cut_at_the_limit(self):
        self.assertEqual(self.find(MAX_SEGMENT_SAMPLES, [(0, MAX_SEGMENT_SAMPLES)]), MAX_SEGMENT_SAMPLES)

    def test_real_detector_finds_nothing_in_silence(self):
        self.assertIsNone(find_segment_end(np.zeros(SAMPLE_RATE, dtype=np.float32)))


class Session:
    """Runs a LiveTranscription whose audio arrives one chunk per poll."""

    def __init__(self, chunks=(), texts=(), can_insert=True, separator="", transcribe_failures=()):
        self.chunks = list(chunks)
        self.texts = iter(texts)
        self.transcribe_failures = list(transcribe_failures)  # None lets that call succeed.
        self.inserted = []
        self.results = []
        self.audio_seen = []
        self.drained = threading.Event()
        self.allow_insert = can_insert
        self.insert_error = None
        self.live = LiveTranscription(self.take_audio, self.transcribe, self.insert,
                                      lambda: self.allow_insert, self.finished, separator)

    def take_audio(self):
        if self.chunks:
            return self.chunks.pop(0)
        self.drained.set()
        return np.zeros(0, dtype=np.float32)

    def transcribe(self, audio):
        failure = self.transcribe_failures.pop(0) if self.transcribe_failures else None
        if failure:
            self.drained.set()
            raise failure
        self.audio_seen.append(np.array(audio))
        return next(self.texts, "")

    def insert(self, text, final):
        if self.insert_error:
            raise self.insert_error
        self.inserted.append((text, final))

    def finished(self, text, error, uninserted):
        self.results.append((text, error, uninserted))

    def run(self, last_audio=None, error=None):
        self.live.start()
        if not self.drained.wait(5):
            raise AssertionError("audio was not consumed")
        self.live.finish(last_audio, error)
        self.live.join(5)
        return self.results[0]


def samples(count, value=0.1):
    return np.full(count, value, dtype=np.float32)


class LiveTranscriptionTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(live_transcription, "POLL_SECONDS", 0.001)
        patcher.start()
        self.addCleanup(patcher.stop)

    def cut_every_chunk(self):
        patcher = patch("live_transcription.find_segment_end", side_effect=lambda audio: len(audio) or None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def never_cut(self):
        patcher = patch("live_transcription.find_segment_end", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_phrase_is_inserted_while_recording_and_enter_waits_for_the_end(self):
        self.cut_every_chunk()
        session = Session([samples(10), samples(20)], ["Unu.", "Doi."])
        text, error, uninserted = session.run()
        self.assertEqual(session.inserted, [("Unu.", False), ("Doi.", False), ("", True)])
        self.assertEqual((text, error, uninserted), ("Unu. Doi.", None, ""))

    def test_recording_without_pause_is_transcribed_once_at_the_end(self):
        self.never_cut()
        session = Session([samples(10)], ["Tot textul."])
        text, error, _ = session.run(samples(5))
        self.assertEqual(session.inserted, [("Tot textul.", True)])
        self.assertEqual(len(session.audio_seen), 1)
        self.assertEqual(len(session.audio_seen[0]), 15)
        self.assertEqual((text, error), ("Tot textul.", None))

    def test_audio_stays_in_order_across_cuts(self):
        self.cut_every_chunk()
        session = Session([samples(2, 0.1)], ["Unu."])
        session.run(samples(3, 0.2))
        np.testing.assert_allclose(np.concatenate(session.audio_seen), [0.1, 0.1, 0.2, 0.2, 0.2])

    def test_text_waits_while_the_user_is_elsewhere_and_arrives_at_the_end(self):
        self.cut_every_chunk()
        session = Session([samples(10), samples(20)], ["Unu.", "Doi."], can_insert=False)
        text, error, uninserted = session.run()
        self.assertEqual(session.inserted, [("Unu. Doi.", True)])
        self.assertEqual((text, error, uninserted), ("Unu. Doi.", None, ""))

    def test_held_text_keeps_its_order_when_the_user_returns(self):
        self.cut_every_chunk()
        session = Session([samples(10), samples(20)], ["Unu.", "Doi."])
        checks = iter([False, True])
        session.live._can_insert = lambda: next(checks, True)
        session.run()
        self.assertEqual(session.inserted[0], ("Unu. Doi.", False))

    def test_separator_joins_segments_when_trailing_space_is_off(self):
        self.cut_every_chunk()
        session = Session([samples(10), samples(20)], ["Unu.", "Doi."], separator=" ")
        session.run()
        self.assertEqual(session.inserted[:2], [("Unu.", False), (" Doi.", False)])

    def test_silent_dictation_never_touches_the_target(self):
        self.never_cut()
        session = Session([samples(10)], [""])
        self.assertEqual(session.run(), ("", None, ""))
        self.assertEqual(session.inserted, [])

    def test_failed_live_insertion_stops_inserting_and_keeps_later_text(self):
        self.cut_every_chunk()
        session = Session([samples(10)], ["Unu.", "Doi."])
        session.insert_error = RuntimeError("focus failed")
        with self.assertLogs(level="ERROR"):
            text, error, uninserted = session.run(samples(5))
        self.assertEqual((text, error, uninserted), ("Unu. Doi.", "focus failed", "Unu. Doi."))

    def test_failed_final_insertion_reports_what_is_missing(self):
        self.never_cut()
        session = Session([samples(10)], ["Unu."])
        session.insert_error = RuntimeError("focus failed")
        with self.assertLogs(level="ERROR"):
            self.assertEqual(session.run(), ("Unu.", "focus failed", "Unu."))

    def test_failed_live_transcription_retries_all_audio_at_the_end(self):
        self.cut_every_chunk()
        session = Session([samples(10)], ["Tot textul."], transcribe_failures=[RuntimeError("GPU busy")])
        with self.assertLogs(level="ERROR"):
            result = session.run(samples(5))
        self.assertEqual(len(session.audio_seen[0]), 15)
        self.assertEqual(result, ("Tot textul.", None, ""))

    def test_failed_final_transcription_inserts_held_text_without_enter(self):
        self.cut_every_chunk()
        session = Session([samples(10)], ["Unu."], can_insert=False,
                          transcribe_failures=[None, RuntimeError("GPU lost")])
        with self.assertLogs(level="ERROR"):
            text, error, uninserted = session.run(samples(5))
        self.assertEqual(session.inserted, [("Unu.", False)])
        self.assertEqual((text, error, uninserted), ("Unu.", "GPU lost", ""))

    def test_stop_error_keeps_text_already_inserted_and_skips_enter(self):
        self.cut_every_chunk()
        session = Session([samples(10)], ["Unu."])
        text, error, uninserted = session.run(error="device lost")
        self.assertEqual(session.inserted, [("Unu.", False)])
        self.assertEqual((text, error, uninserted), ("Unu.", "device lost", ""))
