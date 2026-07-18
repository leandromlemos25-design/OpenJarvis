// Flux Voice Mode — an immersive full-screen voice conversation with a living,
// audio-reactive orb. Tap to talk: the orb breathes when idle, swells with your
// voice while listening, shimmers while thinking, and pulses as Flux speaks.
//
// Pipeline (all wired to the local server): mic -> /v1/speech/transcribe (STT,
// local) -> /v1/chat/completions (Flux persona + tools) -> /v1/speech/synthesize
// (Cartesia voice). Cérebro e transcrição locais; só a voz de saída na nuvem.

import { useEffect, useRef, useState, useCallback } from 'react';
import { X, Mic } from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { transcribeAudio, synthesizeSpeech } from '../../lib/api';
import { streamChat } from '../../lib/sse';
import { stripForSpeech, FLUX_VOICE_ID } from '../../lib/voice';

type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

const STATE_LABEL: Record<VoiceState, string> = {
  idle: 'Toque para falar',
  listening: 'Ouvindo…',
  thinking: 'Pensando…',
  speaking: 'Flux está falando…',
};

// Orb color per state (inner glow, outer glow) — elegant blue → violet → teal.
const STATE_COLORS: Record<VoiceState, [string, string]> = {
  idle: ['#6ea8ff', '#3b5bdb'],
  listening: ['#5ad1ff', '#2f74ff'],
  thinking: ['#b388ff', '#6a3bd6'],
  speaking: ['#5af0c8', '#1fb98a'],
};

// Render a hex color (#rrggbb) with an alpha channel.
function hexA(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function FluxVoiceMode() {
  const open = useAppStore((s) => s.voiceModeOpen);
  const setOpen = useAppStore((s) => s.setVoiceModeOpen);
  const selectedModel = useAppStore((s) => s.selectedModel);

  const [state, setState] = useState<VoiceState>('idle');
  const [caption, setCaption] = useState('');
  const [error, setError] = useState('');

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const intensityRef = useRef(0);
  const stateRef = useRef<VoiceState>('idle');
  const rafRef = useRef<number | undefined>(undefined);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const speechSeenRef = useRef(false);
  const silenceMsRef = useRef(0);
  const listenMsRef = useRef(0);
  const lastTsRef = useRef(0);
  const runningRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<{ role: string; content: string }[]>([]);

  const model = selectedModel || 'qwen3.5:9b';

  const setVoiceState = useCallback((s: VoiceState) => {
    stateRef.current = s;
    setState(s);
  }, []);

  const readIntensity = useCallback((): number => {
    const analyser = analyserRef.current;
    if (!analyser) return 0;
    const buf = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / buf.length) * 3.2);
  }, []);

  const cleanupMic = useCallback(() => {
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    analyserRef.current = null;
  }, []);

  const startListening = useCallback(async () => {
    setError('');
    try {
      const ctx = audioCtxRef.current;
      if (!ctx) return;
      if (ctx.state === 'suspended') await ctx.resume();

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      src.connect(analyser);
      analyserRef.current = analyser;

      chunksRef.current = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.start();
      recorderRef.current = rec;

      speechSeenRef.current = false;
      silenceMsRef.current = 0;
      listenMsRef.current = 0;
      setVoiceState('listening');
    } catch {
      setError('Não consegui acessar o microfone. Permita o acesso no navegador.');
      runningRef.current = false;
      setVoiceState('idle');
    }
  }, [setVoiceState]);

  const speak = useCallback(
    async (text: string) => {
      const clean = stripForSpeech(text);
      if (!clean) return;
      let blob: Blob;
      try {
        blob = await synthesizeSpeech(clean, {
          voiceId: FLUX_VOICE_ID,
          language: 'pt',
        });
      } catch {
        // TTS unavailable (no CARTESIA_API_KEY) — stay silent, keep the text.
        return;
      }
      const ctx = audioCtxRef.current;
      if (!ctx) return;
      const url = URL.createObjectURL(blob);
      const audioEl = new Audio(url);
      currentAudioRef.current = audioEl;
      try {
        const srcNode = ctx.createMediaElementSource(audioEl);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        srcNode.connect(analyser);
        analyser.connect(ctx.destination);
        analyserRef.current = analyser;
      } catch {
        analyserRef.current = null;
      }
      setVoiceState('speaking');
      await new Promise<void>((resolve) => {
        audioEl.onended = () => resolve();
        audioEl.onerror = () => resolve();
        audioEl.onpause = () => resolve(); // tap-to-interrupt
        audioEl.play().catch(() => resolve());
      });
      analyserRef.current = null;
      currentAudioRef.current = null;
      URL.revokeObjectURL(url);
    },
    [setVoiceState],
  );

  const processTurn = useCallback(
    async (blob: Blob) => {
      setVoiceState('thinking');
      let userText = '';
      try {
        const res = await transcribeAudio(blob);
        userText = (res.text || '').trim();
      } catch {
        setError('Falha ao transcrever.');
      }
      if (!userText) {
        if (runningRef.current) startListening();
        else setVoiceState('idle');
        return;
      }
      setCaption(`Você: ${userText}`);
      messagesRef.current.push({ role: 'user', content: userText });

      let reply = '';
      try {
        const controller = new AbortController();
        abortRef.current = controller;
        for await (const ev of streamChat(
          { model, messages: messagesRef.current, stream: true },
          controller.signal,
        )) {
          try {
            const data = JSON.parse(ev.data);
            const delta = data.choices?.[0]?.delta?.content;
            if (delta) reply += delta;
            if (data.choices?.[0]?.finish_reason === 'stop') break;
          } catch {
            /* keep-alives / non-JSON frames */
          }
        }
      } catch {
        setError('Falha ao gerar a resposta.');
      }
      reply = reply.trim();
      abortRef.current = null;
      if (!reply) {
        if (runningRef.current) startListening();
        else setVoiceState('idle');
        return;
      }
      messagesRef.current.push({ role: 'assistant', content: reply });
      setCaption(`Flux: ${reply}`);
      await speak(reply);
      if (runningRef.current) startListening();
      else setVoiceState('idle');
    },
    [model, setVoiceState, startListening, speak],
  );

  const stopListeningAndProcess = useCallback(() => {
    const rec = recorderRef.current;
    if (!rec || rec.state !== 'recording') return;
    recorderRef.current = null;
    rec.onstop = async () => {
      cleanupMic();
      const blob = new Blob(chunksRef.current, {
        type: rec.mimeType || 'audio/webm',
      });
      chunksRef.current = [];
      await processTurn(blob);
    };
    rec.stop();
  }, [cleanupMic, processTurn]);

  const draw = useCallback(
    (ts: number) => {
      rafRef.current = requestAnimationFrame(draw);
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const dt = lastTsRef.current ? ts - lastTsRef.current : 16;
      lastTsRef.current = ts;
      const st = stateRef.current;

      let target = 0;
      if (st === 'listening' || st === 'speaking') target = readIntensity();
      else if (st === 'thinking') target = 0.35 + 0.15 * Math.sin(ts / 160);
      else target = 0.12 + 0.06 * Math.sin(ts / 900);
      intensityRef.current += (target - intensityRef.current) * 0.18;
      const amp = intensityRef.current;

      if (st === 'listening' && recorderRef.current) {
        listenMsRef.current += dt;
        if (amp > 0.14) {
          speechSeenRef.current = true;
          silenceMsRef.current = 0;
        } else if (speechSeenRef.current) {
          silenceMsRef.current += dt;
        }
        if (
          (speechSeenRef.current && silenceMsRef.current > 1300) ||
          listenMsRef.current > 15000
        ) {
          stopListeningAndProcess();
        }
      }

      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;
      ctx.clearRect(0, 0, w, h);

      const [inner, outer] = STATE_COLORS[st];
      const base = Math.min(w, h) * 0.16;
      const r = base * (1 + amp * 0.9);

      const aura = ctx.createRadialGradient(cx, cy, r * 0.2, cx, cy, r * 2.6);
      aura.addColorStop(0, hexA(outer, 0.35 + amp * 0.35));
      aura.addColorStop(1, hexA(outer, 0));
      ctx.fillStyle = aura;
      ctx.beginPath();
      ctx.arc(cx, cy, r * 2.6, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      const points = 64;
      for (let i = 0; i <= points; i++) {
        const a = (i / points) * Math.PI * 2;
        const wob =
          1 +
          0.06 * Math.sin(a * 3 + ts / 380) * (0.5 + amp) +
          0.05 * Math.sin(a * 5 - ts / 520) * (0.5 + amp);
        const rr = r * wob;
        const x = cx + Math.cos(a) * rr;
        const y = cy + Math.sin(a) * rr;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      const core = ctx.createRadialGradient(
        cx - r * 0.3,
        cy - r * 0.3,
        r * 0.1,
        cx,
        cy,
        r * 1.2,
      );
      core.addColorStop(0, hexA(inner, 0.98));
      core.addColorStop(0.6, hexA(inner, 0.85));
      core.addColorStop(1, hexA(outer, 0.9));
      ctx.fillStyle = core;
      ctx.shadowColor = hexA(inner, 0.9);
      ctx.shadowBlur = 40 + amp * 60;
      ctx.fill();
      ctx.shadowBlur = 0;
    },
    [readIntensity, stopListeningAndProcess],
  );

  const handleTap = useCallback(() => {
    const st = stateRef.current;
    if (st === 'idle') {
      runningRef.current = true;
      startListening();
    } else if (st === 'listening') {
      stopListeningAndProcess();
    } else if (st === 'speaking') {
      currentAudioRef.current?.pause();
    }
  }, [startListening, stopListeningAndProcess]);

  const stopEverything = useCallback(() => {
    runningRef.current = false;
    abortRef.current?.abort();
    abortRef.current = null;
    try {
      recorderRef.current?.stop();
    } catch {
      /* not recording */
    }
    recorderRef.current = null;
    cleanupMic();
    currentAudioRef.current?.pause();
    currentAudioRef.current = null;
    setVoiceState('idle');
  }, [cleanupMic, setVoiceState]);

  useEffect(() => {
    if (!open) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      canvas.width = canvas.clientWidth * devicePixelRatio;
      canvas.height = canvas.clientHeight * devicePixelRatio;
    };
    resize();
    window.addEventListener('resize', resize);
    try {
      audioCtxRef.current = new AudioContext();
    } catch {
      audioCtxRef.current = null;
    }
    messagesRef.current = [];
    lastTsRef.current = 0;
    rafRef.current = requestAnimationFrame(draw);
    return () => {
      window.removeEventListener('resize', resize);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      stopEverything();
      audioCtxRef.current?.close().catch(() => {});
      audioCtxRef.current = null;
    };
  }, [open, draw, stopEverything]);

  if (!open) return null;

  const [inner] = STATE_COLORS[state];

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center"
      style={{
        background:
          'radial-gradient(circle at 50% 40%, #12163a 0%, #080a1c 60%, #05060f 100%)',
      }}
    >
      <button
        onClick={() => setOpen(false)}
        className="absolute top-5 right-5 p-2 rounded-full transition-colors"
        style={{ background: 'rgba(255,255,255,0.08)', color: '#cdd3f0' }}
        title="Fechar modo voz"
      >
        <X size={22} />
      </button>

      <div className="text-center mb-2 select-none">
        <span
          className="text-sm tracking-[0.3em] uppercase"
          style={{ color: 'rgba(205,211,240,0.55)' }}
        >
          Flux
        </span>
      </div>

      <canvas
        ref={canvasRef}
        onClick={handleTap}
        className="cursor-pointer"
        style={{ width: 'min(70vw, 420px)', height: 'min(70vw, 420px)' }}
      />

      <div className="mt-4 text-center px-6" style={{ maxWidth: 640 }}>
        <p className="text-lg font-medium" style={{ color: inner }}>
          {STATE_LABEL[state]}
        </p>
        {caption && (
          <p
            className="mt-3 text-sm leading-relaxed"
            style={{ color: 'rgba(220,224,245,0.75)' }}
          >
            {caption}
          </p>
        )}
        {error && (
          <p className="mt-3 text-sm" style={{ color: '#ff8a8a' }}>
            {error}
          </p>
        )}
      </div>

      <button
        onClick={handleTap}
        className="mt-8 flex items-center gap-2 px-5 py-3 rounded-full font-medium transition-transform active:scale-95"
        style={{
          background: state === 'listening' ? '#ff5d6c' : inner,
          color: '#0a0c1a',
        }}
      >
        <Mic size={18} />
        {state === 'idle' && 'Falar com o Flux'}
        {state === 'listening' && 'Toque para enviar'}
        {state === 'thinking' && 'Pensando…'}
        {state === 'speaking' && 'Falando…'}
      </button>
    </div>
  );
}
