#!/usr/bin/env python3
"""Flux Voz — assistente de voz mão-dupla (mordomo, com ferramentas).

Fluxo:
    🎤 você fala  ->  transcreve LOCAL (faster-whisper)  ->  Flux responde
    (persona de mordomo + ferramentas)  ->  🔊 Flux fala de volta
    (Cartesia, voz fluida).

Cérebro (LLM) e transcrição rodam LOCAIS; só a voz de saída vai à nuvem (Cartesia).

Pré-requisitos (na raiz do repo):
    1. Ollama:            ollama serve   &&   ollama pull qwen3.5:9b
    2. OpenJarvis:        uv sync --extra dev --extra desktop
    3. Libs de áudio:     uv sync --extra flux-voice   (ou: uv pip install sounddevice soundfile numpy)
    4. Chave Cartesia:    Windows  ->  setx CARTESIA_API_KEY "sua-chave"  (reabra o terminal)
                          Linux/Mac->  export CARTESIA_API_KEY="sua-chave"

Uso (Windows: rode pela venv direto p/ não perder a extensão nativa/áudio):
    .venv\\Scripts\\python.exe examples\\flux\\flux_voice.py
    # ou, sem re-sincronizar deps:
    uv run --no-sync python examples/flux/flux_voice.py

    python examples/flux/flux_voice.py --hands-free       # sem apertar Enter (VAD)
    python examples/flux/flux_voice.py --device cuda       # GPU (precisa CUDA/cuBLAS)
    python examples/flux/flux_voice.py --model qwen3.5:35b

Durante a conversa:
    - Modo padrão: Enter começa a gravar; Enter de novo para parar.
    - Modo --hands-free: fale quando quiser; o silêncio encerra a fala.
    - Diga "sair" / "tchau", ou Ctrl+C, para encerrar.
"""

from __future__ import annotations

import io
import os
import queue
import re
import sys
import threading

import click

SAMPLE_RATE_IN = 16000  # faster-whisper espera 16 kHz mono


# ─────────────────────────── saída (Windows-safe) ─────────────────────────────
# click.echo(err=True) estoura no console do Windows (colorama/_winconsole,
# "Windows error 6"). Usamos print puro para não engolir erros reais.
def _out(msg: str = "") -> None:
    print(msg, flush=True)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ─────────────────────────── dependências opcionais ───────────────────────────
def _require_audio():
    """Importa as libs de áudio com mensagem de erro clara se faltarem."""
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        return np, sd, sf
    except ImportError as exc:
        _err(
            "Erro: faltam libs de áudio. Instale com:\n"
            "  uv sync --extra flux-voice\n"
            "  (ou: uv pip install sounddevice soundfile numpy)\n"
            "No Linux, pode faltar: sudo apt install libportaudio2\n"
            f"Detalhe: {exc}"
        )
        sys.exit(1)


# ─────────────────────────────── persona ──────────────────────────────────────
def _load_persona() -> str:
    """Carrega SOUL.md + USER.md do Flux para garantir a persona (independe do agente)."""
    from pathlib import Path

    candidates = [
        Path.home() / ".openjarvis" / "personas" / "flux",
        Path(__file__).resolve().parents[2]
        / "configs"
        / "openjarvis"
        / "personas"
        / "flux",
    ]
    parts: list[str] = []
    for base in candidates:
        soul, user = base / "SOUL.md", base / "USER.md"
        if soul.exists():
            parts.append(soul.read_text(encoding="utf-8"))
            if user.exists():
                parts.append("\n\n## Sobre o senhor\n\n" + user.read_text(encoding="utf-8"))
            break
    if not parts:
        parts.append(
            "Você é o Flux, assistente pessoal do senhor. Fala português "
            "brasileiro com elegância de mordomo, trata o usuário por 'senhor'."
        )
    parts.append(
        "\n\nIMPORTANTE: isto será FALADO em voz alta. Responda em português, "
        "curto e natural, sem markdown, sem listas, sem emojis. Frases faladas."
    )
    return "".join(parts)


# ─────────────────────────────── gravação ─────────────────────────────────────
def record_until_enter(sd, np):
    """Push-to-talk: grava do microfone até o usuário apertar Enter."""
    _out("🎤 Fale... (Enter para parar)")
    frames: list = []
    q: queue.Queue = queue.Queue()

    def callback(indata, _frames, _time, status):
        q.put(indata.copy())

    stop = threading.Event()
    threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()

    with sd.InputStream(samplerate=SAMPLE_RATE_IN, channels=1, dtype="float32", callback=callback):
        while not stop.is_set():
            try:
                frames.append(q.get(timeout=0.1))
            except queue.Empty:
                continue

    if not frames:
        return None
    return np.concatenate(frames, axis=0)


def record_hands_free(sd, np, threshold=None, silence_ms=1200, max_ms=15000, calib_ms=600):
    """Hands-free (VAD por energia): calibra o ruído, espera você falar e
    encerra sozinho após um trecho de silêncio."""
    sr = SAMPLE_RATE_IN
    block = 1024
    block_ms = block / sr * 1000.0
    q: queue.Queue = queue.Queue()

    def callback(indata, _frames, _time, status):
        q.put(indata[:, 0].copy())

    frames: list = []
    ambient: list = []
    started = False
    silence_acc = 0.0
    dur = 0.0

    _out("🎧 Fale quando quiser (o silêncio encerra a fala)...")
    with sd.InputStream(
        samplerate=sr, channels=1, dtype="float32", blocksize=block, callback=callback
    ):
        for _ in range(max(1, int(calib_ms / block_ms))):
            b = q.get()
            ambient.append(float(np.sqrt(np.mean(b**2)) + 1e-9))
        base = sum(ambient) / len(ambient)
        thr = threshold if threshold else max(base * 3.0, 0.010)

        while True:
            b = q.get()
            rms = float(np.sqrt(np.mean(b**2)))
            dur += block_ms
            if rms >= thr:
                started = True
                silence_acc = 0.0
                frames.append(b)
            elif started:
                frames.append(b)
                silence_acc += block_ms
                if silence_acc >= silence_ms:
                    break
            if dur >= max_ms:
                break

    if not started or not frames:
        return None
    return np.concatenate(frames, axis=0).reshape(-1, 1)


def _to_wav_bytes(audio, sf) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE_IN, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ─────────────────────────────── STT (com fallback CPU) ───────────────────────
class SpeechToText:
    """Envolve o faster-whisper com fallback automático GPU -> CPU.

    Em máquina com NVIDIA mas sem CUDA/cuBLAS, o carregamento em GPU quebra
    (cublas64_12.dll not found). Aqui detectamos e caímos para CPU sozinhos.
    """

    def __init__(self, backend_cls, model_size: str, device: str):
        self._cls = backend_cls
        self._model_size = model_size
        self._device = device
        self._backend = self._make(device)

    def _make(self, device: str):
        compute = "int8" if device == "cpu" else "float16"
        return self._cls(model_size=self._model_size, device=device, compute_type=compute)

    def transcribe(self, wav_bytes: bytes, language: str):
        try:
            return self._backend.transcribe(wav_bytes, format="wav", language=language)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if self._device != "cpu" and any(
                k in msg for k in ("cuda", "cublas", "cudnn", "library", "dll")
            ):
                _err(f"[stt] GPU indisponível ({exc.__class__.__name__}); caindo para CPU.")
                self._device = "cpu"
                self._backend = self._make("cpu")
                return self._backend.transcribe(wav_bytes, format="wav", language=language)
            raise


# ─────────────────────────────── fala (TTS) ───────────────────────────────────
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def speak_fluid(text: str, tts, voice_id: str, language: str, sd, sf, np) -> None:
    """Fala frase-a-frase: sintetiza a próxima enquanto toca a atual (fluido)."""
    sentences = _split_sentences(text)
    if not sentences:
        return

    audio_q: queue.Queue = queue.Queue(maxsize=2)

    def producer():
        for sent in sentences:
            try:
                result = tts.synthesize(
                    sent, voice_id=voice_id, output_format="wav", language=language
                )
                data, sr = sf.read(io.BytesIO(result.audio), dtype="float32")
                audio_q.put((data, sr))
            except Exception as exc:  # noqa: BLE001
                _err(f"[voz] falha ao sintetizar: {exc}")
        audio_q.put(None)

    threading.Thread(target=producer, daemon=True).start()

    while True:
        item = audio_q.get()
        if item is None:
            break
        data, sr = item
        sd.play(data, sr)
        sd.wait()


# ─────────────────────────────── principal ────────────────────────────────────
@click.command()
@click.option("--model", default="qwen3.5:9b", show_default=True, help="Modelo Ollama.")
@click.option("--engine", "engine_key", default="ollama", show_default=True)
@click.option("--language", default="pt", show_default=True, help="Idioma da fala/voz.")
@click.option(
    "--voice",
    "voice_id",
    default="28a942b5-74f3-47bb-9b56-4c3f2562d3ba",
    show_default=True,
    help="voice_id da Cartesia (voz do Flux).",
)
@click.option("--whisper-model", default="small", show_default=True, help="Tamanho do Whisper (STT).")
@click.option(
    "--device",
    default="cpu",
    show_default=True,
    type=click.Choice(["cpu", "cuda"]),
    help="Dispositivo do STT. 'cuda' precisa de CUDA/cuBLAS; senão fica em cpu.",
)
@click.option("--hands-free", is_flag=True, help="Sem apertar Enter: detecta fala por VAD.")
@click.option("--vad-threshold", type=float, default=None, help="Sensibilidade do VAD (menor = mais sensível).")
def main(
    model: str,
    engine_key: str,
    language: str,
    voice_id: str,
    whisper_model: str,
    device: str,
    hands_free: bool,
    vad_threshold: float | None,
) -> None:
    """Conversa por voz com o Flux (persona + ferramentas + voz fluida)."""
    np, sd, sf = _require_audio()

    if not os.environ.get("CARTESIA_API_KEY"):
        _err(
            "Erro: CARTESIA_API_KEY não definida. Configure sua chave da Cartesia:\n"
            '  Windows:  setx CARTESIA_API_KEY "sua-chave"   (reabra o terminal)\n'
            '  Linux/Mac: export CARTESIA_API_KEY="sua-chave"'
        )
        sys.exit(1)

    try:
        from openjarvis import Jarvis
        from openjarvis.speech.cartesia_tts import CartesiaTTSBackend
        from openjarvis.speech.faster_whisper import FasterWhisperBackend
    except ImportError as exc:
        _err(
            f"Erro: openjarvis/áudio não instalado ({exc}).\n"
            "Rode:  uv sync --extra dev --extra desktop"
        )
        sys.exit(1)

    stt = SpeechToText(FasterWhisperBackend, whisper_model, device)
    tts = CartesiaTTSBackend(model="sonic-2", language=language)

    try:
        flux = Jarvis(model=model, engine_key=engine_key)
    except Exception as exc:  # noqa: BLE001
        _err(
            f"Erro ao iniciar o Flux — {exc}\n"
            f"O engine está no ar? Para Ollama:  ollama serve  &&  ollama pull {model}"
        )
        sys.exit(1)

    persona = _load_persona()
    tools: list[str] = []
    try:
        enabled = getattr(getattr(flux.config, "tools", None), "enabled", None)
        if isinstance(enabled, str):
            tools = [t.strip() for t in enabled.split(",") if t.strip()]
        elif isinstance(enabled, (list, tuple)):
            tools = [str(t) for t in enabled]
    except Exception:  # noqa: BLE001
        tools = []
    if not tools:
        tools = ["web_search", "file_read", "think", "calculator"]

    history: list[tuple[str, str]] = []
    mode = "hands-free (VAD)" if hands_free else "push-to-talk (Enter)"

    _out("─" * 60)
    _out(f"Flux (voz) pronto. Modelo: {model} | STT: whisper-{whisper_model}/{device} | Modo: {mode}")
    _out("Diga 'sair' ou Ctrl+C para encerrar.")
    _out("─" * 60)

    try:
        while True:
            if hands_free:
                audio = record_hands_free(sd, np, threshold=vad_threshold)
            else:
                input("\n[Enter para falar] ")
                audio = record_until_enter(sd, np)

            if audio is None or len(audio) < SAMPLE_RATE_IN // 2:
                _out("(nada capturado)")
                continue

            try:
                result = stt.transcribe(_to_wav_bytes(audio, sf), language)
                user_text = (getattr(result, "text", "") or "").strip()
            except Exception as exc:  # noqa: BLE001
                _err(f"[stt] falha ao transcrever: {exc}")
                continue

            if not user_text:
                _out("(não entendi)")
                continue

            _out(f"\n👤 senhor: {user_text}")
            if user_text.lower().strip(" .!?") in {"sair", "tchau", "encerrar", "fim"}:
                speak_fluid("Às ordens, senhor. Até logo.", tts, voice_id, language, sd, sf, np)
                break

            convo = "\n".join(f"Senhor: {u}\nFlux: {a}" for u, a in history[-4:])
            query = f"{persona}\n\n{convo}\n\nSenhor: {user_text}\nFlux:".strip()

            try:
                reply = flux.ask(query, agent="orchestrator", tools=tools)
            except Exception as exc:  # noqa: BLE001
                _err(f"[flux] erro: {exc}")
                continue

            reply = (reply or "").strip()
            _out(f"🎩 Flux: {reply}")
            speak_fluid(reply, tts, voice_id, language, sd, sf, np)
            history.append((user_text, reply))
    except KeyboardInterrupt:
        _out("\nEncerrado, senhor.")
    finally:
        flux.close()


if __name__ == "__main__":
    main()
