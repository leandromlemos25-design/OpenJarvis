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
# 1. extras de áudio + libs deste script
uv sync --extra dev --extra desktop
uv pip install sounddevice soundfile numpy
# 2. chave da Cartesia (voz fluida)
#    Windows:  setx CARTESIA_API_KEY "sua-chave"   (reabra o terminal)
#    Linux/Mac: export CARTESIA_API_KEY="sua-chave"
# 3. rodar
uv run python examples/flux/flux_voice.py
```

Enter para falar; Enter de novo para parar. Diga "sair" ou Ctrl+C para encerrar.
Voz em PT-BR: passe `--voice <voice_id-da-Cartesia>` (veja vozes em play.cartesia.ai).
