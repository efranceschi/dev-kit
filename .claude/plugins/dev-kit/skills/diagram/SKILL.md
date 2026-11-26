---
name: diagram
description: Draws the diagrams of the system being built in the style of draw.io, without draw.io - the high-level architecture (users, clients, services, jobs, stores, outside services and how they talk), the data model (entities, key fields, relationships) and the deployment (environments, hosts, managed services) - as SVGs in docs/diagrams/ (shown on the board's Architecture tab and in the docs) plus .drawio files anyone can open in draw.io. Use when the board's Architecture button asks for it, when the architecture changed, or as part of architecture, a passed QA gate (when out of date) and docs (mandatory there).
argument-hint: "[update] [architecture | data | deploy]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# diagram

Kit root (`<KIT>` in shared files and agents): `${CLAUDE_SKILL_DIR}/../core`. Include `Kit root: ${CLAUDE_SKILL_DIR}/../core` in the prompt of every agent you spawn. Work from the project root (`${CLAUDE_PROJECT_DIR}`) and do not `cd` away from it.

Session log: record `skill_start` / `skill_end` (with `status` and a brief `feedback` on the dev-kit itself; the script measures the duration and the plugin hooks log every agent) and pause events as `${CLAUDE_SKILL_DIR}/../core/shared/conventions.md` §13 says (allowed keys: `${CLAUDE_SKILL_DIR}/../core/shared/telemetry-schema.json`), with `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" event <type> --set key=value`. Never put project text into an event.

Input: $ARGUMENTS (`update` redraws existing diagrams; without it, a missing diagram is created and an existing one is updated. A kind - `architecture`, `data`, `deploy` - limits the run to that diagram; without one, every kind that applies is drawn: `architecture` always, `data` when `.dev/architecture.md` §4 has entities, `deploy` when §7 describes where it runs)
State: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --short --quiet-if-missing`
Diagrams: !`python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_diagram.py" --root "${CLAUDE_PROJECT_DIR}" check --kind all --info`

Let `DG` = `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_diagram.py" --root "${CLAUDE_PROJECT_DIR}"`.

draw.io is never needed: you write the model (what the system is made of), and `DG render --kind <kind>` draws it, always the same way, as an SVG in draw.io's look (its palette, swimlanes, cylinders for data, dashed boxes for external services, tables for entities, right-angle connectors) and as an uncompressed `.drawio` file with the same picture for whoever wants to edit it in draw.io.

| kind | model, picture, draw.io file in `docs/diagrams/` | drawn from |
|---|---|---|
| `architecture` | `architecture.json`, `.svg`, `.drawio` | the whole `.dev/architecture.md` and the code |
| `data` | `data-model.json`, `.svg`, `.drawio` | `architecture.md` §4 (data model), the migrations or schema |
| `deploy` | `deployment.json`, `.svg`, `.drawio` | `architecture.md` §7 (environments), the deploy files |

Each picture is out of date only when its own source changes: a new entity in §4 leaves the deploy diagram current.

## Procedure
Run steps 1 to 6 for each kind of this run, `architecture` first.

1. Read `.dev/architecture.md` (stack table, context diagram, repository layout, data model, contracts, environments), `.dev/decisions.md`, the brief's blocks 4–6 when there is no architecture yet, and the code that shows what really runs: manifests, `docker-compose*`/`compose*`, `Procfile`, `.env.example` (variable **names** only), the entry points, the deploy files, and the clients of outside services (grep the HTTP/SDK clients). Brownfield (state has `brownfield`): also `.dev/discovery.md`. What is built wins over what was planned: a planned component that does not exist yet is left out, or drawn with `(planned)` at the end of its label when the architecture says it ships in an open milestone. **Before construction** (no milestone has a done task, e.g. when `architecture` runs this skill): nothing is built yet, so draw the whole design as planned, with no `(planned)` labels, and say `as planned` in the `subtitle`.
2. Write or update the model of the kind (`DG example --kind <kind>` prints the format; the docstring of `dev_diagram.py` lists the fields). For `architecture`:
   - **High level only**: deployable units and stores, not classes, modules or endpoints; at most 8 layers, 8 nodes per layer, 40 nodes. Group what is alike (e.g. "Admin pages" inside the web app, not one node per page).
   - **Layers top to bottom** in the order a request travels: people (`actor`), clients (`client`: web, mobile, CLI), edge and services (`service`, `worker` for jobs and schedulers), then data (`database`, `storage`, `cache`, `queue`) and outside services (`external`). Inside a layer, put next to each other the nodes that talk the most, to keep lines short.
   - Every node has a short `label` (its role, in the language of the developer docs, `docs` step 1) and `tech` (framework or product with its major version, from the stack table).
   - Every edge says what flows in a 1–3 word `label` (`HTTPS / JSON`, `SQL`, `publish`, `OAuth`), with `style` `sync` for a call, `async` for a message or event, `data` for reads and writes to a store; `both: true` only for a real two-way exchange.
   - `title` is the product's name followed by "architecture" in the docs language; `subtitle` says what the picture shows and the version or date (e.g. `as built at v1.4.0`). Translate the legend with `legend` when the docs are not in English.
   - With `update`, keep the ids of nodes that still exist, so the `.drawio` file stays comparable between versions; remove what is gone.

   For `data`: one `entity` node per entity of §4 (and of the migrations or schema once code exists), `fields` with the primary key first (`PK id uuid`), then the foreign keys (`FK order_id`), then at most the few fields that explain the entity (12 at most: not every column). Layers group entities by area (e.g. Customers, Sales, Catalogue), placing an entity next to those it joins most. One `relation` edge per relationship, labelled with its cardinality (`1 — N`, `N — N` through its join entity, `1 — 0..1`). An entity that only references outside data (an id from an external service) gets an `external` node for that service.

   For `deploy`: layers from the outside in: the Internet (`actor`), the edge (`network`: DNS, CDN, load balancer, TLS), then each host or platform where code runs (a VM, a cluster, a serverless platform; its label says which environment: production, staging), then managed services (`database`, `storage`, `queue`, `cache`) and outside services. Nodes are what is deployed (containers, functions, processes), with their `tech` (`Docker`, `systemd`, `Lambda`). Edges say the protocol and port when it matters (`HTTPS 443`, `SQL / TLS`). Production only, unless the environments differ in shape; secrets and hostnames never appear.
3. `DG render --kind <kind>`. When it prints errors, fix the model and run it again until it draws.
4. Look at the result: read the SVG and check, for `architecture`, that every container of the stack table, every store of the data model and every outside service of the contracts is there exactly once, and that nothing is drawn that the code does not have (for `data`: every entity of §4 exactly once; for `deploy`: every environment row of §7 that runs code). Fix the model and render again when it is not true.
5. Link it from the documentation when the link is missing: `.dev/architecture.md` §2 (context diagram) gets `![Architecture](../docs/diagrams/architecture.svg)` above its text diagram, §4 gets `![Data model](../docs/diagrams/data-model.svg)` above its `erDiagram`, §7 gets `![Deployment](../docs/diagrams/deployment.svg)`; the README's project structure section gets the architecture picture with a line saying the `.drawio` files in `docs/diagrams/` open in draw.io, and the developer docs link the other two where they describe the database and the deployment. Never remove the text or Mermaid diagrams of `architecture.md`. When this step edited `.dev/architecture.md`, run `DG render --kind <kind>` again for every kind of this run: the SVG's stamp hashes its part of that file, so the diagram would otherwise be out of date at once.
6. `DG check --kind all` must print that every diagram is current. Report in the user's language, per kind: created or updated, layers, nodes and edges, what changed since the previous version (nodes added or removed), and the paths. The files are part of the project's documentation: they are committed with the docs (`docs: diagrams` when committed alone).

## Board
The board's Architecture tab shows the three pictures, one at a time (System · Data · Deployment; only shows them: they are drawn and redrawn here). This skill asks nothing: it works from the files.

## Who runs it
Besides the user: `architecture` (step 5a, and its `review` mode when the architecture changed) draws the planned diagrams; `qa` redraws them as built after a passed gate when `DG check --kind all` says one is missing or out of date; `docs` always runs it with `update` (the final version for the release). `implement` never runs it.

**Last line** (`conventions.md` §15): end the final report with the next command alone on the last line, written in full: the one `python3 -I "${CLAUDE_SKILL_DIR}/../core/scripts/dev_state.py" --root "${CLAUDE_PROJECT_DIR}" status --next` prints. Claude Code then offers it as the greyed-out prompt suggestion (Tab or Right arrow).
