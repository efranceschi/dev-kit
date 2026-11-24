---
name: diagram
description: Draws the high-level architecture diagram of the system being built - the users, clients, services, jobs, data stores, queues and external services, and how they talk - in the style of draw.io, without draw.io, as docs/diagrams/architecture.svg (shown on the board and in the README) plus a .drawio file anyone can open in draw.io. Use when the board's Architecture button asks for it, when the architecture changed, or as part of docs (mandatory there).
argument-hint: "[update]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# diagram

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status` and a brief `feedback` on the dev-kit itself; the script measures the duration and the plugin hooks log every agent) and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says (allowed keys: `${CLAUDE_SKILL_DIR}/../core/shared/telemetry-schema.json`), with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS (`update` redraws an existing diagram; without it, a missing diagram is created and an existing one is updated)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`
Diagram: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_diagram.py" --root "${CLAUDE_PROJECT_DIR}" check --info`

Let `DG` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_diagram.py" --root "${CLAUDE_PROJECT_DIR}"`.

draw.io is never needed: you write the model (what the system is made of), and `DG render` draws it, always the same way, as an SVG in draw.io's look (its palette, swimlanes, cylinders for data, dashed boxes for external services, right-angle connectors) and as an uncompressed `.drawio` file with the same picture for whoever wants to edit it in draw.io.

## Procedure
1. Read `.dev/architecture.md` (stack table, context diagram, repository layout, data model, contracts, environments), `.dev/decisions.md`, the brief's blocks 4–6 when there is no architecture yet, and the code that shows what really runs: manifests, `docker-compose*`/`compose*`, `Procfile`, `.env.example` (variable **names** only), the entry points, the deploy files, and the clients of outside services (grep the HTTP/SDK clients). Brownfield (state has `brownfield`): also `.dev/discovery.md`. What is built wins over what was planned: a planned component that does not exist yet is left out, or drawn with `(planned)` at the end of its label when the architecture says it ships in an open milestone.
2. Write or update the model `docs/diagrams/architecture.json` (`DG example` prints the format; the docstring of `dev_diagram.py` lists the fields):
   - **High level only**: deployable units and stores, not classes, modules or endpoints; at most 8 layers, 8 nodes per layer, 40 nodes. Group what is alike (e.g. "Admin pages" inside the web app, not one node per page).
   - **Layers top to bottom** in the order a request travels: people (`actor`), clients (`client`: web, mobile, CLI), edge and services (`service`, `worker` for jobs and schedulers), then data (`database`, `storage`, `cache`, `queue`) and outside services (`external`). Inside a layer, put next to each other the nodes that talk the most, to keep lines short.
   - Every node has a short `label` (its role, in the language of the developer docs, `docs` step 1) and `tech` (framework or product with its major version, from the stack table).
   - Every edge says what flows in a 1–3 word `label` (`HTTPS / JSON`, `SQL`, `publish`, `OAuth`), with `style` `sync` for a call, `async` for a message or event, `data` for reads and writes to a store; `both: true` only for a real two-way exchange.
   - `title` is the product's name followed by "architecture" in the docs language; `subtitle` says what the picture shows and the version or date (e.g. `as built at v1.4.0`). Translate the legend with `legend` when the docs are not in English.
   - With `update`, keep the ids of nodes that still exist, so the `.drawio` file stays comparable between versions; remove what is gone.
3. `DG render`. When it prints errors, fix the model and run it again until it draws.
4. Look at the result: read `docs/diagrams/architecture.svg` and check that every container of the stack table, every store of the data model and every outside service of the contracts is there exactly once, and that nothing is drawn that the code does not have. Fix the model and render again when it is not true.
5. Link it from the documentation when the link is missing: `.dev/architecture.md` §2 (context diagram) gets `![Architecture](../docs/diagrams/architecture.svg)` above its text diagram, and the README's project structure section gets `![Architecture](docs/diagrams/architecture.svg)` with a line saying `docs/diagrams/architecture.drawio` opens in draw.io. Never remove the text diagram of `architecture.md`.
6. `DG check` must print that the diagram is current. Report in the user's language: created or updated, layers, nodes and edges, what changed since the previous version (nodes added or removed), and the paths. The three files are part of the project's documentation: they are committed with the docs (`docs: architecture diagram` when committed alone).

## Board
The board's Architecture tab shows `docs/diagrams/architecture.svg` (only shows it: it is drawn and redrawn here). This skill asks nothing: it works from the files.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
