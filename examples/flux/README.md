# Flux (exemplo)

Agente de exemplo do **Flux**, o assistente pessoal personalizado deste fork.
É um ponto de partida — copie e adapte para suas próprias rotinas.

```bash
python examples/flux/flux.py "que devo priorizar hoje?"
python examples/flux/flux.py --agent simple "traduza para inglês: bom dia"
python examples/flux/flux.py --model qwen3.5:4b "..."   # modelo mais leve
```

Pré-requisitos: Ollama no ar (`ollama serve`) e um modelo (`ollama pull qwen3.5:9b`).
Veja o guia completo em [`../../FLUX.md`](../../FLUX.md).

## Modo voz (mão-dupla, fluido) — `flux_voice.py`

Você fala, o Flux responde **falando** (voz "British Butler" da Cartesia).
Cérebro e transcrição rodam **locais**; só a voz de saída vai à nuvem.

```bash
# 1. extras de áudio (grupo flux-voice = sounddevice + soundfile + numpy)
uv sync --extra dev --extra desktop --extra flux-voice --extra server
#    todo `uv sync` remove a extensão Rust — recompile depois:
uv run maturin develop --manifest-path rust/crates/openjarvis-python/Cargo.toml
# 2. chave da Cartesia (voz fluida)
#    Windows:  setx CARTESIA_API_KEY "sua-chave"   (reabra o terminal)
#    Linux/Mac: export CARTESIA_API_KEY="sua-chave"
# 3. rodar (Windows: pela venv direto, p/ não perder a extensão nativa/áudio)
.venv\Scripts\python.exe examples\flux\flux_voice.py
#    (ou sem re-sincronizar deps:  uv run --no-sync python examples/flux/flux_voice.py)
```

Enter para falar; Enter de novo para parar. Diga "sair" ou Ctrl+C para encerrar.

Opções:
- `--hands-free` — sem apertar Enter; detecta sua fala por VAD (silêncio encerra).
  Se disparar cedo/tarde demais, ajuste com `--vad-threshold 0.02` (menor = mais sensível).
- `--device cuda` — usa a GPU (precisa CUDA/cuBLAS instalados). Padrão é `cpu` (sempre funciona).
- `--voice <voice_id>` — troca a voz (padrão já é a sua). Vozes em play.cartesia.ai.
- `--model qwen3.5:35b` — respostas mais "inteligentes" (um pouco mais lentas).

> **Nota Windows:** `uv run`/`uv sync` sem os extras podem *remover* a extensão nativa
> `openjarvis_rust` e as libs de áudio. Por isso rode pela venv direto
> (`.venv\Scripts\python.exe ...`) ou use `uv run --no-sync`.

> **Web fala de volta?** Sim (neste fork): com `CARTESIA_API_KEY` no ambiente,
> `jarvis serve` + navegador dão voz mão-dupla — mic dita (STT local) e as
> respostas saem faladas na voz do Flux (botão 🔊 no campo de mensagem).
> Este script continua sendo a opção de terminal (com `--hands-free`/VAD).
