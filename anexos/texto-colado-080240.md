````markdown
# Avaliação do dev-kit (v1.0.1) — projeto memory-archive

**Contexto:** app FastAPI + React, Postgres/pgvector, systemd. Execução de 14/11 a 18/11/2026, com autonomia "high" e `dev-autopilot`.
**Resultado até aqui:**
- 186 tarefas, 184 concluídas e 2 bloqueadas. Dessas 186, 98 são de correção (53%).
- 6 milestones com gate aprovado: M1 91, M2 86, M3 98, M4 94, M5 93, M6 94.
- 231 commits e mais de 4000 testes no backend, 1022 no vitest e 628 no e2e com 3 navegadores.
- Auditoria de usabilidade ainda reprovada: 40 na rodada 1, 47 na rodada 2, rodada 3 em andamento.
**Base:** `.dev/state.json`, `.dev/usage/report.md`, `.dev/usage/notes.md`, `.dev/qa/*` e o histórico da sessão.
**Volume de uso:** 314 transcrições de subagentes (`report.md` cobre até 17/11 03:41; não inclui as rodadas de QA do M6 e de usabilidade). Entre elas, 122 execuções do `dev-implementer`, com média de 45 min cada, e cerca de 200 auditorias. Não há total de tokens medido; os auditores das rodadas de usabilidade gastaram de 70 mil a 160 mil tokens cada.

## Notas por estágio

| Estágio | Nota | Resumo |
|---|---|---|
| dev-start / dev-status | 85 | Retomada e painel confiáveis |
| dev-interview | 85 | Brief completo em cerca de 16 min |
| dev-prd + dev-review prd | 55 | 4 rodadas e aprovação forçada com 52 |
| dev-architecture | 80 | Útil e rápido, mas sem revisão própria |
| dev-ux + dev-ui + dev-review design | 50 | 3 rodadas e aprovação forçada com 41 |
| dev-plan + dev-review plan | 85 | Passou com 85; tarefas executáveis |
| dev-implement (inclusive `--parallel`) | 72 | Entregou muito, com muito atrito no paralelo |
| dev-qa (gates por milestone) | 78 | Achou bugs reais, mas é caro e passou do limite de rodadas |
| dev-usability | 50 | Bons achados, nota que não converge |
| dev-autopilot | 68 | Longo e autônomo, mas travou e deixou a implantação de fora |
| Scripts (`dev_state.py` / `dev_score.py`) | 75 | Sólidos, com lacunas de manutenção |
| Implantação / operação | 25 | Não existe no fluxo |
| dev-docs / dev-release | — | Ainda não executados |
| **Geral** | **68** | Produto real e bem testado, a um custo alto |

## Comentários por estágio

### dev-start / dev-status (85)
- **Deu certo:**
  - O `dev_state.py status` foi chamado 283 vezes e sempre refletiu o estado real.
  - A retomada depois de travamentos e de um reboot funcionou: estado, gates e próximo passo vieram claros.
- **Deu errado:**
  - O status não sabe de agentes antigos ainda vivos.
  - Não avisa que a implantação está atrasada em relação ao checkout.

### dev-interview (85)
- **Deu certo:**
  - Foram 11 blocos de AskUserQuestion, com cerca de 40 perguntas, em uns 16 minutos.
  - Saiu um `brief.md` rico, cobrindo stack, autonomia, qualidade, privacidade e implantação.
  - O bloco de autonomia com `always_ask` funcionou bem durante todo o projeto.
- **Deu errado:**
  - Lacunas reapareceram logo no PRD: tokens e sessões, ingestão por CLI, convites, TOTP e custo de IA geraram mais 5 a 6 rodadas de perguntas.
  - Faltou perguntar sobre o ambiente de implantação contínua: como e quando instalar em produção.

### dev-prd + revisão (55)
- **Deu certo:**
  - Saíram critérios de aceite numerados e testáveis (AC-n), usados até o fim por testes e pelo spec-tracer.
  - O revisor pegou contradições reais.
- **Deu errado:**
  - Foram 4 rodadas, cerca de 1,5 h, e a aprovação teve de ser forçada com nota 52.
  - A régua (−8 por médio, −2 por baixo) pune documentos grandes. Um PRD extenso nunca chega a 85, e cada rodada revela achados novos em vez de fechar os antigos.
  - O resultado foi esforço e tokens gastos para terminar com uma aprovação manual.

### dev-architecture (80)
- **Deu certo:**
  - O `architecture.md` e as ADRs (mais de 139 ao longo do projeto) serviram de referência constante para implementadores e auditores.
  - Rodou numa única passada.
- **Deu errado:**
  - Não há revisão de arquitetura (`dev-review` não cobre).
  - Decisões sobre limites e operação, como PID 1 e reaping, só apareceram no QA.

### dev-ux + dev-ui + revisão de design (50)
- **Deu certo:**
  - O `ui-spec.md` e o `ui-screens.md` (S-01 a S-26, D-1 a D-4) deram consistência visual e foram usados pelos auditores como contrato.
- **Deu errado:**
  - Foram 3 rodadas e a aprovação teve de ser forçada com 41; o mesmo problema da régua por volume do PRD.
  - Faltaram itens que só a auditoria de usabilidade apontou no fim: menu do usuário, Ajuda, título no topo do celular, 404 e guarda de rota de admin.
  - O spec e a implementação divergiram (UserMenu como menu ou como lista) sem nenhum mecanismo de sincronização.

### dev-plan + revisão (85)
- **Deu certo:**
  - Passou com 85 em 3 rodadas.
  - As tarefas tinham AC, arquivos e dependências, e o `sync-plan` levou tudo para o `state.json`.
  - As fatias verticais por milestone funcionaram.
- **Deu errado:**
  - O `plan.md` diverge do `state.json`, porque não existe sincronização no sentido estado → plano. Foi preciso um script manual a pedido do spec-tracer.
  - 98 tarefas de correção entraram fora do plano, então o plano subestima o trabalho real em cerca de 2 vezes.

### dev-implement (72)
- **Deu certo:**
  - Foram 122 execuções do implementador, com 184 tarefas entregues, testes junto de cada tarefa e um commit por tarefa.
  - Código com qualidade de produção, aprovado em gates exigentes.
- **Deu errado:** no modo paralelo, os agentes compartilham árvore, portas e banco.
  - O `pre-commit` faz stash e restaura os arquivos no meio do trabalho dos outros agentes.
  - Um agente rodou `pkill` sem filtro e matou laços de espera de outros.
  - `ruff` e `prettier` rodaram na árvore toda e mexeram em tarefas alheias.
  - Um arquivo compartilhado impediu commits separados.
  - Os subagentes não enxergam as skills da sessão principal, como `claude-api`. A integração com a Anthropic foi escrita de memória, com 4 desvios da API atual.
  - O `done` registrou o SHA errado 4 vezes depois de um commit barrado por hook, e não existe comando para corrigir.
  - O orquestrador verificou tipos com `tsc --noEmit`, que não checa os projetos referenciados; só `tsc -b` mostrou um erro que já tinha passado pelo gate.

### dev-qa / gates (78)
- **Deu certo:**
  - Achou bugs reais e sérios: ReDoS no extrator, requeue sem limite no OOM, sanitizador de markdown, regressão de zumbis com PID 1 (pega por 2 auditores novos de forma independente), isolamento entre espaços e opt-out de AC.
  - Usar auditores novos a cada rodada se pagou.
  - O `dev_score.py` deu uma régua objetiva e o histórico ficou em `qa/<M>/`.
- **Deu errado:**
  - O custo é enorme: cerca de 11 auditores por rodada e um auditor de a11y com média de 83 min.
  - A carga no host chegou a 14 com 6 vCPU e derrubou o e2e (Firefox com "Page crashed").
  - O limite de 3 rodadas foi estourado em M1 (5), M2, M3 e M6 (4 cada), sempre com autorização do usuário.
  - Não há ferramenta para salvar o JSON dos auditores: o orquestrador extraiu à mão das transcrições, e os arquivos `raw` foram reescritos a partir dos relatórios.
  - Por economia, dimensões foram reaproveitadas da rodada anterior, o que contraria a regra de "fresh auditors".
  - Os prompts padrão não isolam portas e banco: um auditor matou o servidor de outro, outro migrou o banco alheio e o limite de 60 conexões do Postgres foi atingido.

### dev-usability (50)
- **Deu certo:**
  - Os achados são valiosos e não tinham aparecido nos gates de UI:
    - foco preso no menu "Mais";
    - chave e link de senha perdidos ao fechar sem copiar;
    - `/admin` aberto para membro;
    - dois botões "Aprovar" na Triagem;
    - lembrete concluído sem "Desfazer";
    - upload mostrando "Pronto" para arquivo sem texto.
  - Os relatórios trazem pontos fortes e capturas de tela; ajudam muito.
- **Deu errado:**
  - A nota não converge: 40, depois 47. A cada rodada, auditores novos trazem 20 a 30 achados baixos novos.
  - Dois auditores de usabilidade somam penalidades na mesma dimensão, o que levou a nota de UX a 10.
  - Com −2 por baixo, chegar a 85 num produto com 26 telas é quase impossível.
  - Cada rodada custa 5 agentes de 70 mil a 160 mil tokens, mais cerca de 1 h de correções e e2e.
  - Ele roda depois de todos os gates; boa parte dos achados (a11y, título, 404) deveria ter saído do `dev-ux` ou dos gates de UI.

### dev-autopilot (68)
- **Deu certo:**
  - Encadeou interview → PRD → arquitetura → design → plano → implementação → QA por dias.
  - Pausou corretamente nas decisões `always_ask` e no limite de rodadas.
- **Deu errado:**
  - A sessão travou duas vezes.
  - Agentes antigos ficaram vivos de 10 a 14 h por laços de espera `until ! pgrep`, que casavam com a própria linha de comando.
  - Os agentes deixam trabalho em background ao devolver o relatório.
  - Não há passo de implantação: o usuário notou que `/reminders` e `/ask` não estavam em produção, que ficou 2 dias atrás, com o banco na revisão 0031 de 0038.

### Scripts `dev_state.py` / `dev_score.py` (75)
- **Deu certo:**
  - Estado durável e consultável.
  - `add-task`, `gate` e `review` com `--count-run` funcionaram.
  - O score por dimensão com mínimos por dimensão é transparente.
- **Deu errado:** faltam comandos que, na prática, viraram scripts manuais ou correções à mão:
  - `set-commit`, ou um `done --force` que sobrescreva o SHA;
  - verificação de que o commit citado contém a tarefa;
  - sincronização do `plan.md` a partir do `state.json`;
  - `dev_score.py ingest <transcrição>`;
  - deduplicar auditores do mesmo tipo dentro de uma dimensão.

### Implantação / operação (25)
- **Deu certo:** o `install.sh` gerado pelo projeto é bom (dry-run, `pg_dump` antes de migrar, `/health`).
- **Deu errado:**
  - O dev-kit não tem estágio para isso: nenhuma skill pergunta ou executa a implantação ao fim de um milestone.
  - Pendências operacionais (credenciais do backup em S3, chaves VAPID, download do modelo de embeddings) ficam soltas em `open-questions`.

## Sugestões prioritárias para o plugin
1. **Régua de nota normalizada:** por tela ou por quantidade de itens; teto de penalidade para achados baixos; deduplicação entre auditores do mesmo tipo. Opção de aprovar com "0 críticos, 0 altos e no máximo N médios" em PRD, design e usabilidade.
2. **Isolamento de recursos nos prompts de auditores e implementadores:** porta, banco e pasta únicos por agente, encerramento só por PID, nada em background ao terminar, formatar só os próprios arquivos. Usar worktree por implementador no modo `--parallel`.
3. **Expor as skills relevantes da sessão aos subagentes**, como `claude-api` e `modern-web-guidance`, ou fazer uma revisão obrigatória no orquestrador quando a tarefa toca uma integração externa.
4. **Ferramentas novas nos scripts:** `dev_score.py ingest`, `dev_state.py set-commit`, verificação do commit, `plan-sync` no sentido estado → plano.
5. **Estágio `dev-deploy`** por milestone: dry-run, instalação e smoke test, com aprovação do usuário. Status mostrando a diferença entre o checkout e a produção.
6. **Antecipar a usabilidade:** heurísticas de usabilidade nos gates de milestones de UI, ou uma passada leve do `dev-usability` por milestone. Assim a auditoria final não vira uma esteira de achados baixos.
7. **Orçamento de custo por gate:** limitar a concorrência de auditores pela CPU do host e reportar o tempo e os tokens de cada rodada.
````