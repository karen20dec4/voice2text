"""Cuts a running dictation at the speaker's pauses, so text appears while they talk."""
import logging
import threading
import time

from faster_whisper.vad import VadOptions, get_speech_timestamps
import numpy as np

SAMPLE_RATE = 16000
POLL_SECONDS = 0.2
# Silence that ends a phrase, and the part of it kept so a final sound is not clipped.
PAUSE_SAMPLES = int(0.6 * SAMPLE_RATE)
TAIL_SAMPLES = int(0.2 * SAMPLE_RATE)
# Past this length a short breath is enough to end the segment.
LONG_SEGMENT_SAMPLES = 12 * SAMPLE_RATE
# Past this length the segment ends anyway, which also bounds the cost of each poll.
MAX_SEGMENT_SAMPLES = 28 * SAMPLE_RATE
# Short gaps are reported so a breath can end a long segment; speech shorter than
# 250 ms is a click or a cough, which Whisper tends to turn into invented text.
VAD_OPTIONS = VadOptions(min_speech_duration_ms=250, min_silence_duration_ms=150, speech_pad_ms=0)


def find_segment_end(audio):
    """Sample at which the audio can be cut between two phrases, or None."""
    if len(audio) < PAUSE_SAMPLES:
        return None
    speech = get_speech_timestamps(audio, VAD_OPTIONS)
    if speech and len(audio) - speech[-1]["end"] >= PAUSE_SAMPLES:
        return speech[-1]["end"] + TAIL_SAMPLES
    if len(audio) >= LONG_SEGMENT_SAMPLES and len(speech) > 1:
        return (speech[-2]["end"] + speech[-1]["start"]) // 2
    return len(audio) if len(audio) >= MAX_SEGMENT_SAMPLES else None


class LiveTranscription:
    """Transcribes and inserts one dictation, segment by segment, on its own thread."""

    def __init__(self, take_audio, transcribe, insert, can_insert, on_finished, separator=" "):
        self._take_audio = take_audio
        self._transcribe_audio = transcribe
        self._insert = insert  # insert(text, final); only final may press Enter.
        self._can_insert = can_insert
        self._on_finished = on_finished  # on_finished(text, error, uninserted)
        self._separator = separator
        self._pending = np.zeros(0, dtype=np.float32)
        self._text = []
        self._held = []  # Transcribed, but not in the target window yet.
        self._inserted = False
        self._insert_error = None
        self._last_audio = None
        self._stop_error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="live-transcription", daemon=True)

    def start(self):
        self._thread.start()

    def finish(self, last_audio=None, error=None):
        """Called once, after the recorder stopped; on_finished reports the result."""
        self._last_audio, self._stop_error = last_audio, error
        self._stop.set()

    def join(self, timeout=None):
        self._thread.join(timeout)

    def _run(self):
        try:
            self._cut_at_pauses()
        except Exception:
            # The audio stays pending, so the end of the dictation retries it whole.
            logging.exception("Transcriere în timp real oprită")
        self._stop.wait()
        self._on_finished(*self._finish())

    def _cut_at_pauses(self):
        while not self._stop.wait(POLL_SECONDS):
            self._add_audio(self._take_audio())
            end = find_segment_end(self._pending)
            if end is not None:
                self._transcribe(end)
                self._insert_held()

    def _add_audio(self, audio):
        if audio is not None and len(audio):
            self._pending = np.concatenate((self._pending, audio))

    def _transcribe(self, end):
        if not end:
            return
        started = time.monotonic()
        text = self._transcribe_audio(self._pending[:end])
        self._pending = self._pending[end:]
        logging.info("Segment transcris: audio=%.1f s, durată=%.2f s, caractere=%s",
                     end / SAMPLE_RATE, time.monotonic() - started, len(text))
        if text:
            self._text.append(text)
            self._held.append(text)

    def _insert_held(self):
        # A failed insertion may have sent part of the text and later segments
        # would land out of order, so it is the last attempt for this dictation.
        if not self._held or self._insert_error or not self._can_insert():
            return
        try:
            self._send(final=False)
        except Exception as error:
            logging.exception("Inserare în timp real eșuată")
            self._insert_error = str(error)

    def _send(self, final):
        text = " ".join(self._held)
        self._insert(self._separator + text if text and self._inserted else text, final)
        self._held.clear()
        self._inserted = True

    def _finish(self):
        error = self._stop_error
        try:
            self._add_audio(self._last_audio)
            self._transcribe(len(self._pending))
        except Exception as failure:
            logging.exception("Eroare procesare dictare")
            error = error or str(failure)
        if self._insert_error:
            error = error or self._insert_error
        elif self._held or (self._inserted and not error):
            try:
                self._send(final=not error)
            except Exception as failure:
                logging.exception("Eroare inserare dictare")
                error = error or str(failure)
        return " ".join(self._text), error, " ".join(self._held)
