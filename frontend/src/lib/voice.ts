// Spoken replies (Flux voice) — strip markdown for speech, synthesize via the
// server's Cartesia-backed /v1/speech/synthesize, and play it in the browser.

import { fetchTtsHealth, synthesizeSpeech } from './api';

// Default Flux voice (Cartesia voice_id chosen by the owner). The server
// falls back to its own default when this is empty.
export const FLUX_VOICE_ID = '28a942b5-74f3-47bb-9b56-4c3f2562d3ba';

let ttsAvailable: boolean | null = null;
let currentAudio: HTMLAudioElement | null = null;
let currentUrl: string | null = null;

/** Cached TTS availability (server needs CARTESIA_API_KEY). */
export async function isTtsAvailable(): Promise<boolean> {
  if (ttsAvailable === null) {
    const health = await fetchTtsHealth();
    ttsAvailable = !!health.available;
  }
  return ttsAvailable;
}

/** Convert a markdown reply into something natural to read aloud. */
export function stripForSpeech(markdown: string): string {
  let text = markdown;
  // Fenced code blocks -> short spoken placeholder
  text = text.replace(/```[\s\S]*?```/g, ' (trecho de código omitido) ');
  // Inline code -> keep the content
  text = text.replace(/`([^`]+)`/g, '$1');
  // Images -> drop; links -> keep label
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ');
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  // Headers, blockquotes, list markers
  text = text.replace(/^#{1,6}\s+/gm, '');
  text = text.replace(/^>\s?/gm, '');
  text = text.replace(/^\s*[-*+]\s+/gm, '');
  text = text.replace(/^\s*\d+\.\s+/gm, '');
  // Emphasis and strikethrough
  text = text.replace(/(\*\*|__|\*|_|~~)/g, '');
  // Tables -> flatten pipes
  text = text.replace(/\|/g, ', ');
  // Collapse whitespace
  text = text.replace(/\s*\n\s*/g, '. ').replace(/\s{2,}/g, ' ');
  text = text.replace(/\.\s*\./g, '.');
  return text.trim();
}

/** Stop any reply currently being spoken. */
export function stopSpeaking(): void {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl);
    currentUrl = null;
  }
}

/**
 * Speak an assistant reply aloud. Silently no-ops when TTS is unavailable;
 * surfaces other failures to the caller (for a toast).
 */
export async function speakReply(markdown: string): Promise<void> {
  const text = stripForSpeech(markdown);
  if (!text) return;
  if (!(await isTtsAvailable())) return;

  const blob = await synthesizeSpeech(text, {
    voiceId: FLUX_VOICE_ID,
    language: 'pt',
  });
  // A newer reply may have started while we were synthesizing.
  stopSpeaking();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  currentAudio = audio;
  currentUrl = url;
  audio.onended = () => {
    if (currentAudio === audio) stopSpeaking();
  };
  await audio.play();
}
