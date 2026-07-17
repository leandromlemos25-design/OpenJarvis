#!/usr/bin/env python3
"""Flux Voz — assistente de voz mão-dupla (mordomo, com ferramentas).

Fluxo:
    🎤 você fala  ->  transcreve LOCAL (faster-whisper)  ->  Flux responde
    (persona de mordomo + ferramentas)  ->  🔊 Flux fala de volta
    (Cartesia, voz "British Butler", fluida).

Cérebro (LLM) e transcrição rodam LOCAIS; só a voz de saída vai à nuvem (Cartesia).

Pré-requisitos (na raiz do repo):
    1. Ollama:            ollama serve   &&   ollama pull qwen3.5:9b
    2. OpenJarvis:        uv sync --extra dev --extra desktop
    3. Libs de áudio:     uv pip install sounddevice soundfile numpy
    4. Chave Cartesia:    Windows  ->  setx CARTESIA_API_KEY "sua-chave"  (reabra o terminal)
                          Linux/Mac->  export CARTESIA_API_KEY="sua-chave"

Uso:
    uv run python examples/flux/flux_voice.py
    uv run python examples/flux/flux_voice.py --model qwen3.5:35b
    uv run python examples/flux/flux_voice.py --voice <voice_id-PT-BR-da-Cartesia>

Durante a conversa:
    - Enter começa a gravar; Enter de novo para parar (fala e escuta).
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


# ─────────────────────────── dependências opcionais ───────────────────────────
def _require_audio():
    """Importa as libs de áudio com mensagem de erro clara se faltarem."""
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        return np, sd, sf
    except ImportError as exc:
        click.echo(
            "Erro: faltam libs de áudio. Instale com:\n"
            "  uv pip install sounddevice soundfile numpy\n"
            "(No Linux, pode ser necessário: sudo apt install libportaudio2)\n"
            f"Detalhe: {exc}",
            err=True,
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
    """Grava do microfone até o usuário apertar Enter. Retorna array mono float32."""
    click.echo("🎤 Fale... (Enter para parar)")
    frames: list = []
    q: queue.Queue = queue.Queue()

    def callback(indata, _frames, _time, status):
        if status:
            pass  # xruns ocasionais são inofensivos
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


def _to_wav_bytes(audio, sf) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE_IN, format="WAV", subtype="PCM_16")
    return buf.getvalue()


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
                    sent,
                    voice_id=voice_id,
                    output_format="wav",  # WAV = fácil de decodificar/tocar
                    language=language,
                )
                data, sr = sf.read(io.BytesIO(result.audio), dtype="float32")
                audio_q.put((data, sr))
            except Exception as exc:  # noqa: BLE001
                click.echo(f"[voz] falha ao sintetizar: {exc}", err=True)
        audio_q.put(None)  # sentinela de fim

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
    default="",
    help="voice_id da Cartesia (vazio = voz British Butler padrão).",
)
@click.option("--whisper-model", default="small", show_default=True, help="Tamanho do Whisper (STT).")
def main(model: str, engine_key: str, language: str, voice_id: str, whisper_model: str) -> None:
    """Conversa por voz com o Flux (persona + ferramentas + voz fluida)."""
    np, sd, sf = _require_audio()

    if not os.environ.get("CARTESIA_API_KEY"):
        click.echo(
            "Erro: CARTESIA_API_KEY não definida. Configure sua chave da Cartesia:\n"
            '  Windows:  setx CARTESIA_API_KEY "sua-chave"   (reabra o terminal)\n'
            '  Linux/Mac: export CARTESIA_API_KEY="sua-chave"',
            err=True,
        )
        sys.exit(1)

    try:
        from openjarvis import Jarvis
        from openjarvis.speech.cartesia_tts import CartesiaTTSBackend
        from openjarvis.speech.faster_whisper import FasterWhisperBackend
    except ImportError as exc:
        click.echo(
            f"Erro: openjarvis/áudio não instalado ({exc}).\n"
            "Rode:  uv sync --extra dev --extra desktop",
            err=True,
        )
        sys.exit(1)

    # Motores: STT local, TTS Cartesia, cérebro local
    stt = FasterWhisperBackend(model_size=whisper_model, device="auto", compute_type="int8")
    tts = CartesiaTTSBackend(model="sonic", language=language)

    try:
        flux = Jarvis(model=model, engine_key=engine_key)
    except Exception as exc:  # noqa: BLE001
        click.echo(
            f"Erro ao iniciar o Flux — {exc}\n"
            "O engine está no ar? Para Ollama:  ollama serve  &&  "
            f"ollama pull {model}",
            err=True,
        )
        sys.exit(1)

    persona = _load_persona()
    # Ferramentas: respeita o config (aceita lista OU string "a,b,c"); fallback útil.
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

    click.echo("─" * 60)
    click.echo(f"Flux (voz) pronto. Modelo: {model} | Voz: Cartesia | STT: whisper-{whisper_model}")
    click.echo("Enter para falar; diga 'sair' ou Ctrl+C para encerrar.")
    click.echo("─" * 60)

    try:
        while True:
            input("\n[Enter para falar] ")
            audio = record_until_enter(sd, np)
            if audio is None or len(audio) < SAMPLE_RATE_IN // 2:
                click.echo("(nada capturado)")
                continue

            # Transcreve (local)
            try:
                result = stt.transcribe(_to_wav_bytes(audio, sf), format="wav", language=language)
                user_text = (getattr(result, "text", "") or "").strip()
            except Exception as exc:  # noqa: BLE001
                click.echo(f"[stt] falha ao transcrever: {exc}", err=True)
                continue

            if not user_text:
                click.echo("(não entendi)")
                continue

            click.echo(f"\n👤 senhor: {user_text}")
            if user_text.lower().strip(" .!?") in {"sair", "tchau", "encerrar", "fim"}:
                speak_fluid("Às ordens, senhor. Até logo.", tts, voice_id, language, sd, sf, np)
                break

            # Monta o prompt: persona + histórico recente + fala atual
            convo = "\n".join(f"Senhor: {u}\nFlux: {a}" for u, a in history[-4:])
            query = f"{persona}\n\n{convo}\n\nSenhor: {user_text}\nFlux:".strip()

            try:
                reply = flux.ask(query, agent="orchestrator", tools=tools)
            except Exception as exc:  # noqa: BLE001
                click.echo(f"[flux] erro: {exc}", err=True)
                continue

            reply = (reply or "").strip()
            click.echo(f"🎩 Flux: {reply}")
            speak_fluid(reply, tts, voice_id, language, sd, sf, np)
            history.append((user_text, reply))
    except KeyboardInterrupt:
        click.echo("\nEncerrado, senhor.")
    finally:
        flux.close()


if __name__ == "__main__":
    main()
