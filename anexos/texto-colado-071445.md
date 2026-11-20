Base: 52,3 h de atividade registrada, somando o tempo dos agentes e das skills. O tempo de uma skill inclui a espera pelos agentes que ela chama, então as porcentagens se sobrepõem em parte. Em cada item, "tempo médio (min)" é a média por execução, e "tempo médio (max)" é a execução mais longa, as duas em minutos.

agente: implementer

- % do tempo gasto: 37,2%
- quantidade de acionamentos: 66
- tempo médio (min): 17,7
- tempo médio (max): 97,8
- melhorias propostas:
  a. Contrato no brief. Separar a "verificação do implementer" da "verificação do orquestrador". O implementer roda unit, lint e só os testes de integração dos ACs da task (-k AC-n), e a suíte completa roda uma vez, depois do merge.
  b. Mais detalhe no plano. O plano passa a ter um campo contract por task, com colunas, rotas e nomes de campos que outras tasks consomem. O kit inclui esse campo no brief de quem produz e de quem consome, e evita descompasso entre as duas pontas.
  c. Restrições do worktree no prompt padrão. O prompt diz que heredoc e comandos compostos são recusados e manda usar Write/Edit e scripts em arquivo. Quase todo implementer perdeu tempo descobrindo isso.
  d. Trava de recursos exclusivos no kit. Uma trava de primeira classe para recursos que não aceitam uso paralelo (sessão remota, banco compartilhado, emulador), em vez de cada projeto inventar a sua.
  e. Arquivos de acúmulo por task. CHANGELOG, README e registros de setup viram fragmentos por task (por exemplo changelog.d/T-xxx.md), juntados no release, o que elimina conflitos de merge no paralelismo.
  f. Autocheck antes de entregar. Um checklist curto por dimensão (strings novas no padrão de microcopy, axe nos testes de componente, invariantes de dados) para chegar à QA com menos achados.

skill: qa

- % do tempo gasto: 8,6%
- quantidade de acionamentos: 2 (registrados)
- tempo médio (min): 135,0
- tempo médio (max): 150,0
- melhorias propostas:
  a. Baseline compartilhado. O orquestrador roda a suíte e as integrações uma vez e grava o resultado num artefato (.dev/qa/<M>/baseline.json) que todos os auditores leem. Hoje vários auditores rodam o make check de novo.
  b. Seleção de auditores no delta pelo diff. Na rodada ≥ 2, chamar só os auditores com achado aberto ou cujo diff toca a sua dimensão; os outros mantêm o relatório anterior automaticamente.
  c. Gate de dados antes dos auditores. Um "smoke de dados" pós-deploy (tabelas novas com linhas, jobs com status ok) evita gastar a rodada 1 em falhas que um teste de 1 minuto pegaria.
  d. Fila por classe de custo. Os auditores estáticos começam na hora; os que dependem do ambiente esperam o fim de jobs longos (backfill, pipeline). Hoje o orquestrador faz isso à mão.
  e. Consolidação automática. Um comando do kit gera findings-round-N.json (abertos + novos + adiados) a partir dos relatórios brutos, em vez de um script ad hoc por projeto.
  f. Validar o JSON na hora. Se o relatório veio sem o bloco JSON, pedir o bloco automaticamente ao mesmo agente.

agente: test-auditor

- % do tempo gasto: 6,6%
- quantidade de acionamentos: 17
- tempo médio (min): 12,2
- tempo médio (max): 58,7
- melhorias propostas:
  a. Não executar a suíte. O auditor recebe o baseline do orquestrador e foca no que só ele faz: ver se cada AC tem teste com asserção real, se há flakiness e cobertura.
  b. Integração por amostragem. Rodar só os testes ligados aos ACs do milestone, com um orçamento de tempo explícito no prompt.
  c. Execução longa em segundo plano. Instrução padrão para disparar comandos longos em background e avaliar o código enquanto eles rodam.

agente: visual-reviewer

- % do tempo gasto: 6,5%
- quantidade de acionamentos: 15
- tempo médio (min): 13,7
- tempo médio (max): 32,4
- melhorias propostas:
  a. Sessão de navegador compartilhada com o a11y-auditor. Um passo do kit sobe o navegador, autentica e gera as capturas e o axe por tela e viewport; os dois agentes só analisam os artefatos.
  b. Capturas mínimas no delta. Só as telas e os viewports dos achados abertos mais as telas tocadas pelo diff, com lista gerada pelo kit.
  c. Mapa tela → rota no ui-spec. Rota e estados acessíveis por URL ajudam o auditor a não navegar por tentativa.

agente: performance-auditor

- % do tempo gasto: 6,4%
- quantidade de acionamentos: 13
- tempo médio (min): 15,4
- tempo médio (max): 47,7
- melhorias propostas:
  a. Benchmark versionado. Um arquivo de cenários fixos (queries, endpoints, parâmetros) que o auditor executa e compara com a rodada anterior, sem redescobrir o que medir.
  b. Separar frio e quente. O kit orienta como medir sem cache e com cache e pede as duas colunas no relatório.
  c. Ambiente quieto. Não rodar durante cargas concorrentes; o orquestrador marca no brief se há escrita em andamento.
  d. Resumo curto e JSON primeiro. O relatório longo cortou o bloco JSON.

agente: a11y-auditor

- % do tempo gasto: 5,9%
- quantidade de acionamentos: 16
- tempo médio (min): 11,6
- tempo médio (max): 32,4
- melhorias propostas:
  a. Reutilizar a sessão e as capturas do passo de navegador compartilhado (ver visual-reviewer).
  b. Mais a11y nos testes de componente. Incentivar o axe nos testes de componente desde a implementação, para o auditor focar em teclado, foco e anúncios.
  c. Separar global de escopo. Achados de componentes globais vão para uma lista à parte (issue), sem ruído no gate do milestone.

agente: requirements-reviewer

- % do tempo gasto: 3,7%
- quantidade de acionamentos: 17
- tempo médio (min): 6,9
- tempo médio (max): 13,0
- melhorias propostas:
  a. Diff do artefato no delta. Nas rodadas ≥ 2, mandar o diff do documento e não o documento inteiro.
  b. Lint estrutural antes. Ids, formato do parser, ACs sem task e dependências inexistentes saem num script (estender o sync-plan) antes de chamar o revisor.
  c. Separar forma de mérito. O revisor só avalia o mérito: testabilidade, lacunas e contradições.

skill: implement

- % do tempo gasto: 3,4%
- quantidade de acionamentos: 1 (registrado)
- tempo médio (min): 107,9
- tempo médio (max): 107,9
- melhorias propostas:
  a. Paralelismo por padrão. O next passa a devolver o conjunto de tasks prontas sem arquivos em comum, e o kit dispara todas.
  b. Merge assistido. Um comando do kit integra o worktree (commit, merge, check, done) e resolve conflitos triviais em arquivos de acúmulo.
  c. Brief comum gerado pelo kit. O prompt base do implementer sai do state e do architecture (perfil, regras, base do commit), sem manter à mão.
  d. Registrar skill_end por milestone. Hoje o log de tempo fica incompleto quando o orquestrador conduz o trabalho dentro da sessão.

skill: review

- % do tempo gasto: 3,3%
- quantidade de acionamentos: 3 (registrados)
- tempo médio (min): 34,6
- tempo médio (max): 46,3
- melhorias propostas:
  a. Revisões independentes em paralelo. Por exemplo PRD e design quando um não depende do outro.
  b. Delta com diff desde a rodada 2.
  c. Lista de artefatos desatualizados. Ao aprovar uma revisão que muda AC, o kit já lista o que ficou desatualizado (plano, design) e oferece rodar as próximas.

agente: spec-tracer

- % do tempo gasto: 3,3%
- quantidade de acionamentos: 17
- tempo médio (min): 6,1
- tempo médio (max): 9,1
- melhorias propostas:
  a. Matriz AC → task → teste por script. Grep dos ids no plano, código e testes; o agente só investiga as lacunas e as diferenças de comportamento.
  b. Acesso de leitura a comandos. Sem Bash, ele não confirma se os testes passam e precisa supor; pelo menos o resultado do baseline compartilhado no brief.
  c. Regra para achados duplicados. Definir no contrato o que fazer quando outro auditor já reportou o mesmo problema.

agente: copy-reviewer

- % do tempo gasto: 3,1%
- quantidade de acionamentos: 17
- tempo médio (min): 5,7
- tempo médio (max): 18,3
- melhorias propostas:
  a. Idioma no topo do brief, gerado pelo kit. Uma linha com o idioma da aplicação e o idioma do relatório evita achados falsos.
  b. Lista de strings novas. O kit extrai do diff as strings visíveis ao usuário e passa só essas.
  c. Literais travados. Marcar textos fixados por AC ou spec, para o revisor não pedir mudança que exige alterar requisito.

agente: data-reviewer

- % do tempo gasto: 2,6%
- quantidade de acionamentos: 12
- tempo médio (min): 6,7
- tempo médio (max): 19,8
- melhorias propostas:
  a. Invariantes versionadas. Um arquivo checks.sql (ou equivalente) com as invariantes dos ACs, mantido pelas tasks, que o auditor executa e interpreta.
  b. Checagem de cobertura da fonte. Uma pergunta padrão: a fonte cobre todo o universo do denominador? Ela evita descobrir tarde limitações como dados regionais versus globais.
  c. Rodar depois das cargas. O orquestrador só dispara o auditor depois de backfills e pipelines.

agente: security-auditor

- % do tempo gasto: 2,2%
- quantidade de acionamentos: 12
- tempo médio (min): 5,9
- tempo médio (max): 9,7
- melhorias propostas:
  a. Usar o baseline compartilhado, sem rodar a suíte de novo.
  b. Varredura de segredos e audit em cache, por commit e lockfile.
  c. Como marcar correção parcial. Definir no contrato quando um achado parcialmente corrigido fica open ou closed.

agente: code-reviewer

- % do tempo gasto: 1,7%
- quantidade de acionamentos: 14
- tempo médio (min): 3,8
- tempo médio (max): 7,7
- melhorias propostas:
  a. Diff restrito no delta: só os arquivos dos achados abertos e os alterados desde a rodada anterior.
  b. Usar o baseline compartilhado em vez de rodar o check.

agente: ops-reviewer

- % do tempo gasto: 1,3%
- quantidade de acionamentos: 13
- tempo médio (min): 3,2
- tempo médio (max): 8,2
- melhorias propostas:
  a. Disparo condicional: pular quando o diff não toca configuração, jobs, deploy, scripts de verificação ou setup.
  b. Checklist de runbook. Toda mudança que exige passo manual no deploy precisa de comando documentado, verificado por script.

skill: start

- % do tempo gasto: 0,8%
- quantidade de acionamentos: 1
- tempo médio (min): 26,7
- tempo médio (max): 26,7
- melhorias propostas:
  a. Poder registrar eventos antes do state. O log falhou nos primeiros eventos de projeto novo.
  b. Descoberta em paralelo. No onboarding, detectar stack, rodar testes e gerar ADRs retroativas em agentes paralelos.

skill: interview

- % do tempo gasto: 0,8%
- quantidade de acionamentos: 1
- tempo médio (min): 25,0
- tempo médio (max): 25,0
- melhorias propostas:
  a. Pergunta sobre fontes de dados. Cobertura, regionalidade e latência das fontes externas, que hoje só aparecem na QA.
  b. Pergunta sobre recursos exclusivos e ambiente de verificação. Por exemplo sessões que não aceitam paralelismo, para configurar a trava desde o início.
  c. Valor sem teto em paid_services. Aceitar explicitamente "sem teto" no preauthorize.

agente: design-reviewer

- % do tempo gasto: 0,6%
- quantidade de acionamentos: 6
- tempo médio (min): 3,1
- tempo médio (max): 5,5
- melhorias propostas:
  a. Contraste por script. O kit calcula o contraste dos tokens e o agente só interpreta.
  b. Validar literais novos. Conferir as strings de microcopy que as tasks inventam fora do ux-flows (hoje só se descobre na QA de copy).

agente: deps-auditor

- % do tempo gasto: 0,5%
- quantidade de acionamentos: 3
- tempo médio (min): 5,6
- tempo médio (max): 8,8
- melhorias propostas:
  a. Audit em cache por hash do lockfile.
  b. Ferramentas de audit no ambiente. O kit verifica e sugere instalar os auditores de cada ecossistema (por exemplo o de Python).
  c. Upgrades adiados vão direto para a fila de issues, com classe e esforço.

skill: architecture

- % do tempo gasto: 0,5%
- quantidade de acionamentos: 1
- tempo médio (min): 16,1
- tempo médio (max): 16,1
- melhorias propostas:
  a. Seção de "recursos exclusivos e limites do ambiente". Paralelismo, cotas e latências, que alimenta a trava e a seleção de tasks paralelas.
  b. Comandos de verificação por camada. Unit, integração e smoke de dados, para o kit montar o baseline compartilhado.

agente: architect

- % do tempo gasto: 0,4%
- quantidade de acionamentos: 1
- tempo médio (min): 13,1
- tempo médio (max): 13,1
- melhorias propostas:
  a. Pedir os limites das fontes de dados. Cobertura e regionalidade, como fato a verificar na recomendação.

skill: costs

- % do tempo gasto: 0,1%
- quantidade de acionamentos: 1
- tempo médio (min): 4,0
- tempo médio (max): 4,0
- melhorias propostas:
  a. Ingestão incremental, só dos transcripts novos ou alterados.
  b. Corrigir a contagem de requests. Com requestId ausente, contar por mensagem; hoje o relatório subconta.
  c. Preço de modelo ausente. Avisar e sugerir a entrada na tabela de preços.
  d. Relatório de tempo por agente e skill, como este ranking, junto com o de custo.

skill: ui

- % do tempo gasto: 0,1%
- quantidade de acionamentos: 1
- tempo médio (min): 2,7
- tempo médio (max): 2,7
- melhorias propostas:
  a. Mapa tela → rota → estados por URL, usado pelos auditores de navegador.

skill: ux

- % do tempo gasto: 0,1%
- quantidade de acionamentos: 1
- tempo médio (min): 2,2
- tempo médio (max): 2,2
- melhorias propostas:
  a. Catálogo de mensagens de validação genéricas (vazio, longo, duplicado), para as tasks não inventarem textos.

skill: prd

- % do tempo gasto: 0,1%
- quantidade de acionamentos: 1
- tempo médio (min): 2,2
- tempo médio (max): 2,2
- melhorias propostas:
  a. Marcar literais travados nos ACs, para os auditores de copy e visual saberem o que exige mudar o requisito.
  b. Premissas de dados verificáveis. Cada AC de dados cita a fonte e uma premissa de cobertura que o spike do milestone deve confirmar.

skill: plan

- % do tempo gasto: 0,0%
- quantidade de acionamentos: 1
- tempo médio (min): 0,1
- tempo médio (max): 0,1
- melhorias propostas:
  a. Campo contract por task (ver implementer).
  b. Spike de dados no início de milestones com fonte nova.
  c. Arquivos compartilhados marcados no plano, para o kit serializar ou fragmentar automaticamente.
