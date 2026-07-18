# Flux — assistente pessoal do senhor

Este é um fork personalizado do [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
configurado como **Flux**: um assistente de IA local, em português, com jeito de
mordomo, que roda na sua máquina.

> O OpenJarvis é a base (o motor). **Flux** é o nome, a voz e a configuração do
> assistente — a camada que é sua.

## O que foi personalizado

| Item | Onde |
|---|---|
| Personalidade do assistente (chat/agentes) | `configs/openjarvis/personas/flux/{SOUL,MEMORY,USER}.md` |
| Voz do briefing falado (digest) | `configs/openjarvis/prompts/personas/flux.md` |
| Config pronta (Ollama + persona Flux) | `configs/openjarvis/examples/flux.toml` |
| Instalador da personalização | `scripts/setup_flux.sh` |
| Agente de exemplo (starter) | `examples/flux/flux.py` |

## Instalação (rodar localmente — recomendado)

O Flux foi feito para rodar **na sua máquina**, não em serverless (Vercel não
serve: precisa de processo persistente + inferência local). Passos:

```bash
# 1. Instale o Ollama e baixe um modelo
#    https://ollama.com
ollama pull qwen3.5:9b        # ou qwen3.5:4b numa máquina mais modesta

# 2. Instale o OpenJarvis (a partir da raiz do repo)
uv sync --extra dev --extra desktop --extra flux-voice --extra server
# ATENÇÃO: todo `uv sync` remove a extensão nativa Rust — recompile sempre depois:
uv run maturin develop --manifest-path rust/crates/openjarvis-python/Cargo.toml

# 3. Instale a personalização do Flux (persona + config em ~/.openjarvis)
bash scripts/setup_flux.sh

# 4. Diga quem é você
$EDITOR ~/.openjarvis/personas/flux/USER.md

# 5. Converse
jarvis
```

Ou use o agente de exemplo direto:

```bash
python examples/flux/flux.py "resuma minha agenda ideal para focar hoje"
```

## Falar com o Flux (voz mão-dupla, fluida)

O Flux tem um **modo voz**: você fala, ele responde **falando** com voz de mordomo.

- 🧠 Cérebro (LLM) e 👂 transcrição (faster-whisper): **locais e privados**.
- 🔊 Voz de saída: **Cartesia** (nuvem) — única forma de soar *bem fluida* em PT-BR.

```bash
uv sync --extra dev --extra desktop --extra flux-voice --extra server
setx CARTESIA_API_KEY "sua-chave"        # Windows (reabra o terminal); export no Linux/Mac
# Windows: rode pela venv direto p/ não perder a extensão nativa/áudio:
.venv\Scripts\python.exe examples\flux\flux_voice.py
# (ou, sem re-sincronizar deps:  uv run --no-sync python examples/flux/flux_voice.py)
```

Opções úteis: `--hands-free` (sem apertar Enter, detecta fala por VAD),
`--device cuda` (GPU, precisa CUDA/cuBLAS; padrão é `cpu`), `--model qwen3.5:35b`.
Detalhes e voz PT-BR: [`examples/flux/README.md`](examples/flux/README.md).

**Interface web (`jarvis serve`) — voz mão-dupla no navegador:** a web deste fork
fala as respostas de volta com a voz do Flux (Cartesia). Requisitos: a variável
`CARTESIA_API_KEY` definida **antes** de rodar `jarvis serve`, e pronto — abra
`http://localhost:8000`, o microfone dita (STT local) e o alto-falante 🔊 no campo
de mensagem liga/desliga a voz das respostas (ligada por padrão). O build do
frontend já vem commitado — não precisa de Node/npm na sua máquina.

## Atualizar o Flux (web) sem dor

A versão do pacote vem de *git tag*, então `git pull` sozinho **não** atualiza a
interface web servida pelo `jarvis serve` (o `static` fica congelado no `.venv`).

**Ordem correta ao atualizar** (parar ANTES do sync — o servidor rodando trava os
arquivos da venv e o sync quebra com "error 32"):

```bash
Stop-Process -Name jarvis -Force          # 1. parar o servidor primeiro
git pull origin main                       # 2. puxar
uv sync --reinstall-package openjarvis --extra dev --extra desktop --extra flux-voice --extra server
uv run maturin develop --manifest-path rust/crates/openjarvis-python/Cargo.toml
.venv\Scripts\jarvis.exe serve             # 3. subir de novo
```

**Fim da dança (recomendado):** instale em modo *editable* uma vez — aí `git pull`
reflete na hora, sem reinstalar nunca mais:

```bash
uv pip install -e . --no-deps
```

## Deixar o Flux online

Para acessar de fora (celular, outro PC), veja **[deploy/flux-online.md](deploy/flux-online.md)**.
Resumo: rode o Flux na sua máquina (seus 64GB dão conta) e exponha por um túnel
(Tailscale ou Cloudflare Tunnel) — sem abrir portas. Vercel/serverless não serve.

## Trocar o modelo

Edite `~/.openjarvis/config.toml` (ou `configs/openjarvis/examples/flux.toml`
antes de instalar) e ajuste `default_model`:

- `qwen3.5:4b` — leve e rápido
- `qwen3.5:9b` — equilíbrio (16GB+ RAM)
- `qwen3.5:35b` — melhor qualidade (32GB+ RAM)

Máquina fraca? Dá para usar a nuvem só para "pensar": veja o modo
`inference-cloud` na doc do OpenJarvis (`pyproject.toml`) e configure
`[engine] default = "cloud"` com sua API key.

## Sobre o "rebranding" completo

O nome do assistente (Flux, a voz, a config) já é seu. **Não** renomeamos o
pacote Python `openjarvis` de propósito: isso quebraria imports, o comando
`jarvis`, o `pip install` e toda a documentação — muito custo, zero ganho para
uso pessoal. Se um dia você quiser publicar como produto próprio, aí sim vale
um rename cuidadoso; me avise.

## Crédito

Construído sobre o [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
(Stanford Hazy Research / Scaling Intelligence Lab), licença Apache 2.0.
Veja [`LICENSE`](LICENSE) e [`README.md`](README.md).
