# minhas-skills

Marketplace pessoal de plugins do Claude Code. Cada suíte é um plugin em `.claude/plugins/`; esses arquivos são a única fonte.

| Plugin | Conteúdo | Docs |
|---|---|---|
| `dev-kit` | Constrói aplicações completas, da entrevista ao lançamento | `.claude/plugins/dev-kit/skills/dev-core/docs/README.md` |
| `3d-maker` | Peças 3D grandes e encaixáveis, do requisito ao STL | `.claude/plugins/3d-maker/skills/pecas-3d-encaixaveis/SKILL.md` |
| `casa-inteligente` | Home Assistant (API REST e MCP) e MQTT com usuário e senha | `.claude/plugins/casa-inteligente/skills/*/SKILL.md` |

## Uso

```
/plugin marketplace add <caminho-desta-pasta-ou-repo-git>
/plugin install dev-kit@minhas-skills
/plugin install 3d-maker@minhas-skills
/plugin install casa-inteligente@minhas-skills
```

Para testar durante a edição, sem instalar: `claude --plugin-dir ./.claude/plugins/dev-kit`.

Novo plugin: crie `.claude/plugins/<nome>/.claude-plugin/plugin.json` com `skills/`, `agents/` etc. na raiz do plugin e adicione-o ao `.claude-plugin/marketplace.json`.
