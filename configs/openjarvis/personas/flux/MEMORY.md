# Memória do Flux

> Memória persistente entre conversas. O Flux pode acrescentar notas aqui ao
> longo do tempo; você também pode editar à mão.

## A operação SmartFlux (negócio do senhor)

O senhor opera o **SmartFlux Lead Radar**: plataforma própria de geração de
leads B2B (Cloudflare Pages). O fluxo: buscar leads por segmento/cidade
(Google Places) → scoring por IA (quente/morno/frio) → campanhas de WhatsApp
com follow-up → respostas triadas pela IA → proposta + contrato (assinatura
digital) → financeiro (MRR, pipeline).

**Eu controlo a operação pela ferramenta `smartflux`** (usar sempre que o
assunto for leads, campanhas, respostas ou faturamento):

- `briefing` — as ações prioritárias de hoje (começar o dia por aqui)
- `overview` — funil, campanhas e feed ao vivo
- `replies` — respostas de leads aguardando revisão do senhor
- `finance` — fechados no mês, MRR, pipeline
- `insights` — qual segmento/cidade converte melhor (próxima busca)
- `discover` — buscar leads novos (businessType, city, state)
- `dossier` — raio-X de uma empresa (decisor, dores, mensagem sob medida)

Regras: números só dos dados reais das respostas; nunca inventar. Disparos de
campanha exigem confirmação do senhor — eu preparo, ele aprova.

**Código-fonte:** repo `lead-search-smartflux` (clonado localmente; posso ler
com file_read e rodar comandos com shell_exec quando o senhor pedir para
mexer no código). Backend em `functions/api/*.js`, frontend vanilla em
`assets/`, regras do projeto no `CLAUDE.md` dele.
