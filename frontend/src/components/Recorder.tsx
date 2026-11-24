"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef, useState } from "react";

import { ApiError, type Transcript, uploadRecording } from "@/lib/api";

type Phase = "idle" | "recording" | "paused" | "recorded" | "sending";

type Props = {
  projectId: number;
  /** The longest recording allowed, in seconds. */
  maxSeconds: number;
  onTranscribed: (transcript: Transcript) => void;
};

// Opus in WebM (Chrome, Firefox, Edge) or AAC in MP4 (Safari, iPhone).
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
// Plenty for speech, and keeps a 10-minute recording around 2.5 MB.
const AUDIO_BITS_PER_SECOND = 32_000;

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function stopRecorder(recorder: MediaRecorder | null) {
  // stop() throws if the recorder has already stopped.
  if (recorder && recorder.state !== "inactive") {
    recorder.stop();
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object") {
    const body = error.body as { detail?: string; audio?: string[] };
    if (body.detail) return body.detail;
    if (body.audio) return body.audio.join(" ");
  }
  if (error instanceof ApiError && error.status === 429) {
    return "You've sent a lot of recordings. Please wait a while and try again.";
  }
  return "Something went wrong sending your recording. Please try again.";
}

export function Recorder({ projectId, maxSeconds, onTranscribed }: Props) {
  const { getToken } = useAuth();
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [audio, setAudio] = useState<{ blob: Blob; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Count recording time while recording (not while paused).
  useEffect(() => {
    if (phase !== "recording") {
      return;
    }
    const timer = setInterval(() => setSeconds((current) => current + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  // Stop automatically at the time limit.
  useEffect(() => {
    if (phase === "recording" && seconds >= maxSeconds) {
      stopRecorder(recorderRef.current);
    }
  }, [phase, seconds, maxSeconds]);

  // Release the microphone and the audio preview when leaving the page.
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);
  useEffect(() => {
    return () => {
      if (audio) URL.revokeObjectURL(audio.url);
    };
  }, [audio]);

  async function start() {
    setError(null);
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices) {
      setError("Your browser can't record audio. Please try the latest Chrome, Edge, Firefox or Safari.");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("We couldn't use your microphone. Please allow microphone access and try again.");
      return;
    }

    const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(stream, {
      mimeType,
      audioBitsPerSecond: AUDIO_BITS_PER_SECOND,
    });
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
      chunksRef.current = [];
      setAudio({ blob, url: URL.createObjectURL(blob) });
      setPhase("recorded");
    };

    streamRef.current = stream;
    recorderRef.current = recorder;
    setSeconds(0);
    recorder.start(1000);
    setPhase("recording");
  }

  function pause() {
    recorderRef.current?.pause();
    setPhase("paused");
  }

  function resume() {
    recorderRef.current?.resume();
    setPhase("recording");
  }

  function stop() {
    stopRecorder(recorderRef.current);
  }

  function discard() {
    setAudio(null);
    setSeconds(0);
    setError(null);
    setPhase("idle");
  }

  async function send() {
    if (!audio) return;
    setPhase("sending");
    setError(null);
    try {
      const token = await getToken();
      if (!token) {
        setError("Your session has expired. Please sign in again.");
        setPhase("recorded");
        return;
      }
      const transcript = await uploadRecording(token, projectId, audio.blob);
      // The recording has done its job: drop it from the browser too.
      discard();
      onTranscribed(transcript);
    } catch (err: unknown) {
      setError(errorMessage(err));
      setPhase("recorded");
    }
  }

  const buttonClass =
    "rounded-md border border-neutral-300 px-4 py-2 font-medium disabled:opacity-50 dark:border-neutral-700";
  const primaryClass =
    "rounded-md bg-neutral-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900";

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-neutral-300 p-4 dark:border-neutral-700">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Record your explanation</h2>
        <span className="font-mono text-sm" aria-label="Recording time">
          {formatTime(seconds)} / {formatTime(maxSeconds)}
        </span>
      </div>

      <p role="status" className="text-sm text-neutral-600 dark:text-neutral-300">
        {phase === "idle" && "Press Record and describe your idea in your own words."}
        {phase === "recording" && "Recording… speak naturally. You can pause at any time."}
        {phase === "paused" && "Paused."}
        {phase === "recorded" && "Listen back, then send it or record again."}
        {phase === "sending" && "Turning your recording into text…"}
      </p>

      {audio && phase !== "sending" && (
        <audio controls src={audio.url} className="w-full">
          Your browser can&apos;t play the recording.
        </audio>
      )}

      <div className="flex flex-wrap gap-2">
        {phase === "idle" && (
          <button type="button" onClick={start} className={primaryClass}>
            Record
          </button>
        )}
        {phase === "recording" && (
          <>
            <button type="button" onClick={pause} className={buttonClass}>
              Pause
            </button>
            <button type="button" onClick={stop} className={primaryClass}>
              Stop
            </button>
          </>
        )}
        {phase === "paused" && (
          <>
            <button type="button" onClick={resume} className={buttonClass}>
              Resume
            </button>
            <button type="button" onClick={stop} className={primaryClass}>
              Stop
            </button>
          </>
        )}
        {(phase === "recorded" || phase === "sending") && (
          <>
            <button type="button" onClick={discard} disabled={phase === "sending"} className={buttonClass}>
              Record again
            </button>
            <button type="button" onClick={send} disabled={phase === "sending"} className={primaryClass}>
              {phase === "sending" ? "Sending…" : "Send for transcription"}
            </button>
          </>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  );
}