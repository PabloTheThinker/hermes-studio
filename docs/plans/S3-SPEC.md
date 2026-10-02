# S3 spec: project store, lock, event bus, plus Wire's registry and /mcp

**Status:** SPEC ONLY. No code, no branch, no PR. Written by Bay, Oct 1 2026, 6:30 PM ET; revised 6:41 PM ET after Wire's review (contract §1i) and Ada's 6:40 PM rulings; revised 6:56 PM ET for Ada's rulings 1–3, the C5 gate and Prove's D27 additions; revised 7:05 PM ET for Wire's five fixes, the D27 header match, Ada's cap ruling and the oversized-body rule; revised 7:11 PM ET for Ada's drain/close rulings, Prove's malformed-header proposal, the HTTP close-on-refusal ruling and tests 101–103; final edits 7:18 PM ET (HTTP header check and message, rulings on D4/D8/D17/D19/D25/D27/D28, Wire's five items, duplicate headers). Approved in full by Ada at 7:33 PM ET (all 31 decisions; source: the PR #42 body). §13 As built added for Ada's 8:28–8:29 PM approval. Ada's 8:58–9:02 PM rulings on Prove's pre-gate of PR #42 (F1, F2, O1–O4) folded in during recovery on Oct 1–2 (see **[R]** below).

**What I read.** Main is at `c6de84e` (#40 merged; tree `2eccb5b`). That's the same tree as `c1bbddb`: `git diff c1bbddb c6de84e` is empty. I made a worktree at `/workspace/hermes-studio-s3`, detached, with no commits. Every `file:line` below is at `c6de84e`.

**Sources.** PLAN-MERGED §4.1 and Prove C3–C9; SECTION-BAY-ENGINE §2 and the S3 row; SECTION-WIRE §1–§3; WIRE-S1-REGISTRY-CONTRACT §1–§1i and tests 1–104 (101–103 for D27; 104 for GET /mcp mid-stream).

**Labels used below.**
- **SETTLED:** code, docs or an Ada ruling already decides it, and I quote the source.
- **APPROVED:** ruled today by Ada and Prove, so it goes into the S3 build.
- **D*n*:** an open decision, with my recommendation (**Rec**) and the alternative (**Alt**).
- **Probe:** I ran it against the engine at `c6de84e`. The scripts are in `evidence/s3-spec/`.

**Rule ids:** no new ones. The oplog stays at 17 rules and the validator at 36 (§9).

**[R] Recovery note.** This file was restored from a backup taken before Ada's last rulings (8:28–9:02 PM ET, Oct 1). Text marked **[R]** was folded in afterwards from `S3-RULINGS-ADDENDUM.md` (Ada's rulings, authoritative), Wire's final contract (`WIRE-S1-REGISTRY-CONTRACT.md`, 9:02 PM state) and Prove's pre-gate (`records/PROVE-S3-PRE.md`). It states the rulings; it is **not** Bay's own final wording, which could not be recovered. See `RECOVERY-NOTES.md`.

---

## 1. Store

| Item | Spec | Source |
|---|---|---|
| Folder | `~/.hermes/clips/projects/<project_id>/`, holding `base.json` (the version-0 doc that `Oplog` replays from), `oplog.jsonl`, `timeline.json`, `snapshots/v<N:06d>.json` (one every 50 versions), `exports/`, `cache/` and `.lock` | PLAN-MERGED §4.1; `Oplog(base, path=…)` oplog.py:800; `load(base, path)` :1223 |
| Log line | The locked fields plus optional `step`. `load` rejects any other key | oplog.py:41–56; `_check_line` :787–790 |
| Line durability | A line is appended, flushed and fsynced before the write takes effect | oplog.py:1099–1105 |
| Atomic batch | The ops run on a copy, and the copy must pass `validate()`. If anything fails, nothing is applied | docs/oplog.md:65–66 |
| `project_id` | **SETTLED: it's the timeline `id`.** "optional `project_id` (must be this timeline's `id`)" (docs/oplog.md:59–60), checked at oplog.py:881–888. The folder uses the same id, and `ID_RE` (timeline.py:35) makes it safe as a path | — |

- **D1 Source of truth.** **Rec:** `base.json` + `oplog.jsonl` are the truth; `timeline.json` and the snapshots are caches. **Alt:** make `timeline.json` the truth. That breaks C4 (replay = live) whenever the two disagree.
- **D2 Commit order and crash recovery (C3).**
  - **Rec, commit order:** under the mutex, (1) fsync the line (as today); (2) write `timeline.json` with tmp + `os.replace` + a dir fsync; (3) write a snapshot when `new_version % 50 == 0`; (4) publish the event.
  - **Rec, on open:** replay from the nearest snapshot, and rewrite `timeline.json` if its hash differs.
  - **Rec, torn last line:** on open, the engine truncates a **torn final line** (no `\n` and not valid JSON) and logs it. Today `load` would raise `JSONDecodeError` at :1228. Any other bad line refuses the open. **Only the open engine (holding the lock) truncates.** The closed-app read never writes (D28(a)).
  - **Rec, missing final newline (Wire fix 3):** on open, if the final line is valid JSON (a complete record) but has no trailing `\n`, the engine writes the missing `\n` (and fsyncs) **before the next append**, so the next record can't merge into it.
    - Today, `load` accepts that file, and the next `_commit` appends `line + "\n"` right after it (oplog.py:1101–1102). The two records merge into one line, and the next `load` fails with `JSONDecodeError` "Extra data" (Probe `evidence/s3-spec/newline_merge_probe.py`/`.out`).
    - The closed-app read never writes; it parses that line normally. §11 row F.
  - **Alt:** refuse to open on a torn line. Then a `kill -9` mid-append bricks the project.
- **D28 What reads use, and what a corrupt store returns (Wire's blocker: tests 58, 61, 62).**
  - **(a) Read source, app open:** the engine's in-memory `Oplog` (`doc`, `head()`), under the D3 mutex. No file is read per call.
  - **(a) Read source, app closed (stdio proxy, test 58):** the proxy opens files **read-only** and never writes, not even to repair a cache, so C7's strace check holds. Steps:
    1. Read and `validate()` `base.json`.
    2. Read `oplog.jsonl` and **parse every line** (JSON + `_check_line` shape + `seq` continuity, the same checks `Oplog.load` does before replaying, oplog.py:1228–1232) **before trusting `timeline.json`** (Wire fix 2). A corrupt line in the middle gives `failed` with `seq` (as in (b)), the same answer as the open app.
       - A **torn final line** (no `\n`, not valid JSON) is **skipped in memory, never truncated**: the read is read-only (Wire fix 1). The last complete line is the log head.
       - A valid final line with no `\n` is a complete line and counts as the head.
       - The head is the last complete line's `hash`/`new_version`, or `base.json`'s when there's none.
    3. **Fast path:** if `timeline.json` parses, `validate()` passes (stored hash included) and its `hash` and `version` equal the log head, serve it.
    4. **Otherwise** replay `base.json` + log (`Oplog.load`, from the newest snapshot that validates and lies on the log) and serve that.
    `timeline.json` is never trusted on its own.
  - **(b) Corrupt `base.json`:** the store runs `timeline.validate()` on it **before** constructing `Oplog`. That's needed because `Oplog.__init__` calls `stamp_hash`, which skips the stored-hash check and re-stamps (oplog.py:801, timeline.py:684–690); Probe: a stale-hash base is accepted silently today. Results use **existing codes**: `schema_mismatch` (`bad_schema` @ `/schema_version`) or `invalid_doc` (`rule`/`path`/`id?`/`problems` verbatim, e.g. `hash_mismatch` @ `/hash`). No `hash` in the response. Same for every read tool, and the open app refuses to open the project with the same body.
  - **(b) Corrupt log line (not a torn tail, D2):** `load` raises a bare `ValueError` today ("not an oplog line" :789, "out of sequence" :1232, "replay does not reproduce the entry" :1235) or `JSONDecodeError` (:1228); Probe confirmed all three. **Rec:** the store catches them and answers **`code:"failed"`** (the existing generic code, the same one mcp.py:486–487 uses), `isError`, with `error` naming the line (`"oplog line 7: replay does not reproduce the entry"`), a `seq: 7` field and a `hint` ("The project log is damaged; restore the project folder from a backup"). **No rule id**, like `engine_offline`. No hash returned; writes refused with the same body. **Alt:** `invalid_doc` with a new rule `bad_oplog_line` @ `/oplog/<seq>`. That's a **new rule id** and would need Ada; I don't recommend it, because the log isn't a doc and the agent can't fix it.
  - **(b) Corrupt cache (`timeline.json` or a snapshot):** **never an error.** It's ignored and the doc is replayed. The open engine rewrites it on open (D2); a closed-app read just doesn't use it. A bad snapshot is skipped in favour of an older one or `base.json`, and noted in the engine log.
  - **Tests re-targeted (Wire to apply):**
    - **61(a)** unknown `schema_version`, **61(b)** stale `hash` and **62** three copies of `c9`: put the fault in **`base.json`** (empty log). Expected results are unchanged: `schema_mismatch`, `invalid_doc` `hash_mismatch` @ `/hash` with no `id`, `invalid_doc` with two `duplicate_id`. No hash in any response; no `.otio` written.
    - **New 61(c):** the same faults written into **`timeline.json`** only (base and log intact): `get_timeline`/`get_hash` **succeed**, with the hash of the log head. Closed app: nothing is written; open app: the file is rewritten on open.
    - **New 61(d), both app states (Wire fixes 1–2):**
      - A corrupt **middle** line (bad JSON, an unknown key, out of sequence) gives `failed` with `seq` and no hash, **whether the app is closed or open**.
      - A tampered `hash` on the **final** line also gives `failed` in both states: the closed path's fast-path check fails, so it replays.
      - A tampered `hash` on a **middle** line (valid JSON and shape) is found only by replay. So it's `failed` with the app open; with the app closed it's caught only when the fast path is skipped. Wire should target it at the open app, or put it on the final line (§12 finding 8).
      - **Torn final line, app open:** truncated on open (D2), and reads succeed at the last complete version.
      - **Torn final line, app closed:** reads succeed at the last complete line's `version`/`hash`, and `oplog.jsonl` is **byte-identical afterwards** (no truncation, nothing written; strace shows `O_RDONLY` only).
      - **Valid final line with no `\n`, app open:** after open and one write, the file has two well-formed lines, and a reload succeeds.
    - **58:** reads with the app closed come from the read-only path above; strace shows only `O_RDONLY` opens of `base.json`, `oplog.jsonl`, `timeline.json` and `snapshots/`. Writes and `export_otio` still give `engine_offline`.
- **D3 Concurrency.** **Rec:** one `threading.Lock` per project. It wraps `Oplog.call`, persisting and publishing, and every read that returns `version`/`hash`/`seq`. This is needed because `Oplog` has no lock of its own and `studio.py` uses `ThreadingHTTPServer` (studio.py:8, :792). **Alt:** a writer thread fed by a queue.
- **D4 Non-string `project_id`.** **Probe:** `project_id: 5` gives `not_found` with `id: "5"`, because of the `str()` at oplog.py:887. That breaks F2 (a non-string id must be `bad_arg` before any lookup).
  - **Rec:** return `bad_arg` @ `/project_id`, which is an existing rule. Wire also checked `null` → `id:"None"` and `true` → `id:"True"` today. /mcp requires `project_id`; the engine keeps it optional, and HTTP takes it from the URL.
  - **Rec, missing at /mcp (Wire ask 7):** /mcp gives `invalid_op` `missing_arg` @ `/project_id` (an existing rule, same shape as the engine's `_check_args`, oplog.py:860–861), before the engine is called. /mcp needs the id to pick the project, so it can't be engine-answered. This check is /mcp-only, so it joins the named §1h exemptions (§6).
  - **Alt:** keep `not_found` and document it.

## 2. Lock (C7, Glyph B)

| Item | Spec | Source |
|---|---|---|
| Scope | **The project, per engine process.** "One engine owns each project. The stdio `hermes-studio mcp` … attaches … never opens the project files for writing itself. A stale lock … is recovered" | PLAN-MERGED §4.1 |
| Contents | pid, port, token hash, plus an OS file lock | PLAN-MERGED §4.1 |
| App closed | Reads work. Writes and `export_otio` get `engine_offline` + `hint` | PLAN §8 decision 3; Wire's error table |

- **D5 Mechanism.**
  - **Rec, holding the lock:** the engine holds `flock(LOCK_EX|LOCK_NB)` (on Windows, `msvcrt.locking`) on `.lock` for as long as it runs.
  - **Rec, file content:** JSON `{pid, port, started_at (UTC ISO 8601), engine_version, attach_token_sha256}`.
  - **Rec, stale lock:** if the file exists but the OS lock can be taken, the lock is stale. The new engine takes over and rewrites the file.
  - **Alt:** check whether the pid is alive. That's racy, because pids get reused.
- **D6 A second engine.** **Rec:** a **startup error**: `HermesStudioError` `failed` (exit 1), naming the pid, port and `started_at`. Hint: "Project is open in Hermes Studio; `hermes-studio mcp` attaches to it." No tool caller ever sees this error (the proxy attaches, and a closed app gives `engine_offline`), so it needs **no rule id**. **Alt:** a tool-level code `project_locked`.
- **D7 Glyph's question: who holds it, and what does a write get while someone else holds it?**
  - In Phase 1, only an engine ever holds the lock, never an actor.
  - Inside one engine, writes are serialised (D3). A write waits for at most one commit and never gets a lock error.
  - A write against a timeline that has moved on gets **`conflict`** with `current_version` + `history_diff` (oplog.py:919–931), and the run pauses (PLAN §8 decision 6).
  - **Rec:** no actor edit lease in S3.
  - **Alt:** a lease (for example while a human drags). That needs a new rule `locked` with `{holder:{kind,id}, since, retry_after_ms}`, and Ada's approval. I don't recommend it.
- **D8 Reading the lock state.** **Rec:** a new read tool **`project_status{project_id}`** that returns `{project_id, schema_version, version, hash, seq, engine:{pid, port, started_at} | null, mode}`. `mode` stays `null` until S8. It works with the app closed (it reads `.lock`). Add it to Wire's registry and the C9 allowlist. **Alt:** fold the engine block into `get_hash`.

## 3. Event bus (C8, Glyph A)

| Item | Spec | Source |
|---|---|---|
| Feed | The bus is fed by the log: one append-only stream with a monotonic `seq`, sent over SSE, with `Last-Event-ID` replay | SECTION-BAY-ENGINE §3; SECTION-WIRE §2 |
| `undoes` | **SETTLED.** It's `null` for an apply. Otherwise it's the list of undone `op_id`s, newest first. A redo gives `[the undo entry]` | docs/oplog.md:52; **Probe:** redo `undoes == [undo op_id]` |

- **D9 Event types.**
  - **Rec, log events:** one event per **new log entry**: `op.applied` when `undoes` is null, and `op.undone` otherwise (that covers undo *and* redo). There is no `op.redone`, because after `load` an undo-of-undo *is* a redo (RULED, contract §1c).
  - **Rec, cached retries:** a cached retry emits **nothing**.
  - **Rec, ephemeral events:** `job.progress`, `approval.pending` and `run.paused` come in later slices. They're ephemeral: they carry no SSE `id`.
  - **Rec, `timeline.changed`:** reserved and not emitted in S3 (`media.proxy` leaves the doc in S4; docs/oplog.md:292–296).
  - **Alt:** add `op.redone`. It can't be told apart from an undo after `load`.
- **D10 Payload.** **Glyph A: yes, an undo event names the entry it undid, through `undoes`.**
  - **Rec, fields:** the payload is the same **diff record** as `history_diff` and the `conflict` diff: `{type, project_id, seq, op_id, group_id, actor{kind,id}, step?, summary, base_version, new_version, hash, changed_ids, undoes}`. Glyph's `version` is `new_version`.
  - **Rec, left out:** `ops`, `inverse`, `client_op_id` and `warnings`. Cards join on `op_id`.
  - **Rec, engine change:** add `hash` to the `history_diff` keep-list (oplog.py:834).
  - **Alt:** a separate event shape.
- **D11 SSE.**
  - **Rec, ids:** the SSE `id` is the log `seq`, which has no gaps by construction (oplog.py:1082). So C8's 0 gaps / 0 dupes follows directly.
  - **Rec, reconnect:** `GET /api/projects/<id>/events` with `Last-Event-ID: n` replays `seq > n` from the log, then goes live. Events are published after the durable commit, under the mutex.
  - **Rec, edge cases:** an `n` above the head gets an un-ided `stream.reset{head_seq}`; a non-integer `n` gets 400.
  - **Rec, slow clients:** a bounded queue of 1024 events per client. On overflow the client is disconnected and reconnects with `Last-Event-ID`.
  - **Alt:** a separate bus counter, which needs its own durable store.
- **D12 MCP side.** **Rec (S3+W):** a resource `timeline://<project_id>` with `resources/updated` on every entry. **Alt:** agents poll `get_hash`.

## 4. C5: a forged `step`/`actor` never takes effect, on HTTP, ACP and MCP alike (RULED, Ada 6:24 PM)

**SETTLED behaviour (Wire's findings, line numbers spot-checked):**
- `Oplog.call` strips `actor`/`step` from the args and from every op, at **oplog.py:848** (`_strip_forged`, :1318–1340; `FORGED_FIELDS`, :37). This happens **before** the retry lookup (`_replayed`, :933).
- Each stripped field gets a `{code:"ignored_field", path, message}` warning (:1328–1336).
- The write applies with the session's actor (:1086) and step (only from `Session.step()`, :97–108 and :1096–1098). See docs/oplog.md:21–31 and test 70.
- **Fingerprint:** it's computed after stripping, so keeping, dropping, adding or changing a forged field on a retry never gives `client_op_id_mismatch`:
  - the key is `(session.actor.kind, session.actor.id, client_op_id)`, at :936;
  - `_same_call` (:953) compares the stripped args.

**GAP at `c6de84e`** (Probe `evidence/s3-spec/c5_retry_probe.py`/`.out`, matching Wire's findings). Warnings are cached at commit (:1109–1110) and returned as stored (:951), and `load` rebuilds them as `[]` (:1241).

| Retry | Live at `c6de84e` | After `load` | **Approved target** |
|---|---|---|---|
| Exact retry, same forged field | cached + its warning | cached, **no warning** | cached + the warning |
| Retry drops the forged field | cached + the **original's** warning | cached, no warning | cached, no warning |
| Clean original, retry **adds** a forged field | cached, **no warning** | cached, no warning | cached + the warning for the added field |
| Any of the above | never `client_op_id_mismatch` | never | never |

**APPROVED (Ada and Prove, 6:28 PM): replay and warnings rules for the S3 build.**
1. **A retry returns the cached result, plus the `ignored_field` warnings from its own strip at :848.** Every other field is byte-identical to the cache.
2. **The entry stores only *result* warnings,** meaning warnings that describe what the write did. It never stores `ignored_field`. So an exact retry shows the warning once, and a retry that drops the field shows none. `ignored_field` is a property of the call, not of the result. The cache keeps storing result warnings only. Note: the warning set is closed at `{ignored_field}` (§5 item 2), so in S3 the stored list is **always empty**. The mechanism is there for any result-warning code Ada approves later.
   - **Stored warnings are always empty in S3**: the only warning code is `ignored_field`, and it's never stored. The mechanism stays (the line key, reload, replay order) for any result-warning code Ada approves later.
   - **Prove's C5 gate:** a retry gets **its own** strip `ignored_field` warnings (one per forged field it sent, at that field's path), **both live and after a reload** (`Oplog.load`), and nothing else (test 93).
3. **Stored result warnings survive a reload.** They're saved in the `oplog.jsonl` entry, and `load` reads them instead of rebuilding `[]` at :1241. **On replay the order is:** the stored result warnings first, then this call's strip warnings.
4. **Old lines:** an entry with no `warnings` key loads with no warnings. That isn't an error.
5. **Saving warnings changes neither the doc `hash` nor the `version`.**

**Exact on-disk shape:**
- New optional line key **`warnings`**, added to `LINE_OPTIONAL` next to `step` (oplog.py:56), so `_check_line` (:787–790) accepts it. The value is a non-empty list of `{code, path, message}` with `code != "ignored_field"`. `_check_line` rejects an empty list, `ignored_field`, or any other shape, with "not an oplog line".
- The key is **written only when that list is non-empty**, through `_canon` (sorted keys, :138). So in S3 every line stays **byte-identical** to the `c6de84e` format, and old logs load unchanged (rule 4).
- **Example (future, hypothetical code):** `{"actor":{…},…,"undoes":null,"warnings":[{"code":"<approved_code>","message":"…","path":"/ops/0/…"}]}`.
- Code changes: `_commit` passes only the result warnings to the line and the cache. `_result(entry, entry.get("warnings", []) + own_strip)` is built on every return, fresh and replay alike. `load` uses `entry.get("warnings", [])`.

**No hash chain to break (rule 5).** Checked at `c6de84e`:
- An entry's `hash` is the **doc** hash after the entry. `load` checks it by replaying the ops (`new["hash"] != e["hash"]`, :1234).
- Nothing hashes the line itself, and there's no previous-entry hash or chain. `oplog.py` has no `hashlib`, `sha256`, `prev_hash` or `chain`.
- `warnings` never enters the doc, so `canonical_hash` and `version` can't change.
- `_same_call` reads only `base_version`/`summary`/`group_id`/`ops`/target fields (:953–1002), so retry matching is unaffected too.
- **Also kept out of** the `history_diff` record and events (D10). `history_list` returns full lines, so it shows `warnings` when they're present.

**How each transport ends up with the session's actor:**

| Route | Who decides actor/step | Forged attempts |
|---|---|---|
| **HTTP** (Edit page REST) | `Authorization: Bearer <ui token>` → `Session(Actor("human", <user>))`, `plan=None` | Body `actor`/`step` are stripped at :848. Headers like `X-Actor` aren't read. No token → 401; wrong scope → `permission_denied`. The Host/Origin/Content-Type guard stays (studio.py:258–270) |
| **ACP** (Hermes) | The `acp:hermes` token minted by Electron main. `PlanContext.step` is set only by Electron main from ACP plan updates, through a control-token call | Hermes's tool args go through MCP with its token and get stripped. Hermes has no control token |
| **MCP** (HTTP and the stdio proxy) | The token's registered agent id, **never** `clientInfo`, `_meta` or args. `plan=None`, so no `step` | Stripped by the engine. /mcp passes them through and doesn't strip them itself (§1g) |
| **Store** | The line actor comes only from `Session` (:1086). **Probe:** the forged `"x"` is nowhere in the file, and the logged op has no `step` | — |
| **Lock / bus** | Only the owning engine writes (D6). Events are built from the committed entry (D10) | A forged value is never stored or published |

- **D13 Tokens.**
  - **Rec, tokens:** per-launch random 256-bit tokens held in memory, with scopes `read`/`write`/`render`.
  - **Rec, kinds:** `ui` (human), `acp:hermes`, `mcp:<name>` (the name is chosen when the token is minted) and `control` (Electron main only).
  - **Rec, human sessions:** only `ui` can make a human session.
  - **Alt:** take the agent id from MCP `clientInfo`. That's self-asserted, so it's out.
- **D14 How the stdio proxy authenticates.** `.lock` only holds a hash, so the proxy can't log in with it.
  - **Rec:** the engine writes `.attach` (mode 0600) holding the raw `mcp:stdio` token. It's replaced on every launch and deleted on a clean exit.
  - **Alt:** the proxy asks Electron over a local socket.

## 5. Wire's list

| # | Question | Answer |
|---|---|---|
| 1 | Engine errors → MCP | **Every** engine and tool error comes back as a **tool result** with `isError: true` and the `as_dict()` body `{ok:false, error, code, hint?, rule?, path?, id?, op_index?, …}` (mcp.py:484–493). That covers `invalid_op`/`not_found`/`conflict`/`undo_blocked` (oplog.py:112) plus `schema_mismatch`/`invalid_doc`/`engine_offline`/`permission_denied`/`needs_approval`.<br><br>**JSON-RPC protocol errors only for:** `-32700` parse (mcp.py:303), `-32600` for a non-object message (D15; missing today: mcp.py:437–438 drops it silently), `-32601` unknown method (:462), and `-32602` for an unknown tool name (:479), a non-object `params`, or `arguments` that's present but not an object (D15).<br><br>Unexpected exceptions become `isError` with `failed` (:486–487), never `-32603`. A missing or bad token gets HTTP 401 before JSON-RPC. The engine's `unknown_tool` can't be reached from /mcp |
| 2 | `warnings[]` | **A closed set: `{ignored_field}`** (oplog.py:1330), shaped `{code, path, message}`. Adding a code is a contract change that needs Ada's OK. `otio_tick_precision` is reserved for the PLANNED export_otio note, not in S3. Rounding is reported in `used`, not as a warning. Retry rules are in §4 (APPROVED) |
| 3 | Undo/redo with no `base_version` | **SETTLED:** the `conflict` check is skipped (`_base_version(…, required=False)`, oplog.py:919–921, :1144) and the call acts on the **current** version. The actor and dependents checks still apply (docs/oplog.md:225–235).<br><br>**Probe:** apply A, apply B, then undo A with no `base_version` → applied at v3. With `base_version:1` → `conflict`, `current_version:3`. /mcp never fills it in (D18) |
| 4 | `conflict` diff shape | **SETTLED:** `{code:"conflict", current_version, history_diff:[record…]}`. The records cover `new_version > min(base_version, current)`, oldest first (oplog.py:924–931). Record keys: `seq, op_id, group_id, actor, step?, summary, base_version, new_version, changed_ids, undoes` (:834; Probe). D10 adds `hash`; D19 adds a cap |
| 5 | `history_list` / `history_diff` | Today there's no paging (oplog.py:828–835). See D19 |
| 6 | One read with `version` + `hash` | `get_hash{project_id}` returns `{project_id, schema_version, version, hash, seq}`, read under the mutex (D3) through a new `Oplog.head()`. `get_timeline`'s raw doc also carries both (docs/timeline.md:10). Lock state is in `project_status` (D8) |
| 7 | Is `project_id` the timeline `id`? | **Yes, SETTLED** (docs/oplog.md:59–60; oplog.py:881). Typing is D4 |
| 8 | `schema_version` guard | **SETTLED (Ada 18:11, §1h).** It's /mcp-only and runs first. Anything other than `"hs.timeline/1"` gets `schema_mismatch`, `rule:"bad_schema"`, `path:"/schema_version"`, `expected`, `got`, and the engine is never called. A matching value is **stripped**; otherwise the engine says `unknown_arg` (`_check_args`, oplog.py:857). D20 decides which tools |

- **D15 Non-object message, `params` and `arguments` (Wire ask 1).** Today: a non-object message is **silently dropped** (mcp.py:437–438, `continue`, no reply); `params = msg.get("params") or {}` (:440) and `args = params.get("arguments") or {}` (:467) turn **any falsy value** (`[]`, `""`, `0`, `false`) into `{}`; and a truthy non-object `params` (e.g. `[1]`) makes `params.get` raise `AttributeError` inside the call thread, so no reply is sent.
  - **Rec, message:** a message that isn't an object (array, string, number, `null`) gets **`-32600` Invalid Request** with `id: null`. (We don't support JSON-RPC batches, so an array is a single invalid request.)
  - **Rec, `params`:** only a **missing** `params` key becomes `{}`. Anything else that isn't an object, falsy or not, gets **`-32602`**.
  - **Rec, `arguments`:** only a **missing** `arguments` key becomes `{}`. `null` and every other non-object (`[]`, `""`, `0`, `false`, `[1]`, `"x"`) get **`-32602`**, because MCP defines `arguments` as an object. (This replaces the earlier "`null` → `{}`".) The test is `"arguments" not in params`, never truthiness.
  - **Alt:** pass a non-object `arguments` to the engine, which gives `bad_arg` @ `""` (oplog.py:846). That doesn't work for per-op registry entries that build ops from the arguments.
- **D16 `structuredContent` on errors.** **Rec:** no, as today: the body goes in the last text block (mcp.py:490–493). **Alt:** add it and make `outputSchema` a `oneOf`.
- **D17 `ensure_ascii`. Must fix.** mcp.py:306 and :488, and the CLI's JSON output at cli.py:95 (`emit`) and :100 (`error`) (Wire ask 2), call `ensure_ascii=False` and then `.encode("utf-8")`. If an error message echoes a lone surrogate, `Transport.write` raises `UnicodeEncodeError` and **no reply is sent** (Probe). For the CLI, `print` raises `UnicodeEncodeError` on a strict-UTF-8 stdout the same way. studio.py:123/:249 already use the default (`True`). **Rec:** `ensure_ascii=True` on every /mcp, HTTP and CLI JSON output. **Alt:** `surrogatepass`, which emits invalid UTF-8.
- **D27 Parse robustness. Must fix (Prove 6:37 PM).** At c6de84e a single bad input line kills the stdio /mcp server (exit 1, no `-32700`): `Transport.read` (mcp.py:283–303) only catches `JSONDecodeError` on newline framing. Three repros are in `evidence/prove-s3-spec/stdio_parse_probe.out`: an integer longer than 4300 digits (`ValueError`), invalid UTF-8 (`UnicodeDecodeError`), and any bad body under `Content-Length` framing (no try at all). Wire's line refs (ask 1): the `Content-Length` path parses at mcp.py:299 with no `try`, its `int()` on the header at :293 can raise too, and the newline path's `except` at :302 catches only `JSONDecodeError`. **Rec:** one `parse_message(bytes)` used by both framings (:299 and :300–303) and by the HTTP body parser. It catches `UnicodeDecodeError`, `ValueError` (which covers `JSONDecodeError` and the int-digit limit) and `RecursionError`, and answers `-32700` with `id: null`. When a message body fails to parse, the server keeps reading. A `Content-Length` header is handled by (a)–(c) below: drained, or the session is closed. **Nothing on stdio ever resyncs by scanning bytes for a header.** HTTP /mcp answers 400 with the same JSON-RPC body; the REST routes keep their own body (d). No new rule id.
  - **Prove's evidence** (`evidence/prove-s3-spec/stdio_parse_probe.out`; I re-ran it at `c6de84e`):
    - `huge`: a >4300-digit integer → `ValueError`, exit 1.
    - `badutf8` → `UnicodeDecodeError`, exit 1.
    - `lspbad`: a bad body under `Content-Length` → `JSONDecodeError`, exit 1.
    - `neg`: `Content-Length: -1` → mcp.py:298 calls `self.inp.read(-1)`, which reads **to EOF**. With stdin closed the probe gets a reply (exit 0); on a live pipe it **blocks forever**. My re-run with the pipe held open got no reply and was killed by `timeout` (exit 124).
    - `short`: `Content-Length: 2` with the body `{}{"jsonrpc":"2.0","id":7,"method":"ping"}` → the `{}` is dropped, and the **leftover bytes are parsed as a newline-framed message and run** (reply for `id: 7`). My re-run: same.
    - Also, `int()` at :293 accepts `+5`, ` 5 ` and `1_0`, and on `abc` it raises and crashes the server (exit 1).
  - **(a) The `Content-Length` value (Prove; match per Wire, cap and limits per Ada).**
    - **Match:** take the header line and remove exactly one line terminator (`\r\n` or `\n`). Take the text after the first colon and strip only the ASCII spaces and tabs around it (`strip(b" \t")`, not the `.strip()` that :293 uses today). The value must pass **`re.fullmatch(rb"[0-9]+", value)`**. That's fully anchored, like D26's `\A…\Z`, so a trailing `\n`, `\r`, `\v` or `\f` is rejected; a `$`-anchored `re.match` would let a trailing `\n` through.
    - **Digit count before `int()` (Ada):** a digit run **longer than 8 digits** is a broken stream (case 2 below), and `int()` is never called on it. The rule counts **digits, not value**, so `000000007` (9 digits) closes the session too. Up to 8 digits, `n = int(value)`, which can't raise. This replaces the old 4300-significant-digit rule.
    - **Cap (Ada, 7:05 PM):** `MAX_BODY = 1024 * 1024` = 1,048,576, **inclusive**: the single existing constant at `studio.py:38`, shared by stdio /mcp, HTTP /mcp and the REST JSON routes. The transport **imports it, with no second copy of the number**. The drain limit is written as `16 * MAX_BODY`, not as a literal.
    - **Three cases:**
      1. **`n ≤ MAX_BODY`:** read exactly `n` bytes and parse them as a message. A body that doesn't parse gets `-32700` with `id: null`, and the session goes on (framing is still in step).
      2. **`MAX_BODY < n ≤ 16 * MAX_BODY` (16,777,216, inclusive). RULED (Ada, 7:09 PM):** see (b).
      3. **Broken stream. RULED (Ada, 7:09 PM):** `n > 16 * MAX_BODY`, or a digit run longer than 8 digits. stdio sends `-32700` with `id: null`, logs one line to stderr (`mcp: broken Content-Length framing: <reason>; closing session`), and **closes the session with a nonzero exit**. The client reconnects. There's no skip-ahead.
    - **Malformed header. Prove's proposal, ruled by Ada at 7:12 PM:** the header fails the match. That covers `-1`, `+5`, `1_000`, `abc`, empty or whitespace-only, non-ASCII digits (`٣`), and a stray control character. It's handled **the same as case 3**: `-32700` with `id: null`, a stderr line, and a close with a nonzero exit. `read` is never called with the value.
    - **Duplicate headers. Prove's proposal, ruled by Ada at 7:19 PM:** **two or more `Content-Length` headers in one header block, even with the same value,** are malformed on both transports. On stdio: `-32700` with `id: null`, a stderr line, and a close with a nonzero exit. On HTTP: see (d). Today stdio parses only the **first** `Content-Length` line and skips the rest of the header block (mcp.py:291–297). HTTP's `headers.get` also returns the first one, so today the first wins silently on both.
    - **Known limit:** a `validate_timeline` document over 1 MiB is refused. Raising the cap means changing that one constant (studio.py:38), and that decision goes back to Ada. `MAX_IMAGE_BODY` (32 MiB, :39) is for design uploads and isn't reused.
  - **(b) Over the cap, up to 16 × MAX_BODY: answer, then drain. RULED (Ada, 7:09 PM).**
    - stdio **first writes and flushes `-32700`** with `id: null`. The body is never parsed.
    - Then it **reads and discards exactly N bytes** in chunks of ≤ 64 KiB, **without keeping or scanning them**. A `Content-Length:` line or a JSON-RPC call inside the body never starts a call.
    - After N bytes, framing is back in step, and the next header is read normally.
    - **Why:** once the error has gone out, a stalled drain (a client that announced N bytes and sends fewer) is no worse than stdio's normal wait for the next message.
  - **(c) Sticky framing; no resync anywhere.**
    - **Once a stream has used `Content-Length` framing, it stays in that mode.** Whatever follows a body is read as the next header block.
    - **A too-short length:** the leftover bytes are read as the next header. If they don't parse as a valid header, that's a malformed header: `-32700`, `id: null`, a nonzero exit. Prove's `short` probe (`Content-Length: 2`, body `{}{"jsonrpc":…,"id":7,…}`): `{}` gets `-32600` (D15), then the leftover `{"jsonrpc"…` fails as a header and the session closes. `id: 7` never runs.
    - **Known limit of framing (Wire, 7:11 PM):** if the leftover bytes happen to form a valid frame (`Content-Length: N`, a blank line, then a call), no server can tell them apart from a real client message, and that call runs. Wire confirmed with mcp.py's reader at `c6de84e` that `Content-Length: 2` + `{}` followed by a valid frame is byte-for-byte the same as two real messages. So the spec claims "an embedded call never runs" **only** for the malformed-header and over-cap cases, whose bytes are never parsed.
    - Newline framing (no `Content-Length` seen yet) is unchanged: one JSON message per line, and a bad line gets `-32700` while the session goes on.
    - **[R] Newline-mode line cap (O1, RULED Ada 8:58 PM).** In newline mode the reader takes **at most `MAX_BODY + 1` bytes per line**. A longer line gets `-32700` with `id: null`, a stderr line and a nonzero exit, and is **never parsed** (test 102(b2)). Before (`0282e9f`, Prove O1): `mcp.py:331` used an unbounded `readline()`, so a 3 MiB newline-framed message was read whole and answered.
    - **[R] No blank-line skip (RULED Ada 8:29/8:32 PM).** Remove the blank-line skip (`mcp.py:319–320` at `0282e9f`). In `Content-Length` mode, anything between frames that isn't a valid header, **a blank line included**, gets `-32700` with `id: null`, a stderr line and a nonzero exit. No skip-ahead anywhere (test 102(a)).
  - **(d) HTTP twin: same header check, close on refusal. RULED (Ada approved Wire's point 1, 7:09 PM; header check and message, Ada 7:18 PM).**
    - **Today (`c6de84e`):**
      - `_read_json` does `int(handler.headers.get("Content-Length") or 0)` (studio.py:149). That accepts `+5`, ` 5 ` and `1_000`. A `ValueError` is read as `0` (studio.py:150–151), so the body is left unread and the request goes on with `{}`. That covers `abc`, more than 4300 digits (`int()`'s limit), and a Unicode digit such as `٣`: the header arrives as Latin-1, so `٣` becomes `'Ù£'` and `int()` raises (checked here). A str `'٣'` itself would give `int()` 3.
      - A negative value or one over the cap raises `ValueError("request body too large")` without reading the body (studio.py:152–153). `do_POST` answers 400 (studio.py:446–447) through `_json` (studio.py:122–129), which sends no `Connection: close`.
      - With two `Content-Length` headers, the first one wins.
      - `protocol_version = "HTTP/1.1"` (studio.py:236) keeps the stdlib keep-alive loop running, so an unread body is parsed as the next request.
      - **Wire's repro, re-run here** (`evidence/s3-spec/http_oversize_smuggle_probe.py`/`.out`): a 1,048,577-byte `POST /api/design` whose body starts with `GET /api/doctor HTTP/1.1` gets **400, then 200 from `/api/doctor`, then 414** for the padding.
    - **S3, the header check: the same as stdio.** The value, with surrounding spaces and tabs stripped, must pass **`re.fullmatch(rb"[0-9]+", value)`** and the **8-digit rule** (a run longer than 8 digits fails, and is counted by digits, not value). `int()` is never called on a value that fails either check.
    - **Failing either check gets `400 {"ok": false, "error": "invalid content length"}` plus a close (RULED, Ada 7:18 PM).** That's a new message string, **not a rule id**, so the counts stay 17/36.
    - **`-1` (ruled by Ada at 7:19 PM):** `-1` fails the header check before any size check runs, so it gets `invalid content length` plus a close. `request body too large` is only for lengths that are well-formed and over the cap.
    - **Duplicate `Content-Length` headers (ruled by Ada at 7:19 PM):** two or more, even with the same value, get `invalid content length` plus a close. **Implementation (Prove's note):** read the header with `handler.headers.get_all("Content-Length")` and refuse anything other than exactly one value; `headers.get` returns only the first header, so a duplicate would slip through.
    - **Over the cap** (passes the checks, `n > MAX_BODY`): keeps today's **`400 {"ok": false, "error": "request body too large"}`**, now with a close.
    - **`Transfer-Encoding` (RULED, Ada 7:25 PM):** a request with **any** `Transfer-Encoding` header, with or without `Content-Length`, gets **`400 {"ok": false, "error": "unsupported transfer encoding"}`** plus a close on REST, and `-32700` (`id: null`) plus a close on HTTP /mcp. The body is never read. That's a new message string, **not a rule id**, so the counts stay at 17/36. **Order (Prove):** check `Transfer-Encoding` **first**, before any `Content-Length` check, so a request with both `Transfer-Encoding` and a bad or duplicate `Content-Length` always gets `unsupported transfer encoding`. **Before (`c6de84e`):** `evidence/s3-spec/http_chunked_smuggle_probe.py`/`.out`. A chunked `POST /api/design` with no `Content-Length` whose body is `GET /api/doctor` gets **200, then 200**: the body is left on the connection and runs as a second request. `http.server` doesn't decode chunked bodies. The Edit page never sends chunked (Glyph checked): `fetch()` with a string body sets `Content-Length`.
    - **Missing `Content-Length`** (and no `Transfer-Encoding`): unchanged; it's read as `0`, as today (studio.py:149, `or 0`). Per HTTP/1.1, such a request has no body.
    - **Close on every refusal:** the server keeps the 400 status, **sends `Connection: close` and sets `self.close_connection = True`**, the same pattern `_refuse` already uses (studio.py:248–256). The leftover body is never parsed as a second request: **one response per connection**.
    - **[R] Every method, before routing (F2, RULED Ada 8:58 PM; GET body rule Ada 9:02 PM).** The checks run on **every** HTTP method, before routing, in this order:
      1. Any `Transfer-Encoding` → 400 `{"ok": false, "error": "unsupported transfer encoding"}`.
      2. `Content-Length` must be exactly one valid value, read with `get_all`, using the same strip, fullmatch and 8-digit rule as stdio. An invalid value, `-1` or a duplicate → 400 `{"ok": false, "error": "invalid content length"}`.
      3. A **GET** with a valid length above 0, **even one over the cap**, → 400 `{"ok": false, "error": "request body not allowed"}`. The body is never read.
      4. Over the cap (only a POST gets this far) → 400 `{"ok": false, "error": "request body too large"}`.
      - On HTTP /mcp each of these refusals is `-32700` with `id: null` instead of the REST body. Every refusal sends `Connection: close`.
      - A GET with no `Content-Length` or `Content-Length: 0` is unchanged.
      - Before (`0282e9f`, Prove F2): GET never called `body_length`, so `GET /api/doctor` with a `Content-Length` body holding an embedded `GET /api/doctor` got 200, then 200; the same with `Content-Length: abc`; a chunked GET got 200 and a close. Tests 103(vi-a/b/c), including `Content-Length: 2000000` on a GET.
  - **(e) HTTP bodies (Ada approved Wire's point 3).**
    - **REST routes:** `400 {"ok": false, "error": "invalid content length"}` when the header fails a check, and `400 {"ok": false, "error": "request body too large"}` when it's over the cap. Both close the connection.
    - **Only HTTP /mcp** answers a refusal or an unparseable body with the JSON-RPC `-32700` body (`id: null`), also with status 400 and `Connection: close`.
  - **Crash-probe tests:** 101 and 102 for stdio, and 103 for HTTP (§7). All three are in Prove's D27 crash-probe gate, alongside `huge`, `badutf8` and `lspbad`.
- **D18 /mcp fills nothing in.** **Rec:** /mcp never adds or changes `base_version`, `client_op_id`, `summary`, `group_id`, `project_id`, or any op key. For example, a `base_version` filled from the current version would make every retry a mismatch. **Alt:** none that's retry-safe.
- **D19 Paging (Wire asks 3 and 8).**
  - **Today:** no arg checks. **Probe:** `history_list("5")` and `(None)` raise `TypeError` once there's an entry; `-1` returns everything; `True` and `1.5` are accepted (`True` acts as 1); `99` gives `[]`. Same for `history_diff` (oplog.py:828–835).
  - **Rec, tools:**
    - `history_list{project_id, since_version?=0, limit?=50}` → `{entries, next_since_version, head_version}`.
    - `history_diff{project_id, since_version, limit?=200}` → `{records, next_since_version, head_version}`.
    - `since_version` is **required** for `history_diff` (missing → `missing_arg` @ `/since_version`, from the engine's own `_check_args`).
  - **Rec, types and bounds (checked in the engine read methods, so HTTP and /mcp get the same answer):**
    - `since_version`: an **int, not a bool, ≥ 0**, with **no upper bound**. Above the head → an **empty page**, `next_since_version: null`, not an error.
    - `limit`: an **int, not a bool**, `1–200` for `history_list`, `1–500` for `history_diff`.
    - Anything else gives `invalid_op` `bad_arg` @ `/since_version` or `/limit`, no `id`. That covers `"5"`, `null`, `-1`, `true`, `1.5`, `0` for `limit` and values above the cap. An unknown arg gives `unknown_arg` @ `/<arg>` (same `_check_args`).
    - Check order: `_check_args` (unknown, then missing) → `since_version` → `limit`.
  - **Rec, order and cursor:** oldest first. `next_since_version` is the `new_version` of the last returned item when more exist, otherwise `null`. `head_version` is the current version.
  - **Rec, raw ticks (Test 50, APPROVED Ada 6:40 PM):** `history_list` returns the **raw log lines**, with ticks exactly as stored (`ops`, `inverse`). That's the same exemption as `get_timeline`, so it's exempt from the `{ticks, seconds}` output rule. `history_diff` records carry no time fields.
  - **Rec, conflict diff:** at most 200 records (the oldest 200 after `base_version`). The `conflict` body is `{…, current_version, history_diff:[…], history_diff_truncated: <bool>}`. **`history_diff_truncated` is always present** (`false` when not cut) and sits at the **top level, next to `history_diff`**. To fetch the rest, the client calls `history_diff{since_version: <new_version of the last record>}` and pages from there.
  - **Alt:** unbounded results, or `history_diff_truncated` only when true (absent ≠ false is easy to misread).

## 6. /mcp rules (Ada §1g/§1h, settled) and how they're wired

| Rule | Spec | Source |
|---|---|---|
| Pre-checks | /mcp checks a field before the engine **only when** its check gives the engine's own answer (rule, path, whether `id` is present, order). Everything else goes to the engine as received. Declared types aren't enforced | contract §1g |
| /mcp-only fields | Use engine rule ids and JSON Pointer paths. **`invalid_args` is gone**. The named §1h exemptions are exactly: the `schema_version` guard; `_s` conversion failures; the both-sent check (D23); a missing `project_id` (D4); `trim_clip{dur_s}` on a clip (D30, path only); and batch order (D31). Nothing else is checked by /mcp alone | §1g, §1h (approved) |
| Batch order (RULED, Ada 6:47 PM; §1h) | /mcp checks and converts the **whole batch** before calling the engine; per op: check view → both-sent → conversion; the first failure is returned as is | D31 |
| Time inputs (APPROVED, Ada 6:40 PM) | **/mcp accepts time in seconds through `_s` args, and raw tick args pass through to the engine** (the contract rule now reads this way) | D23 |
| `_s` conversion | `seconds_to_ticks_nearest(x)` (timeline.py:160), run once. It returns `(ticks, Fraction)`; /mcp sends only `[0]`, a Python `int` (test 91 checks `type is int`). A `TypeError`/`ValueError` gives `invalid_op` `bad_arg` @ `/ops/k/<arg>_s` (nested: `/ops/k/anchor/offset_s`), with `op_index`, no `id` and no engine call. Negatives, `1e308` and `-0.0` reach the engine | §1h(a) |
| Re-pointing | If the engine answers `too_large`/`negative_time` with `op_index == k` and a path ending at the **converted field**, the path becomes `/ops/k/<arg>_s`; `code/rule/id/op_index/problems` are kept. Every other answer passes through verbatim | §1h. **Probe:** a 2nd marker at −1 gives `/markers/2/at`, `op_index:1`, `id:mk2` |
| Passthrough | Labels, `summary`, `props`, `text` and `style` are forwarded byte for byte: no NFC, no int↔float conversion. Key order doesn't matter (`_canon` sorts, oplog.py:138) | contract §1e; docs/oplog.md:249–290 |

- **D20 Tools that accept `schema_version`.** **Rec:** every tool, read and write. **Alt:** write tools only.
- **D21 /mcp order. APPROVED (Ada 6:40 PM), with Prove's ordering rule.** When an `_s` value fails to convert, /mcp runs the engine's own op-arg check (reused, not copied) with a placeholder int in place of the bad value; `unknown_arg`/`missing_arg` comes back unchanged; only otherwise `bad_arg` @ the `_s` path. No caveat, no §1h exemption for this case.
  - **Which engine function (Wire's correction, 6:46 PM; checked):** not `Oplog._check_args` (oplog.py:857–866). That one checks the **outer** `timeline_apply` args: on an op view it would flag `op` itself as unknown, use `/<arg>` paths, and raise `KeyError` reading `args["client_op_id"]` (:862). The per-op name check is **inline in `_apply_one`** (oplog.py:763–771: not-an-object/no `op` → `bad_arg`, unknown op → `unknown_op`, then `unknown_arg` sorted with `key=repr`, then `missing_arg`). `_run` adds the `/ops/k` prefix and `op_index` (oplog.py:1010–1024, the `except _OpError` block).
  - **S3 engine refactor (named):** pull that block into one shared helper, **`check_op_args(op: dict, k: int, *, internal: bool = False) -> OplogError | None`**. It returns the same `invalid_op` error `_run` builds today (rule, `op_index` k, path `/ops/k/<arg>` with `_key_parts` for non-string keys), or `None`. `_apply_one`/`_run` call it in place of the inline code (raising what it returns), and /mcp calls it on the check view. Same function, identical paths. Names only: it never looks at values, so the placeholder `0` can't trip it (oplog.py:768–771; Wire confirmed).
  - **Helper steps, in order:** (1) not an object / no string `op` → `bad_arg` @ `/ops/k`; (2) `unknown_op` @ `/ops/k/op`; (3) `unknown_arg` @ `/ops/k/<key>` (sorted `key=repr`); (4) `missing_arg` @ `/ops/k/<key>` (sorted); (5) **new, the only behaviour change (D29 RULED):** the anchor-key check. Steps 1–4 are a **pure refactor**: byte-identical answers.
  - **Prove's ordering rule (written down exactly):** for each op, /mcp first builds a **check view**:
    1. Drop every `<arg>_s` key.
    2. For each dropped key, add `<arg>` with placeholder int `0` **only if the caller did not already send `<arg>`**. Never overwrite a raw value.
    3. Run `check_op_args(view, k)` on that view **first**. If it errors, return that error unchanged (with `op_index` k, path `/ops/k/…`).
    4. **Only then** run the both-sent check: `<arg>` and `<arg>_s` both present → `bad_arg` @ `/ops/k/<arg>_s`.
    5. **Then** the `_s` conversions: a `TypeError`/`ValueError` → `bad_arg` @ the `_s` path.
    - Example: `{op:"move_clip", id:"c1", at:0, at_s:1, bogus:1}` → `unknown_arg` @ `/ops/0/bogus` (not the both-sent `bad_arg`).
    - **Nested `anchor.offset_s`:** the same steps inside `anchor`: drop `offset_s`, add `offset: 0` only if `offset` is absent, then both-sent (`bad_arg` @ `/ops/k/anchor/offset_s`), then conversion. `anchor`'s keys are checked **by name** in `check_op_args` step 5 (D29): an unknown key is `unknown_arg` and a missing `to`/`offset` is `missing_arg`, both @ `/ops/k/anchor/<key>`. That check runs on the check view, so it sees `offset: 0` in place of `offset_s` and never fires because of `offset_s` (Wire fix 5).
    - **Same path for success and failure:** the view check runs whether the conversions succeed or not, so the D21 path and the normal path give the same answer for the same arg names.
  - **Full /mcp order:** (1) JSON-RPC parse and shape, auth (D15, D27); (2) the `schema_version` guard; (3) `project_id` present (D4); (3b) the engine's own top-level `timeline_apply` envelope check (oplog.py:1115–1119, e.g. `summary`), extracted into a shared helper and reused, not copied, so `{summary:"", at_s:"x"}` gives `bad_arg` @ `/summary` on /mcp and HTTP alike.
    - **APPROVED (Ada ruling 3, 6:56 PM):** it's the same principle as D21 (reuse the engine's own check), so there's no new exemption. The alternative is removed.
    - The envelope check is exactly oplog.py:1115–1119, in this order: `_check_args`, then `group_id: null`, then `_base_version_type`, then `_ops_shape`.
    - Dedupe (`client_op_id_mismatch`) and `base_version`/`conflict` stay **after** the op stage (test 99). Test 100 pins this order;
    (4) per op, in op order: the check view → both-sent → `_s` conversion; (5) the engine, with the converted ops; (6) re-pointing (D22).
  - **Known /mcp-vs-engine differences: RULED by Ada (6:47 PM).** D29 is fixed; D30 and D31 are named §1h exemptions. The raw-passthrough idea I floated at 6:46 is withdrawn: under ruling D31, conversion errors are reported before anything reaches the engine.
- **D29 Keys inside `anchor`. RULED (Ada 6:47 PM): FIXED, not exempt. Shape APPROVED (Ada ruling 2, 6:56 PM).** The shared helper also checks `anchor`'s keys by name, so the engine and /mcp give that answer first.
  - **What the engine gives today at `c6de84e`** (Probe `evidence/s3-spec/anchor_keys_probe.py`/`.out`, for `set_anchor`, `add_text` and `insert_clip`): no name check exists. `_check_refs` only refuses a non-string `anchor.to` (`bad_arg` @ `/ops/k/anchor/to`, no `id`; oplog.py:294–296). Everything else is a **validator** answer after the op has built the item: `invalid_op` with a **doc path** and the item `id`, plus `problems`:
    - `{to, offset, zz}` → `unknown_field` @ `T/anchor/zz`, `id` = the item (`x1` target; `x2`/`c4` engine-picked new ids), `problems:[unknown_field]`;
    - `{offset}` → `missing_field` @ `T/anchor/to`; `{to}` → `missing_field` @ `T/anchor/offset`; `{}` → `missing_field` @ `T/anchor/offset`, `problems:[…/offset, …/to]`; `{offset, zz}` → `unknown_field` @ `T/anchor/zz`, `problems:[…/zz, …/to]`;
    - `5` or a list → `not_object` @ `T/anchor`.
  - **Why the shape changes:** today's path `T/…` is the item's position after the op runs, and for create ops today's `id` is the engine-picked new id. Neither exists at the name stage.
  - **APPROVED as specced (Ada ruling 2, 6:56 PM):** the answer below, with no `id`, checked before the same op's `not_found`. Glyph finds the op through `op_index` (and the `/ops/k/…` path), not an item `id`.
  - **The shape (APPROVED):** op-arg rules at op paths, the same way the helper reports top-level keys. Step 5 runs only when the op is public, takes `anchor` (`insert_clip`, `add_text`, `set_anchor`) and `anchor` is a **dict** (`null` for `set_anchor` and non-objects are untouched, so they keep today's answers):
    - (5a) any key other than `to`/`offset` → **`unknown_arg` @ `/ops/k/anchor/<key>`** (sorted `key=repr`; non-string keys via `_key_parts`);
    - (5b) then a missing `offset` or `to` (sorted: `offset` first) → **`missing_arg` @ `/ops/k/anchor/<key>`**;
    - `invalid_op`, `op_index` k, **no `id`, no `problems`**. These are existing oplog rules, so there's no new rule id.
    - On /mcp the check view drops `anchor.offset_s` and adds `offset: 0` only when `offset` is absent (D21), so (5b) never fires because of `offset_s`. Over HTTP, an `anchor.offset_s` key is `unknown_arg` @ `/ops/k/anchor/offset_s`, like a top-level `at_s`.
  - **Exact anchor delta for Prove's whitelist** (every other input stays byte-identical): an input changes **only if** some op k is public, is `insert_clip`/`add_text`/`set_anchor`, has a dict `anchor`, passes steps 1–4, and that dict has a key outside `{to, offset}` or lacks `to` or `offset`. For those inputs:
    - **before:** `invalid_op`, rule `unknown_field`/`missing_field` @ `T/anchor/<key>`, `id` = the item, `problems` = the validator list (or an earlier same-op answer, see below);
    - **after:** `invalid_op`, rule `unknown_arg`/`missing_arg` @ `/ops/k/anchor/<key>`, `op_index` k, no `id`, no `problems`.
    - **Order delta in the same op:** the anchor-key answer now comes **before** that op's `_check_refs`, lookups, value checks and the validator. Probe, before → after: `set_anchor{id:"zz", anchor:{offset:0}}`: `not_found` @ `/ops/0/id` → `missing_arg` @ `/ops/0/anchor/to`; `set_anchor{id:"x1", anchor:{to:5}}`: `bad_arg` @ `/ops/0/anchor/to` → `missing_arg` @ `/ops/0/anchor/offset`.
    - Ops before k, and the outer stages (tool args, shape, dedupe, `base_version`), are unchanged and still come first.
    - **`load`/`replay`/undo** run with `internal=True` and skip step 5. Logged anchors already passed validation, so replay is unaffected either way.
- **D30 `trim_clip{dur_s}` on a clip. RULED (Ada 6:47 PM): a named §1h exemption.** /mcp gives the conversion error (`bad_arg` @ `/ops/k/dur_s`) for a bad `dur_s`. Over HTTP, any `dur` on a clip is `bad_arg` @ `/ops/k/id` (oplog.py:480–483, after the lookup; Probe). Only the path differs. A **valid** `dur_s` on a clip still reaches the engine and gets `bad_arg` @ `/ops/k/id`, the same as HTTP.
- **D31 Batch order. RULED (Ada 6:47 PM): exempt; written into §1h.** /mcp runs the per-op pre-engine steps (check view → both-sent → conversion) for **every op in the batch, in op order**, and returns the **first** error **before anything reaches the engine**. So a bad `_s` in op k+1 is reported ahead of an engine-stage error in op k (e.g. `not_found`). **Of the engine's outer stages, D31 claims to beat only two:** dedupe (`client_op_id_mismatch` on a cached key) and `base_version`/`conflict`. It makes **no** claim over an outer `unknown_arg`/`missing_arg` or a shape error: the engine's envelope check (oplog.py:1115–1119) runs **first**, on /mcp as on HTTP (D21 step 3b, Ada ruling 3; Wire fix 4). Only when the whole batch passes do the converted ops go to the engine. **§1h wording:** "/mcp runs the engine's own envelope check, then checks and converts the whole batch before calling the engine. For each op in order: the check view, then both-sent, then the `_s` conversions. The first failure is returned as is; the engine sees only fully converted batches."
- **D22 Re-pointing table (Wire ask 4).** The table lives in the registry, one row per `_s` arg, and is tested against §1h's per-op table. A rewrite happens only when **all** of these hold: `rule` is `too_large` or `negative_time`; `op_index == k`; the path is one of that arg's landing paths below. **`T/…` and `/markers/<j>/…` only match when the error's `id` is the op's own target (its `id` arg) or the item/marker that op k created** (an `id` that wasn't in the doc /mcp read under the D3 mutex before the call). An error on any other item, such as an anchored item moved by `move_clip`, stays verbatim.

  | Op | `_s` arg | Engine field | Landing paths that are re-pointed | Not re-pointed (verbatim) |
  |---|---|---|---|---|
  | `add_marker` | `at_s` | `at` | `/ops/k/at`; `/markers/<j>/at` (new marker) | — |
  | `move_clip` | `at_s` | `at` | `/ops/k/at`; `T/at` (target) | `out_of_range` @ `T`; errors on anchored items |
  | `split_clip` | `at_s` | `at` | `/ops/k/at` | `bad_arg` @ `/ops/k/at` (not strictly inside); `non_integer_duration` |
  | `trim_clip` | `src_in_s` | `src_in` | `/ops/k/src_in` | `too_large` @ `T/at` (a different field, §1h) |
  | `trim_clip` | `src_out_s` | `src_out` | `/ops/k/src_out`; `T/src/1` | `empty_range`, `src_out_of_media` |
  | `trim_clip` | `dur_s` (text only) | `dur` | `/ops/k/dur`; `T/dur` | on a clip: `bad_arg` @ `/ops/k/id` |
  | `set_fade` | `fade_in_s`, `fade_out_s` | `fade_in`, `fade_out` | `/ops/k/<field>`; `T/<field>` | `fade_too_long` @ `T` |
  | `set_anchor` | `at_s` (with `anchor: null`) | `at` | `/ops/k/at`; `T/at` | `anchor_before_zero` |
  | `set_anchor` | `anchor.offset_s` | `anchor.offset` | `/ops/k/anchor/offset`; `T/anchor/offset` (`too_large` only; it's signed, so never `negative_time`) | `anchor_before_zero` @ `T/anchor` |
  | `insert_clip` | `at_s` | `at` | `/ops/k/at`; `T/at` (new clip) | `overlap`, `out_of_range` @ `T` |
  | `insert_clip` | `src_s` (a 2-element list `[in_s, out_s]`, each converted) | `src[0]`, `src[1]` | `T/src/0` → `/ops/k/src_s/0`; `T/src/1` → `/ops/k/src_s/1` | `out_of_range` @ `T/src`; `empty_range`; `non_integer_duration` |
  | `insert_clip` | `fade_in_s`, `fade_out_s` | `fade_in`, `fade_out` | `T/<field>` (new clip) | `fade_too_long` |
  | `insert_clip` | `anchor.offset_s` | `anchor.offset` | `T/anchor/offset` (`too_large` only) | `anchor_before_zero` |
  | `add_text` | `at_s`, `dur_s`, `fade_in_s`, `fade_out_s` | same names | `/ops/k/at`; `T/<field>` (new text item) | `fade_too_long`; `empty_range` on `dur` |
  | `add_text` | `anchor.offset_s` | `anchor.offset` | `T/anchor/offset` (`too_large` only) | `anchor_before_zero` |
  | `add_transition` | `dur_s` | `dur` | `T/dur` (new transition) | `transition_overlap_mismatch` |

  - A rewritten error keeps `code`, `rule`, `id`, `op_index` and `problems`; only `path` changes (e.g. `/ops/k/src_s/1`, `/ops/k/anchor/offset_s`).
  - **`src_s` element errors:** a non-list or wrong-length `src_s` isn't a conversion; it's passed to the engine as `src` unconverted, so the engine answers. An element that fails conversion → `bad_arg` @ `/ops/k/src_s/<i>`.
  - **Alt:** hard-code it in the handler.
- **D23 Raw tick field at /mcp. APPROVED (Ada 6:40 PM).** Raw tick fields pass through /mcp to the engine (HTTP takes ticks too). Sending both `<arg>` and `<arg>_s` (including `anchor.offset` + `anchor.offset_s`) gives `bad_arg` @ `/ops/k/<arg>_s`. That's the **only** /mcp-only check on op args, and it's a **named §1h exemption**. It runs after the check view and before conversion (D21). Contract rule: "/mcp accepts time in seconds through `_s` args, and raw tick args pass through to the engine."
- **D24 Arg parsing.** **Rec:** /mcp handlers get the raw parsed JSON `dict`, with no SDK/pydantic coercion. If we use the `mcp` SDK, register the tools with free-form `dict` inputs. **Alt:** typed models, which break byte-for-byte passthrough.
- **D25 REST status codes.** **Rec:** the body is the same as /mcp's, with `invalid_op`/`schema_mismatch` 400, `not_found` 404, `conflict`/`undo_blocked` 409, `invalid_doc` 422, no token 401, `permission_denied` 403, Host 421 (studio.py:261), **`engine_offline` 503** (with `Retry-After` omitted: it won't come back until the app opens), **`needs_approval` 202** (S8; the write is parked, not refused), `failed` (D28 corrupt log, unexpected errors) 500 (Wire ask 5). **Alt:** always 200 + `ok:false`.
- **D26 HTTP read routes (Glyph, 6:32 PM).** **Rec:** these four GET routes call the same engine reads as the /mcp tools, under the D3 mutex, and return **byte-identical bodies** with D25 status codes and the same auth as the Edit page REST (§4, Bearer ui token):
  - `GET /api/projects/<id>/status` → `project_status` (D8).
  - `GET /api/projects/<id>/hash` → `get_hash` `{project_id, schema_version, version, hash, seq}`.
  - `GET /api/projects/<id>/history?since_version=&limit=` → `history_list` (D19 defaults and bounds).
  - `GET /api/projects/<id>/history/diff?since_version=&limit=` → `history_diff` (D19).
  - `<id>` is the `project_id` (Wire 7). Query values arrive as strings. HTTP turns a value matching the ASCII-only regex `\A(0|[1-9][0-9]*)\Z` into an int (no `str.isdigit`, so Unicode digits, signs, `-1`, `007`, spaces and empty strings stay raw strings) and passes anything else as the raw string, so the **engine** gives `bad_arg` @ `/since_version` or `/limit`, the same as /mcp. Unknown query params are ignored with no warning (`ignored_field` stays a body-only warning).
  - **Huge digit strings (Wire ask 6):** a value matching the regex but longer than `sys.get_int_max_str_digits()` (4300) makes `int()` raise `ValueError` (Probe). HTTP catches it and passes the **raw string** through, so the engine gives `bad_arg`; never a 500. Up to 4300 digits it becomes an int: `since_version` then gives an empty page (no upper bound) and `limit` gives `bad_arg` (over the cap).
  - **Repeated param:** not an HTTP-only check. HTTP passes the **list** of the raw strings (each one regex-converted the same way) to the engine as the value, and the engine's own type check gives `bad_arg` @ `/since_version` or `/limit`. Note that /mcp has no equivalent: `json.loads` keeps the **last** duplicate JSON key silently (Probe: `{"a":1,"a":2}` → `{"a":2}`), and that stays as is.
  - **Parity rule:** an HTTP query string `"5"` is the same as /mcp `5` (a JSON int). A /mcp JSON string `"5"` is `bad_arg`, a value HTTP can't send. Everything else is identical because the engine does the checking.
  - The events route (D11) stays as written. **Alt:** one `GET /api/projects/<id>` that bundles status and hash, which Glyph didn't ask for.
  - **[R] Path decoding (RULED Ada 8:58 PM; Glyph fix 1).** Split the path on `/` first, then percent-decode each segment once, the same way on GET and POST. So `p%2F1` is the id `p/1` (`not_found`), never a split path. The D26 route test adds this decode case.

## 7. Prove's gates and Wire's tests → where the spec settles them

| Gate / test | Settled by | Status |
|---|---|---|
| **C5(a)**: lands with the session's actor/step, no trace in the history entry | §4 (:848, :1086, :1096); transport table; D13 | engine PASS (Probe) |
| **C5(b)**: `ignored_field` names the path | :1328–1336 (`/actor`, `/ops/k/step`) | PASS |
| **Test 70**: (a) + (b) | same | PASS at `c6de84e` |
| **C5(c) / Test 93**: retry keeps/drops/adds/changes a forged field, live and after reload | Fingerprint after stripping (:848 → :936/:953); **APPROVED rules 1–5** in §4 | **fails at `c6de84e`** on drop, add and reload (Probe); green after the S3 change |
| **Test 94**: C5 over HTTP, ACP and MCP | §4 transport table; D13, D14; one `Oplog.call` path for all three | S3+W |
| Exact /mcp retry never gives `client_op_id_mismatch` | D18, D24, §6 passthrough, `_canon` | design |
| **Test 91**: float `_s` retry returns the cache; ticks are whole ints | The helper is pure and returns an **int**. **Probe:** `0.1+0.2` and `0.3` both → 211680000, every time; `1/3` → 235200000, every time. /mcp puts that int straight into the op, and a test asserts `type is int`, since `235200000.0` would be a mismatch (docs/oplog.md:284–290) | design + test |
| **Test 92**: NFD retry gets `not_nfc` every time; a refused call doesn't reserve the key | Passthrough; the key is stored only in `_commit` (:1110). **Probe:** NFD `edit_text` with key `k` → `not_nfc` @ `/ops/0/text` twice, then NFC with `k` → applied, seq 1 | PASS |
| `_s` bool / `"1.5"` | `TypeError` → `bad_arg` @ the `_s` path, no engine call | settled §1h |
| `_s` NaN / ±Inf / `1e400` | `ValueError` → the same `bad_arg` | settled |
| `_s` `1e308` | engine `too_large`, re-pointed, `id` kept (D22) | settled |
| `_s` `-0.0` | tick 0, applied; `used = {ticks:0, seconds:0}` | settled |
| `_s` negatives | engine `negative_time`, re-pointed. `anchor.offset_s` is signed and applies | settled |
| §1g `{id:5,bogus:1}` / `{id:5}` / `{id:"zz",text:5}` | engine answers: `unknown_arg` @ `/ops/0/bogus`; `bad_arg` @ `/ops/0/id` with no `id`; `not_found` @ `/ops/0/id` with `id:"zz"` | settled (contract §1f) |
| **Prove's ordering rule**: `{at, at_s, bogus}` → `unknown_arg` @ `/ops/k/bogus`; then both-sent; then conversion; same for `anchor.offset_s`; same path on success and failure | D21 (APPROVED), using the extracted `check_op_args` (oplog.py:761–772) | S3+W |
| Both `at` and `at_s` | D23 (APPROVED): `bad_arg` @ `/ops/k/at_s` | S3+W |
| **Test 95** (`at_s` ordering: check view, then both-sent, then conversion) | D21 (APPROVED), `check_op_args` | S3+W |
| **Test 96** (`anchor.offset_s` ordering, nested) | D21 nested rule; D29 for keys inside `anchor` | S3+W |
| **Test 97** (anchor keys by name, D29) | D29 (APPROVED shape): `unknown_arg`/`missing_arg` @ `/ops/k/anchor/<key>`, no `id`, before the same op's `not_found`/`bad_arg`; identical over HTTP and /mcp | **unpinned; runs** at the S3 head |
| **Test 98** (`trim_clip{dur_s}` on a clip) | D30 (named §1h exemption) | S3+W |
| **Test 99** (batch order) | D31 (named §1h exemption) | S3+W |
| **Test 100** (envelope before the /mcp op stage) | D21 step 3b (APPROVED, Ada ruling 3) | S2+S3+W |
| **Test 101 (D27 boundaries):** stdio `Content-Length` `1048576`, `1048577`, `16777216`, `16777217`, a 9-digit length (`100000000`) and `000000007` (9 digits); an 8-digit length handled by value (`00000007` with a 7-byte body); and **duplicate headers** (`Content-Length: 5` twice, and `5` + `7`; RULED) | **Pinned:** `1048576` is **accepted** and answered normally. `1048577` and `16777216` get `-32700` with `id: null` **before the drain finishes** (the test reads the error before sending any body byte), then exactly N bytes are drained (no read over 64 KiB, nothing kept), and the next frame is answered. `16777217`, `100000000` and `000000007` get `-32700` with `id: null` and a stderr line, then the process **exits nonzero**; `int()` is never called on a 9-digit run, because the rule counts digits, not value. `00000007` is read as 7. Both duplicate-header cases get `-32700` with `id: null`, a stderr line and a nonzero exit, and no body is read (RULED (Ada 7:19 PM)) | S3+W; Prove's D27 crash-probe gate |
| **Test 102 (embedded frames; three parts)** | **(a) Malformed lengths close the session (RULED):** `-1`, `+5`, `1_000`, `abc`, empty, whitespace-only, `٣` (UTF-8 bytes), `5` + a stray `\r`/`\v`, two conflicting headers (`5` + `7`), and the same value twice (`5` twice, Ada 7:19 PM/Prove), each followed by a body holding a full `Content-Length` + `tools/call` frame: `-32700` with `id: null`, a nonzero exit, and **the embedded call never runs**. **(b) Over-cap lengths never run an embedded frame:** `Content-Length: 2097152` whose body holds a full `Content-Length: 40` + `tools/call` frame (`id: 9`), padded to 2,097,152 bytes, then a valid frame `id: 10`: `-32700` first, **no reply for `id: 9` and its handler never runs**, `id: 10` answered. Plus Wire's case, **`Content-Length: 16777217`** (over the drain limit) whose body starts with the same embedded `id: 9` frame: `-32700` with `id: null`, a stderr line, a nonzero exit, and `id: 9` never runs. **(c) Too-short lengths:** asserts **only** that leftover bytes which don't parse as a header close the session (`-32700`, `id: null`, nonzero exit). Prove's `short` case gives `-32600` for `{}`, then the close, and `id: 7` never runs. Not asserted: leftovers that form a valid frame run, a known limit of framing (D27(c)) | S3+W; Prove's D27 crash-probe gate |
| **Test 103 (new, HTTP close-on-refusal):** Wire's `/api/doctor` repro (a 1,048,577-byte POST whose body starts with `GET /api/doctor HTTP/1.1`), and the same embedded GET after `Content-Length` values `abc`, `+5`, `1_000`, `٣`, a 9-digit value (`100000000`), `-1`, and duplicate headers (`5` twice; `5` + `7`), each on a REST route and on HTTP /mcp. Plus the embedded GET sent **chunked** (`Transfer-Encoding: chunked`, with no `Content-Length`, and also with a bad or duplicate `Content-Length`). Plus a POST with **no** `Content-Length` | **Before (`c6de84e`):** the over-cap repro gets 400, then 200 from `/api/doctor`, then 414. `+5`/`1_000` are read as numbers; `abc`, `٣` (arrives as Latin-1 `'Ù£'`) and over 4300 digits are read as 0, with the body unread. Duplicates: the first wins. HTTP /mcp: 404 for every case (no route at `c6de84e`). Chunked: **200, then 200** (`/api/doctor` answered; `http_chunked_smuggle_probe.out`). **After:** **one response per connection**, with `Connection: close` and the socket closed; `/api/doctor` is never answered. **REST:** over cap → exactly one `400 {"ok": false, "error": "request body too large"}`. `abc`, `+5`, `1_000`, `٣`, the 9-digit value → exactly one `400 {"ok": false, "error": "invalid content length"}`, with `int()` never called. `-1` and duplicates → `invalid content length` (RULED (Ada 7:19 PM)). Any `Transfer-Encoding` → exactly one `400 {"ok": false, "error": "unsupported transfer encoding"}`, also when a bad or duplicate `Content-Length` is present, because `Transfer-Encoding` is checked first (RULED, Ada 7:25 PM). **HTTP /mcp:** exactly one 400 with `-32700` (`id: null`) in every case. Missing `Content-Length` with no `Transfer-Encoding` → unchanged (read as 0) | S3+W; Prove's D27 crash-probe gate |
| **Prove's D27 crash-probe gate** | `huge`, `badutf8`, `lspbad` (Prove's probe) + tests 101–103. The stdio server never crashes. A bad message body gets exactly one `-32700`/`-32600` and the session goes on. **Closing the session with a nonzero exit, after `-32700` with `id: null`, is the expected answer for a broken stream** (over 16 × MAX_BODY, more than 8 digits, or a malformed header, RULED). **The only wait allowed is draining bytes still owed after the error went out.** An embedded frame never runs after a malformed header or inside an over-cap body. HTTP sends one response per refused connection | S3+W |
| Known differences (anchor keys, `trim_clip dur_s` on a clip, batch/stage order) | **RULED:** D29 fixed (shape APPROVED, Ada ruling 2); D30, D31 exempt | — |
| **Prove's regression gate** (widened by Ada, 6:49 PM): at the S3 head every engine answer is **byte-identical** to `c6de84e` for the same input (`code`, `rule`, `path`, `id`, `op_index`, order of `problems`), checked by replaying the S2/S2b fuzz corpora and regression scripts on both commits and diffing. **Any replay diff outside §11's allowed list is a FAIL** | §11 (the twelve allowed diffs); `check_op_args` steps 1–4 are a pure refactor | S3 gate |
| **Tests 88 / 89 / 90** | §6, D15, D19, D20, D21 (incl. step 3b), D22, D23, D24, D29, D30, D31 | S3+W |
| **Test 50** (`{ticks, seconds}` everywhere) | `get_timeline` **and `history_list`** are raw-tick exemptions (APPROVED, D19) | S3+W |
| **Test 58** (app closed: reads work, writes refused, no write opens) | D28(a) read-only path; `engine_offline` | S3 |
| **Tests 61 / 62** (corrupt store) | D28(b): faults moved into `base.json`; new 61(c) cache-only fault (reads succeed); new 61(d) for both app states: corrupt middle line → `failed` + `seq`; torn tail truncated with the app open, skipped in memory with it closed (file unchanged); missing final `\n` repaired with the app open (D2) | S3+W, re-targeted |
| Test 89: missing `project_id` | D4: `missing_arg` @ `/project_id` | S3+W |
| Transport robustness | D15 (`-32600`/`-32602`), D17 (mcp.py + cli.py), D27 | S3+W |
| C3 / C4 | D1, D2, D28 | S3 |
| C7 | D5, D6, D14, D28(a) (read-only closed-app path) | S3 |
| C8 | D9, D11 | S3 |
| C9 | D8 adds `project_status` to the allowlist (APPROVED, Ada 7:18 PM; test 60) | S3+W |

## 8. Retries at /mcp: labels, summaries, props

**SETTLED** by canonical same-call (docs/oplog.md:249–290; oplog.py:953–967): "equal" means byte-identical canonical JSON. /mcp forwards every passthrough field untouched, converts each `_s` to the **same int** every time, and fills nothing in (D18). So an exact retry produces the same engine call and gets the cache. Any real change (a label, NFD vs NFC, `1` vs `1.0`) is `client_op_id_mismatch` @ `/client_op_id`, with `op_ids:[cached]`.

## 9. New rule ids

**None.** S3 uses only existing rules (`bad_arg`, `not_found`, `unknown_arg`, `missing_arg`, `bad_schema`, `too_large`, `negative_time`, `not_nfc`, `client_op_id_mismatch`) and error codes already in Wire's table (`schema_mismatch`, `engine_offline`, `permission_denied`).
- The lock refusal is a startup error with no rule (D6).
- `locked` (the D7 Alt) is not recommended.
- C5 stays strip + `ignored_field` (Ada 6:24 PM), with no hard-reject rule.
- `warnings` in the line is a line key, not a rule.
- A corrupt log line uses the existing generic code `failed`, with no rule (D28). The alternative rule `bad_oplog_line` would be **new** and needs Ada; I don't recommend it.
- The /mcp-only checks (schema guard, `_s` conversion, both-sent, missing `project_id`) reuse `bad_schema`, `bad_arg` and `missing_arg`.
- D29's anchor-key check reuses `unknown_arg`/`missing_arg` (existing oplog rules); D30/D31 are exemptions with no rule.

- **[R]** `"request body not allowed"` (Ada 9:02 PM), like `"invalid content length"` and `"unsupported transfer encoding"`, is a message string, not a rule id.

Counts stay at **17 oplog / 36 validator**.

## 10. Decisions: 31 numbered, 19 open, 12 approved/ruled

**[R]** The states below are the 7:18 PM record. Ada approved all 31 decisions at 7:33 PM ET (PR #42 body); the 8:58–9:02 PM rulings that refine D26, D27 and D28 are folded into §6, §11 and §13 and noted in the rows.

| # | Decision | Rec | State |
|---|---|---|---|
| D1 | Source of truth | the log + `base.json`; json and snapshots are caches | open |
| D2 | Commit order and torn line | fsync line → replace json → snapshot → event; the open engine truncates only a torn final line, and writes a missing final `\n` before the next append; the closed read never writes | open (revised) |
| D3 | Concurrency | per-project mutex around call, persist, publish and head reads | open |
| D4 | `project_id` typing | `bad_arg` @ `/project_id` for non-string; **missing at /mcp → `missing_arg` @ `/project_id`** | **RULED** (Ada 7:18 PM) |
| D5 | Lock mechanism | OS lock; JSON pid/port/started_at/version/token hash; stale = the lock can be taken | open |
| D6 | Second engine | startup error `failed` naming pid/port/since; no rule | open |
| D7 | Actor edit lease (Glyph B) | none in S3; serialised writes + `conflict` | open |
| D8 | Lock-state read | new tool `project_status`; on the C9 tool allowlist (test 60) | **RULED** (Ada 7:18 PM) |
| D9 | Event types | `op.applied`/`op.undone` per new entry; nothing on a cached retry | open |
| D10 | Event payload | the diff record (+`hash`); `undoes` names the undone entries | open |
| D11 | SSE | id = log `seq`; replay from the log; `stream.reset`; bounded queue | open |
| D12 | MCP notifications | `timeline://<id>` `resources/updated` | open |
| D13 | Tokens/sessions | per-launch scoped tokens; only `ui` is human; never `clientInfo` | open |
| D14 | stdio proxy auth | 0600 `.attach` token | open |
| D15 | Non-object message / `params` / `arguments` | message → `-32600`; `params`/`arguments` present but not an object (incl. `null`, `[]`, `""`, `0`, `false`) → `-32602`; only a missing key → `{}` | open (revised) |
| D16 | `structuredContent` on errors | no | open |
| D17 | `ensure_ascii` | `True` on mcp.py:306/:488 **and cli.py:95/:100** (must fix) | **RULED** (Ada 7:18 PM) |
| D18 | /mcp fills nothing in | never fills `base_version`/`client_op_id`/`summary`/`group_id` | open |
| D19 | History paging | int (not bool) ≥ 0 `since_version`, no upper bound, empty page above head; `limit` 1–200/1–500; engine `bad_arg`; `history_list` raw ticks (test 50 approved); `history_diff_truncated` always present, top level | **RULED** (Ada 7:18 PM) |
| D20 | `schema_version` accepted on | every tool | open |
| D21 | /mcp order for `_s` | envelope check reused (oplog.py:1115–1119, step 3b) → check view (placeholder 0, never overwrite) → shared `check_op_args(op, k)` (pulled out of `_apply_one` oplog.py:763–771) → both-sent → conversion | **APPROVED** (Ada 6:40 PM + Prove's rule; step 3b Ada ruling 3, 6:56 PM) |
| D22 | Re-pointing table | full table in the registry; `T/` matches only the op's target or new item | open (revised) |
| D23 | Raw tick field at /mcp | passes through; both sent → `bad_arg` @ `/ops/k/<arg>_s` (named §1h exemption) | **APPROVED** (Ada 6:40 PM) |
| D24 | Arg parsing | raw dicts, no SDK coercion | open |
| D25 | REST status | 400/404/409/422/401/403/421, **503 `engine_offline`, 202 `needs_approval`**, 500 `failed`; same body | **RULED** (Ada 7:18 PM) |
| D26 | HTTP read routes | four GETs; ASCII digit regex; >4300 digits and repeated params pass raw to the engine; parity HTTP `"5"` = /mcp `5`; **[R]** split the path, then decode each segment (Ada 8:58 PM) | open (revised) |
| D27 | Parse robustness | one `parse_message` for :299, :300–303 and HTTP; a bad body gets `-32700` and the session goes on; `Content-Length`: `re.fullmatch(rb"[0-9]+")`, more than 8 digits → close; ≤ `MAX_BODY` read; up to `16 * MAX_BODY` → `-32700` then drain N unscanned (RULED); above that → `-32700` + stderr + nonzero exit (RULED); malformed header → the same close (RULED); duplicate headers malformed on both transports (RULED (Ada 7:19 PM)); HTTP: the same header check, `invalid content length` (RULED), `-1` → that message (RULED (Ada 7:19 PM)); no resync; HTTP refusals close the connection (RULED), REST keeps its body, HTTP /mcp gets `-32700` (RULED) (tests 101–103) (must fix); **[R]** every method, before routing: TE → one valid CL → GET body > 0 → cap (POST only), GET → `request body not allowed` (Ada 8:58/9:02 PM); newline-mode cap `MAX_BODY + 1` (O1); no blank-line skip in CL mode | **RULED** (Ada 7:18 PM) |
| D28 | Read source and corrupt store | open app: memory; closed app: read-only, parses every log line first (torn tail skipped in memory, never truncated), `timeline.json` only if it validates and matches the log head, else replay; bad `base.json` → `schema_mismatch`/`invalid_doc`; bad log line → `failed` + `seq`; bad cache → ignored; **[R]** a `base.json` with no `hash` → `invalid_doc` `hash_mismatch` (O2); every line checked as `Oplog.load` does, `inverse` included (F1) | **RULED** (Ada 7:18 PM) |
| D29 | Keys inside `anchor` | shared helper step 5: `unknown_arg`/`missing_arg` @ `/ops/k/anchor/<key>`, no `id`, before the same op's `not_found`; Glyph uses `op_index`; §11 row 1 | **RULED: fixed; shape APPROVED** (Ada 6:47 PM; ruling 2, 6:56 PM) |
| D30 | `trim_clip{dur_s}` on a clip | conversion error `bad_arg` @ `/ops/k/dur_s`; HTTP `bad_arg` @ `/ops/k/id` | **RULED: §1h exemption** |
| D31 | Batch order | /mcp checks + converts the whole batch before the engine; first failure wins | **RULED: §1h exemption** |

**APPROVED/RULED, not open:** the C5 replay and warnings rules (§4, rules 1–5, with the on-disk shape); D21 and D23 (Ada 6:40 PM); test 50's raw-tick exemption for `history_list` (Ada 6:40 PM); D29, D30, D31 (Ada 6:47 PM); D29's shape, D21 step 3b and the twelve §11 diffs (Ada rulings 1–3, 6:56 PM); D4, D8, D17, D19, D25, D27, D28 (Ada 7:18 PM).

**Ada's yes on Wire's five items (7:18 PM):**
1. stdio stays in `Content-Length` mode once it has used it (D27(c); Ada's 7:14 ruling).
2. Batch order per op: check view → both-sent → conversion → the engine (D21, D30, D31).
3. `failed` is the existing error code, not a rule. Closed-app reads get it for a corrupt log line (D28), and HTTP returns it as **500** (D25).
4. D19 paging: `history_list` `limit` 1–200, `history_diff` `limit` 1–500, and `history_diff_truncated` always present at the top level.
5. D8 `project_status` is approved and goes on the C9 tool allowlist for test 60.

Also accepted by Ada as a known gap: §12 finding 8 (a tampered middle-line `hash` with the app closed; Wire tests it with the app open).

**Engine changes for the S3 build:**
- D2 (store), D3 (mutex), D4 (`project_id` typing)
- D10 (`hash` in `history_diff`), D19 (paging and arg checks), `Oplog.head()`
- D21/D29: the shared helper `check_op_args(op, k) -> OplogError | None`, pulled out of `_apply_one` (oplog.py:763–771) and used by `_run` and /mcp; steps 1–4 a pure refactor, step 5 the anchor-key check
- D28: validate `base.json` before `Oplog`; map `load` errors to `failed`
- §4 rules 1–5 (`LINE_OPTIONAL += "warnings"`; `_commit`, `_result`, `_replayed` and `load` :1241)

All of them are small, and none adds a rule.

## 11. Allowed replay diffs vs `c6de84e` (Ada 6:49 PM; widened by Ada ruling 1, 6:56 PM)

**These twelve are the only allowed diffs. Any other replay diff is a FAIL** under Prove's byte-identical gate (§7). Rows 1–4 were approved at 6:49 PM; rows A–H come from Ada's ruling 1. Wire's review items are already covered: D19 is in A, B and D; D10 in C; D2's torn tail in F.

"Before" is the behaviour at `c6de84e`, and "after" is S3. Anything a row doesn't name (other fields, other inputs, the order of `problems`) must stay byte-identical.

| # | Diff | Before (`c6de84e`) | After (S3) | Source |
|---|---|---|---|---|
| 1 | **Anchor keys checked by name** | A public `insert_clip`/`add_text`/`set_anchor` that passes steps 1–4, with a dict `anchor` that has a key outside `{to, offset}` or lacks `to`/`offset`, gets `invalid_op` `unknown_field`/`missing_field` @ `T/anchor/<key>`, with `id` = the item (an engine-picked id for create ops) and `problems` = the validator's list. Or an earlier same-op answer wins: `not_found` @ `/ops/k/id`, `bad_arg` @ `/ops/k/anchor/to`, or a value error | `invalid_op` **`unknown_arg`** @ `/ops/k/anchor/<key>` (unknown keys first, sorted `key=repr`), else **`missing_arg`** @ `/ops/k/anchor/<key>` (`offset` before `to`). `op_index` k, **no `id`, no `problems`**. Comes **before** the same op's `_check_refs`, lookup (`not_found`), value checks and validator. Unchanged: non-dict anchors, `anchor: null`, ops before k, the outer stages, and `internal=True` runs (`load`, `replay`, undo) | D29 (approved); test 97; `anchor_keys_probe.out` |
| 2 | **C5 replay warnings** | A cached retry returns the stored result as is, `warnings` included. Live, that's the **original** call's `ignored_field` list, even when this retry sent none or different ones; after `Oplog.load` it's `[]` (oplog.py:951, :1109–1110, :1241) | `warnings` = the stored result warnings (**always `[]` in S3**), then **this call's own** `ignored_field` strip warnings (the oplog.py:848 order: args first, then each op), **live and after a reload**. Every other field is byte-identical. The `warnings` line key is written only when non-empty, so no S3 line changes; doc `hash`/`version` unchanged | §4 rules 1–5; test 93 |
| 3 | **D4: non-string `project_id`** | `project_id` = `5` / `null` / `true` / `[]` → `not_found` @ `/project_id`, with `id` = `"5"` / `"None"` / `"True"` / `"[]"` (`str()`, oplog.py:887) | `invalid_op` **`bad_arg`** @ `/project_id`, **no `id`**, at the same point in `_check_args`. A string that isn't this doc's id is still `not_found` with that `id` | D4 |
| 4 | **D17 + D27: parses input differently** (and escapes output to ASCII) | **stdio /mcp:** invalid UTF-8, a >4300-digit integer, a bad JSON body under `Content-Length`, or a non-integer `Content-Length` → uncaught exception, **the server exits 1** with no reply. `Content-Length: -1` → `read(-1)`, which **hangs** on a live pipe. A short length → the leftover bytes **run as a newline-framed call**. Output uses `ensure_ascii=False` (mcp.py:306, :488; cli.py:95, :100), so a lone surrogate in a reply raises and **no reply** is sent (Prove's `stdio_parse_probe.out` and my re-runs). **HTTP:** `int(headers.get("Content-Length") or 0)` (studio.py:149) accepts `+5`, ` 5 ` and `1_000`. Anything that raises (`abc`, `٣` as Latin-1, over 4300 digits) is read as 0 (studio.py:150–151), with the body unread. Over cap or negative → 400 `request body too large` (studio.py:152–153). The first of two headers wins. A refused or unread body stays on the keep-alive connection (studio.py:236) and is parsed as the next request: Wire's repro gets **400, then 200 (`/api/doctor`), then 414** (`http_oversize_smuggle_probe.out`). A chunked POST (`Transfer-Encoding: chunked`, no `Content-Length`) whose body is `GET /api/doctor` gets **200, then 200** (`http_chunked_smuggle_probe.out`). HTTP /mcp → 404 (no route at `c6de84e`). **[R] GET and newline cap (probed at `0282e9f`, Prove F2/O1):** a GET whose `Content-Length` body holds `GET /api/doctor` got **200, then 200** on `/api/doctor` (the same with `Content-Length: abc`); a chunked GET got 200 and a close. A 3 MiB newline-framed line was read whole and answered | **stdio:** a bad message body gets **`-32700`** (`id: null`) and the session goes on. `Content-Length` must pass `re.fullmatch(rb"[0-9]+")`. Up to `MAX_BODY` (1,048,576, inclusive, studio.py:38) it's read. Up to `16 * MAX_BODY` (16,777,216) the server sends **`-32700` first, then drains exactly N bytes** unscanned. Above that, or for more than 8 digits (`000000007` included), it sends **`-32700`, logs to stderr, and exits nonzero**. A malformed header gets the same close (RULED). No resync ever; framing stays sticky. **HTTP:** the same header check as stdio (`re.fullmatch(rb"[0-9]+")` + the 8-digit rule; `int()` is never called on a failing value). Every refusal keeps 400 but sends `Connection: close` and closes, so there's **one response per connection**. **REST:** a failed check → `{"ok": false, "error": "invalid content length"}` (RULED; `-1` and duplicates RULED (Ada 7:19 PM)); over cap → `{"ok": false, "error": "request body too large"}`. **Any `Transfer-Encoding`** (checked before `Content-Length`, also with a bad or duplicate length) → REST `{"ok": false, "error": "unsupported transfer encoding"}` plus a close, body never read (RULED, Ada 7:25 PM). **HTTP /mcp:** `-32700` (`id: null`) plus a close for every refusal. A missing header with no `Transfer-Encoding` is still read as 0. Output is written with `ensure_ascii=True`: non-ASCII becomes `\uXXXX`, and the decoded JSON values are unchanged. **[R] Every method, before routing (Ada 8:58/9:02 PM):** (1) any `Transfer-Encoding` → `unsupported transfer encoding`; (2) exactly one valid `Content-Length` (`get_all`, the stdio rule) else `invalid content length`; (3) a **GET** with a valid length above 0, even over the cap → **400 `{"ok": false, "error": "request body not allowed"}`**, body never read; (4) over the cap (POST only) → `request body too large`. HTTP /mcp gets `-32700` `id: null` for each; every refusal sends `Connection: close`. A GET with no length or length 0 is unchanged. **[R] Newline cap (O1):** at most `MAX_BODY + 1` bytes per line; a longer line → `-32700` `id: null`, stderr, nonzero exit, never parsed. **[R]** In `Content-Length` mode a blank line between frames is a malformed header (no skip) | D17, D27; tests 101–103 (102(b2), 103(v), 103(vi)) |
| A | **History arg checks** | `Oplog.history_list(since_version=0)` and `history_diff(since_version)` (oplog.py:828–835) check nothing. `"5"` and `None` raise **`TypeError`** once the log has an entry (`[]` on an empty log); `-1` returns every entry; `True` acts as `1`; `1.5` compares as a float; an extra argument is a Python `TypeError` | The engine read methods check, in this order: `unknown_arg` @ `/<arg>`; `history_diff` with no `since_version` → `missing_arg` @ `/since_version`; `since_version` not an int, a bool, or < 0 → `invalid_op` `bad_arg` @ `/since_version`; `limit` not an int, a bool, or outside 1–200 (`history_list`) / 1–500 (`history_diff`) → `bad_arg` @ `/limit`. No `id`. A `since_version` above the head is **not** an error | D19 (Wire's D19 item) |
| B | **History return shape** | A bare list of every matching entry (full lines) or record, oldest first | `{entries: [...], next_since_version, head_version}` and `{records: [...], next_since_version, head_version}`. At most `limit` items (default 50 / 200), oldest first. `next_since_version` = the last item's `new_version` when more exist, else `null`. `head_version` = the current version. Above the head: `[]` and `null`. The items are byte-identical to today's (an entry carries `warnings` only when non-empty, which never happens in S3) | D19 (Wire's D19 item) |
| C | **`hash` in `history_diff` records** | Record keys (oplog.py:834): `seq, op_id, group_id, actor, step?, summary, base_version, new_version, changed_ids, undoes` | The same keys **plus `hash`** (that entry's doc hash), in every `history_diff` record **and** in every `conflict` body's `history_diff`. The other values are unchanged | D10 (Wire's D10 item) |
| D | **Conflict cap + `history_diff_truncated`** | `conflict` = `{ok:false, error, code:"conflict", hint, current_version, history_diff}`, where `history_diff` holds **every** record with `new_version > min(base_version, current)` (oplog.py:924–931) | The same body, but `history_diff` holds only the **oldest 200** of those records, and **`history_diff_truncated`** sits at the top level next to `history_diff`, **always present**: `true` when records were cut, else `false`. `error`, `hint` and `current_version` are unchanged | D19 (Wire's D19 item) |
| E | **Corrupt `base.json`** | `Oplog(base)` calls `stamp_hash` (oplog.py:801). A stale or missing stored `hash` is **accepted and re-stamped**. Any other validator fault raises `TimelineError` (`bad_input`, with `.rule`/`.path`/`.problems`), e.g. `bad_schema` @ `/schema_version` | The store runs `validate()` on `base.json` first. A bad or missing `schema_version` → **`schema_mismatch`** `rule:"bad_schema"` `path:"/schema_version"`, with `expected` and `got`. A stale `hash`, **or no `hash` key at all ([R] O2, RULED Ada 8:59 PM)**, → **`invalid_doc`** `hash_mismatch` @ `/hash`, no `id`, whether the app is open or closed. Any other fault → `invalid_doc` with `rule`/`path`/`id?`/`problems` verbatim from `validate()`. Only a file that is unreadable or not JSON → `failed` (as in F). No hash is ever returned, and every read and write tool gets the same body | D28; tests 61/62 (re-targeted) |
| F | **Corrupt log line and torn tail** | `Oplog.load` raises a bare exception: `JSONDecodeError` for any non-JSON line, **including a torn last line** (:1228); `ValueError` "not an oplog line" (:789), "oplog line N: out of sequence" (:1232), or "oplog line N: replay does not reproduce the entry" (:1235) | **Torn tail** (the **last** line, no trailing `\n`, not valid JSON): the open engine truncates the file to the end of the previous line and loads (logged once). A closed-app read skips that line in memory, uses the last complete line as the head, and never writes. **Missing final newline** (the last line is valid JSON with no `\n`). Before: `load` accepts it, the next `_commit` appends right after it (oplog.py:1101–1102), the records merge, and the next `load` raises `JSONDecodeError` "Extra data" (`newline_merge_probe.out`). After: the open engine writes the missing `\n` (fsynced) before the next append, so the file holds two well-formed lines and reloads cleanly. The closed-app read parses it as a normal line and never writes. **Corrupt middle line:** the same `failed` body whether the app is closed (it parses every line first) or open. **[R] F1 (RULED Ada 8:58 PM):** `_replay_from` and `doc_at_head` check every line exactly as `Oplog.load` does, **`inverse` included**, and the code never falls back to the last line's seq. A 5-line log whose seq 2 `inverse` was edited (hash and version intact) gets `failed` with **`seq: 2`**, open or closed (test 61(d)). Before (`0282e9f`): open → `seq: 5`; closed → the doc was served. **Any other bad line:** `isError`, `{ok:false, code:"failed", error:"oplog line <n>: <reason>", seq:<n>, hint:"The project log is damaged; restore the project folder from a backup."}`, where `n` is the line's `seq`, or its 1-based line number if it doesn't parse. No `rule`, no hash. Writes get the same body | D28, D2 (Wire's D2 item) |
| G | **Missing `project_id` at /mcp** | There are no /mcp timeline tools (mcp.py has only the clipper tools). The engine accepts a call with no `project_id` (it's optional, docs/oplog.md:59) | /mcp returns `invalid_op` **`missing_arg`** @ `/project_id` (no `id`), before any other tool-level check. The engine and HTTP are unchanged (HTTP takes it from the URL) | D4 |
| H | **D15 protocol answers** | A non-object message is **silently dropped** (mcp.py:437–438). A falsy `params` → `{}` (:440); a truthy non-object `params` → `AttributeError` in the call thread, **no reply**. `arguments` that's `null`/`[]`/`""`/`0`/`false` → `{}` (:467); a truthy non-object goes to the tool | A non-object message (array, string, number, `null`) → **`-32600`**, `id: null`. `params` present but not an object → **`-32602`**, with the request's `id`. `arguments` present but not an object (**`null` included**) → **`-32602`**. Only a **missing** `params`/`arguments` key becomes `{}`. A message object with no `method` (e.g. `{}`) → `-32600` | D15 |

**No replay diff (new surface or internal only), for the record:** `check_op_args` steps 1–4 (pure refactor); `Oplog.head()`; the D3 mutex; the store, lock, bus and SSE (D1, D2 commit order, D5–D12); tokens (D13, D14); the HTTP routes and status codes (D25, D26); the `project_status` tool (D8); and the /mcp-only §1h rules (D20–D24, D30, D31), since /mcp doesn't exist at `c6de84e`.

## 12. Findings that differ from Wire's review (§1i) or from the rulings' wording

1. **The helper.** Wire's 6:46 correction is right, and I'd found the same: `_check_args` (:857) is outer-args only, and the op check is inline at :763–771. That's now the named `check_op_args` refactor (D21).
2. **D29 shape.** A check on names alone can't keep today's anchor answer. The new shape (`/ops/k/anchor/<key>`, no `id`, op found by `op_index`) is approved (Ada ruling 2) and is row 1 of §11.
3. **Prove's byte-identical gate.** §11 now lists all twelve allowed diffs (rows 1–4 + A–H, Ada ruling 1), each with its exact before and after. Any other diff fails.
4. **D15 is stricter than my first draft and than "`null` → `{}`".** Wire's ask says only a missing key becomes `{}`, so `arguments: null` is now `-32602` too. A truthy non-object `params` (e.g. `[1]`) is a fourth case Wire didn't list: today it raises `AttributeError` in the call thread and no reply is sent.
5. **Base-hash check.** `Oplog.__init__` re-stamps the base hash (`stamp_hash`, oplog.py:801), so a stale-hash `base.json` loads silently today (Probe). Test 61(b) only works if the store calls `validate()` first (D28).
6. **Test 61/62 targets.** I agree it's a blocker. The faults move into `base.json`; a fault only in `timeline.json` becomes a success case (61(c)), not an error.
7. Everything else in §1i is confirmed against `c6de84e`: mcp.py:293/:299/:302/:437–438/:440/:467/:306/:488, cli.py:95/:100, the `history_list`/`history_diff` behaviours, and the >4300-digit `int()` limit.
8. **61(d) and a tampered middle `hash`: ACCEPTED by Ada as a known gap (7:18 PM).** **[R] Note:** F1 (8:58 PM) requires `doc_at_head` to check every line as `Oplog.load` does, which in effect needs a full replay on closed reads and would close this gap too. No recovered ruling text says the gap is closed, so it stays recorded here as accepted. A middle line whose stored `hash` was edited, but that is valid JSON with a valid shape, is caught only by replay. The closed-app fast path checks only the head's `hash` against `timeline.json`, so the closed app may serve that doc. Wire tests this case with the app open (where `load` replays and gives `failed`).
9. **Missing final newline is a live bug at `c6de84e`** (Wire fix 3, confirmed): `load` accepts the file, and the next append merges two records into one line, which bricks the next load (`evidence/s3-spec/newline_merge_probe.out`). It's fixed in D2 and listed in §11 row F.
10. **D27 framing (Ada's 7:09 PM rulings).** Drain-then-continue is ruled up to `16 * MAX_BODY`; above that, and for more than 8 digits, the server closes. Prove's malformed-header close was ruled by Ada at 7:12 PM. Wire's correction stands: a too-short length whose leftovers form a valid frame can't be detected by any server, so test 102(c) asserts only the close on leftovers that aren't a header.
11. **HTTP keep-alive smuggling is live at `c6de84e`.** I re-ran Wire's repro and got 400 → 200 → 414. **RULED (Ada 7:18 PM):** HTTP uses stdio's header check, and a value that fails it gets `400 {"ok": false, "error": "invalid content length"}` plus a close. That's a new message string, not a rule id. Over cap keeps `request body too large`. Today's `int()` at studio.py:149 accepts `+5`, ` 5 ` and `1_000`. `٣` reaches `int()` as Latin-1 `'Ù£'`, so it's read as 0 like `abc`, rather than as 3. Still RULED (Ada 7:19 PM): `-1` → `invalid content length` (Bay), and duplicate headers → malformed on both transports (Prove). **Second route, same hole (Prove, 7:22 PM):** a chunked POST with no `Content-Length` gets 200 → 200 at `c6de84e` (`evidence/s3-spec/http_chunked_smuggle_probe.out`). **RULED (Ada 7:25 PM):** any `Transfer-Encoding` gets `400 unsupported transfer encoding` (`-32700` on HTTP /mcp) plus a close, checked before `Content-Length`. Counts stay at 17/36.

## 13. As built (Ada, 8:29 PM)

This records what PR #42 does where §1–§12 left room, as Ada ruled at 8:29 PM (the addendum dates the approval 8:28). It is exact so Prove can test it. Everything here is new surface or store behaviour, so §11 is unchanged: the engine's allowed replay diffs are still rows 1–4 and A–H. Code references are to `feat/editor-s3-store-mcp`.

### 13.1 Projects: creation, opening, replay

- **Creation.** `project.create_project(base)` is **test-only**: no tool, route or CLI command creates a project in S3.
  - It validates `base`, then writes `<root>/<id>/` with `snapshots/`, `exports/`, `cache/`, `base.json` (stamped) and an empty `oplog.jsonl`.
  - `<root>` is `Path.home()/.hermes/clips/projects`.
- **Startup.** `studio.serve` → `http_engine.start(port)` → `Engine.open_all()` opens **every** folder under `<root>` whose name is a valid id (`T.ID_RE`, not `.`/`..`) and that holds a `base.json`, in sorted order.
  - A project already locked by another engine raises `failed` with `LOCKED_HINT` (D6). That aborts startup.
  - A project whose files are damaged still opens and holds its lock. Every tool on it then returns the stored error body (§11 rows E/F).
- **Lazy open.** A project folder created after startup is opened on **first use** by any engine route (REST GET/POST, HTTP /mcp, an attached stdio call): `Engine.get(id)` → `Engine.open(id)`. An id with no folder or no `base.json` gets the engine's own `not_found` (`rule: not_found`, `path: /project_id`, `id`).
- **Replay on open.** `Engine.open` takes the lock, repairs the tail (D2: truncates a torn final line, or adds a missing final `\n` with an fsync), then runs `Oplog.load(base, oplog.jsonl)`. That is a **full replay from `base.json`**. **Replaying from the nearest snapshot is deferred**: snapshots are written (every 50 versions) but not read on open.
  - After loading, `timeline.json` is rewritten if its bytes differ from the loaded doc.
- **Closed-app reads** (stdio with no engine holding the project) use D28(a). They take `timeline.json` when it validates and its `hash`/`version` equal the log head. Otherwise they replay from the newest valid snapshot on the log, else from `base.json`. They never write anything.
  - **[R] F1 (Ada 8:58 PM):** whatever source a closed read uses, every log line it replays is checked exactly as `Oplog.load` checks it, `inverse` included, so a tampered middle line gives the same `failed` `seq` body open or closed (§11 row F). The fast path above predates that ruling.

### 13.2 Tokens

- **Kinds and sessions.**
  - `ui` → `Session(Actor("human", "user"))`, no plan. The human id is the literal string `"user"`.
  - `acp:hermes` → `Session(Actor("agent", "hermes"), PlanContext())`. `PlanContext.step` starts as `null`.
  - `mcp:<name>` → `Session(Actor("agent", "<name>"))`, no plan, so lines carry no `step`.
  - `control` → **no session**.
- **No `PlanContext.step` API.** S3 has no route or tool that sets `PlanContext.step`. The control token has no API at all.
- **Token form.** Tokens are 256-bit (`secrets.token_hex(32)`), per launch, in memory only, and kept by their sha256.
- **Minted in S3 production code:**
  - `ui`, by `http_engine.start`. It is kept in `http_engine.UI_TOKEN` and not delivered anywhere (see 13.3).
  - `mcp:stdio`, by `Engine.__post_init__`. It is written raw to each project's `.attach`.
  - `acp:hermes`, other `mcp:<name>` tokens and `control` are only minted by tests in S3.
- **Scopes.** Every kind is minted with `{read, write, render}` by default. `render` is checked nowhere in S3. A narrower set is possible only through `Tokens.mint(scopes=...)`, which tests use.
- **Authentication.** On every engine route, a missing, unknown, or duplicated `Authorization` header, or one that isn't `Bearer <token>`, gets **401** `{"ok": false, "error": "missing or unknown token"}` with `Connection: close`.

**Scope table (as the code has it):**

| Kind | Actor | `step` on lines | Default scopes | Timeline read tools¹ | Write tools² | REST GET | REST POST writes | HTTP /mcp `tools/list`, `initialize`, `ping` | HTTP /mcp `resources/list` | HTTP /mcp `resources/read` | GET /mcp stream |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ui` | human `user` | none | read, write, render | yes | yes | yes | yes | yes | yes | yes | yes |
| `acp:hermes` | agent `hermes` | `PlanContext.step` (null in S3) | read, write, render | yes | yes | yes | yes | yes | yes | yes | yes |
| `mcp:<name>` (incl. `mcp:stdio`) | agent `<name>` | none | read, write, render | yes | yes | yes | yes | yes | yes | yes | yes |
| `control` | none | — | read, write, render (nominal) | **`permission_denied`** | **`permission_denied`** | **403 `permission_denied`** | **403 `permission_denied`** | yes | **yes (see 13.9 Q1)** | **`-32602` "unknown resource uri"** | **yes (see 13.9 Q1)** |
| any kind without `read` | — | — | (test-only) | `permission_denied` | (needs `write`) | 403 | (needs `write`) | yes | yes | `-32002` "Resource not found", `data` = the `permission_denied` body | **403** |
| any kind without `write` | — | — | (test-only) | yes | `permission_denied` | yes | 403 | yes | yes | yes | yes |

¹ `get_timeline`, `get_hash`, `list_markers`, `validate_timeline`, `history_list`, `history_diff`, `project_status` need `read`.
² `timeline_apply`, `history_undo`, `history_redo` **and `export_otio`** need `write`.

The control token **fails closed on every tool**:
- HTTP /mcp `tools/call` returns `isError` with `{"code": "permission_denied", "error": "this token has no 'read' scope"}` before any tool check.
- REST returns 403 with the same body, with `'read'` on GET and `'write'` on POST.

### 13.3 Token delivery (out of S3)

How the Edit page (the `ui` token) and Electron main (the `acp:hermes` and `control` tokens) receive their tokens is **out of S3**. When it is built, delivery goes **through the Electron preload, in memory only**: never in a URL, a query string, `localStorage`/`sessionStorage`, a cookie, or a file. The one exception is the stdio proxy's `mcp:stdio` token, which goes in `.attach` (mode 0600) per D14.

### 13.4 Routes

- **REST reads:** `GET /api/projects/<id>/{status,hash,history,history/diff,events}` (D25, D26).
- **REST writes:** `POST /api/projects/<id>/{timeline_apply,history_undo,history_redo}`.
  - The JSON body goes to `Oplog.call` unchanged. No body (no `Content-Length`) reads as `{}`.
  - Any other path under `/api/projects/` gets 404 `{"ok": false, "error": "unknown project route"}`.
- **Project-id decoding (Glyph fix 1).** On **both** GET and POST, the path is split on `/` **raw** first, and then each segment is URL-decoded **once** (`urllib.parse.unquote`). **[R]** Ada's 8:58 PM wording is "split the path first, then decode each segment, the same way on GET and POST"; the restored text said only the `<id>` segment is decoded.
  - So `%70%31` is `p1` on both methods.
  - `%2570%2531` is the id `%70%31` (`not_found`), not `p1`.
  - `p%2F1` is the id `p/1` (`not_found`), not a split path.
  - Before the fix, GET decoded the whole path before routing.
- **Status codes** (`http_engine.STATUS`): `invalid_op` 400, `schema_mismatch` 400, `bad_input` 400, `not_found` 404, `conflict` 409, `undo_blocked` 409, `invalid_doc` 422, `permission_denied` 403, `engine_offline` 503, `needs_approval` 202, `failed` 500. The body is the error's `as_dict()`.

### 13.5 HTTP /mcp

- **`POST /mcp` takes one JSON-RPC message per request.**
  - **400 + `-32700` (`id: null`) + `Connection: close`:** any body refusal (D27: `Transfer-Encoding`, a malformed or duplicate `Content-Length`, over `MAX_BODY`), and a body that isn't UTF-8 JSON. No `Content-Length` reads as an empty body, which is `-32700`.
  - **400 + `-32600` (`id: null`):** a message that isn't an object or has no string `method` (D15). The connection stays open.
  - **200 + `-32602` (with the request's `id`):** `params` present but not an object.
  - **202, empty body:** a notification (no `id`), including one whose `params` is invalid.
  - **200** for every other reply, including `isError` tool results.
  - `tools/list` lists **only the 11 timeline tools**.
  - Unknown methods get `-32601`. `resources/subscribe`/`unsubscribe` reply `{}`; updates go out on GET /mcp. `prompts/list` returns `[]`.
- **`GET /mcp`** is an SSE stream (`text/event-stream`, `Connection: close`). It sends `notifications/resources/updated` `{uri: "timeline://<id>"}` for every new log entry in **every** project the engine has open. **That includes projects opened after the stream connected (Glyph fix 2):** the listener is registered on the `Engine`, not per project.
  - It sends `: keepalive` every 15 s.
  - It needs `read` scope; without it the reply is 403.
  - A client whose queue fills (1024 notes) is dropped.
  - The stream doesn't take `Last-Event-ID`.
  - **[R]** Before routing, `GET /mcp` runs the same body checks as every method (§6 D27(d), Ada 8:58/9:02 PM): `Transfer-Encoding`, an invalid or duplicate `Content-Length`, or any valid length above 0 gets 400 `-32700` `id: null` + `Connection: close`.
- **Order inside `POST /mcp`:**
  1. Host/Origin/Content-Type guard (421/403/415).
  2. `body_length` (Transfer-Encoding, then `Content-Length`).
  3. Over cap.
  4. Token (401).
  5. Body read and parse (`-32700`).
  6. D15 shape (`-32600`/`-32602`).
  7. Notification (202).
  8. Dispatch.
  9. For `tools/call`: unknown tool name `-32602` → `arguments` not an object `-32602` → control token `permission_denied` → §13.7.

### 13.6 `used` and exports

- **`used`.** It appears in a `timeline_apply` result **only** when at least one `_s` argument was converted. It holds `{"<key>": {"ticks": <int>, "seconds": <float(Fraction(ticks, 705600000))>}}`.
  - **The key** is the `_s` argument's own name, so it is the same for every op: `at_s`, `dur_s`, `src_in_s`, `src_out_s`, `fade_in_s`, `fade_out_s`.
  - **Anchors** go under **`offset_s`**, not `anchor.offset_s`.
  - **Collisions.** When several ops (or the anchor and a top-level arg) convert the same key, **the last op in batch order wins**.
  - **`src_s`** is a **list** of two `{ticks, seconds}` objects. A `src_s` that isn't a two-element list is passed to the engine unconverted as `src`, with no `used` entry.
  - A cached retry adds `used` again from this call's own conversion.
- **Exports.** `export_otio` writes `<project>/exports/<id>-v%06d.otio`, where the number is the current `version`. It returns `{"path", "timeline_hash"}` and needs `write`. It runs only on an open engine; with the app closed it returns `engine_offline`.

### 13.7 Error order (as the code has it)

**/mcp timeline tool** (`mcp_timeline.run_tool`; the same on HTTP /mcp, attached stdio and closed stdio):

1. **`schema_version` guard:** present and not `"hs.timeline/1"` → `schema_mismatch` `bad_schema` @ `/schema_version` with `expected` and `got`. Otherwise it is dropped from the arguments.
2. **`validate_timeline` only:** `read` scope → unknown args (`unknown_arg` @ `/<arg>`) → no `doc` (`missing_arg` @ `/doc`) → the `doc` checks → `{ok: true, hash}`. It never touches a project.
3. **No `project_id`** → `invalid_op` `missing_arg` @ `/project_id`, no `id` (§11 row G).
4. **Scope:** `write` for the three writes and `export_otio`; `read` otherwise → `permission_denied`.
5. **Unknown args** for `get_timeline`, `get_hash`, `list_markers`, `export_otio` and `project_status` (`unknown_arg` @ `/<arg>`, first by `repr` sort).
6. **Project lookup** (only for a string `project_id`):
   - On an open engine: `Engine.get`, which opens lazily. A lock held elsewhere → `failed` + `LOCKED_HINT`.
   - On closed stdio: `ClosedProject`, which can raise the store bodies of §11 rows E/F.
   - Only a `not_found` here falls through to step 7. Any other error is returned as is.
7. **Project-id precheck.** When the project can't be resolved (`project_id` isn't a string, or there's no such project), `/mcp` returns `Oplog.precheck(tool, args)`. That is the engine's own checks, in the engine's own order, run on a shadow log with doc id `null`. The call **never reaches an engine**.
   - Writes: `check_apply_envelope` / `check_undo_envelope`. The `project_id` check sits inside `_check_args`, after unknown/missing/`client_op_id`/`group_id`/`summary`.
   - History: `history_list`/`history_diff` arg checks.
   - Others: `_check_project_id`.
   - A non-string id gives `bad_arg` @ `/project_id` with no `id`. A string id gives `not_found` with that `id`.
8. **`engine_offline`** (writes and `export_otio` on closed stdio), `503` over HTTP. It comes **after** steps 1–7, so on a closed app these all win over `engine_offline`: a schema error, a missing or bad `project_id`, a precheck answer for an unknown project, and a damaged-store body.
9. **Damaged store** (open engine): the stored `failed` / `schema_mismatch` / `invalid_doc` body (§11 rows E/F).
10. **`timeline_apply` on an open engine**, under the project mutex:
    1. Strip forged `actor`/`step`.
    2. `check_apply_envelope` (D21 step 3b).
    3. The /mcp op stage, op by op in batch order: check view (`check_op_args` steps 1–5) → both-sent → `_s` conversion (D21/D23/D31).
    4. `Oplog.call`: the envelope again, dedupe/`client_op_id_mismatch`, conflict, op checks, validator.
    5. `repoint` (D22).

    `history_undo`/`history_redo` go straight to `Oplog.call`.
11. **Reads:** `project_status` → status (a damaged store → its body). The others run under the mutex: `history_list`/`history_diff` run the engine's D19 checks (§11 row A), and `get_hash` → `head()`.

**REST POST write:**
1. Guard.
2. `body_length` → 400 + close.
3. Token → 401.
4. Route shape → 404.
5. Over cap → 400 + close.
6. Body JSON → 400 `{"ok": false, "error": "invalid JSON body"}`.
7. No session or no `write` → 403.
8. `Engine.get` (lazy open; `not_found`; `failed` when locked).
9. `Project.write` → `Oplog.call` (a damaged store → its body).

**REST GET:**
1. Guard.
2. **[R]** Body checks before routing (Ada 8:58/9:02 PM): `Transfer-Encoding` → valid single `Content-Length` → a length above 0 gets `request body not allowed`; each is 400 + close.
3. Token → 401.
4. No session or no `read` → 403.
5. `Engine.get`.
6. Route (unknown → 404).
7. For `history`/`history/diff`, the D26 query mapping and then the engine's checks.

### 13.8 Files, framing

- **Owner-only files.** Every file the store writes is created **0600**: `base.json`, `oplog.jsonl`, `timeline.json`, `snapshots/v%06d.json`, `.lock`, `.attach`, and `exports/*.otio` (chmod 0600 after OpenTimelineIO writes it). Atomic writes create their temp file 0600 before `os.replace`. Directories are created with the default mode. On Windows the modes are not enforced.
- **Windows lock.** The project lock is `fcntl.flock` (LOCK_EX for the engine, a LOCK_SH probe for readers) on POSIX. On Windows it is a one-byte `msvcrt.locking` lock at offset `LOCK_BYTE = 2**30`, far past the `.lock` JSON. Windows byte-range locks are mandatory, so other processes can still read `.lock` (the D6 message and the stdio attach both read it while it is held).
  - `tests/test_s3_lock.py` runs in the windows desktop job (step "Project lock test") and fails the job on any skip. **[R]** It is a byte-range `.lock` test and **blocks the merge** (addendum).
- **No blank-line skip on stdio.** Once a stdio session is in `Content-Length` mode, **every** line between frames must start a valid header block. A blank line (`\r\n`, `\n`, or whitespace-only) where a header block should start is a malformed header block: `-32700` `id: null`, a stderr line (`mcp: broken Content-Length framing: …`), then exit with status 1. Nothing after it runs.
  - Newline-framed sessions still skip blank lines between messages.
- **[R] Newline-mode cap (O1, Ada 8:58 PM).** A newline-framed read takes at most `MAX_BODY + 1` bytes per line. A longer line gets `-32700` `id: null`, a stderr line and a nonzero exit, and is never parsed (test 102(b2)).
- **[R] Formatting (O3).** `ruff format --check` passes on the files the PR touches (at `0282e9f` it failed on 8 of them; CI runs only `ruff check`).

### 13.9 Open questions recorded with this section (not ruled)

- **Q1. The control token outside tools.** As built, a `control` token passes `GET /mcp` (it holds the nominal `read` scope) and HTTP /mcp `resources/list`, so it can list project ids and receive `resources/updated` URIs. It also gets `-32602` "unknown resource uri" rather than `permission_denied` on `resources/read`. Failing closed there too would be a one-line change in each place; it needs a ruling.
- **Q2. RESOLVED [R] (O2, Ada 8:59 PM): a missing `hash` gets `invalid_doc` `hash_mismatch` @ `/hash`, open and closed (§11 row E).** Original question: **§11 row E, missing `hash`.** Row E's "before" says a stale **or missing** stored hash is re-stamped. Its "after" names only a stale hash. `validate()` treats `hash` as optional (`TOP_OPTIONAL`), so a `base.json` with no `hash` is still accepted and stamped. The s11 row-E probe records this as unchanged (a control, not a diff).
- **Q3. RESOLVED [R] (Ada; contract 8:32 PM): deferred to S4.** No contract test requires it. Original note: **`get_timeline{summary:true}`** (the outline with ticks + seconds) is **not built**. It is held until Wire says whether a contract test needs it. Contract test 48 reads "a clip's `at.seconds` from the summary" (see the S3 build report).

**[R] Still open after recovery:** Q1 (the control token on `GET /mcp`, `resources/list` and `resources/read`). The addendum rules only that the control token gets `permission_denied` on every **tool**; no recovered source rules Q1.

### 13.10 Tests owed in the S3 commit ([R], Ada 8:58–9:02 PM, from the addendum)

- **89:** use real ops with valid args, plus the ops whose id is optional, so every case reaches `bad_arg` at `/ops/0/id`.
- **92:** assert `/markers/1/label` and `mk1` literally.
- **94:** the actor is agent/stdio with no plan step.
- **101:** add a stray `\r`.
- **102(a):** both malformed-header lists, `5` sent twice with an embedded frame, whitespace-only, stdio `٣`, an empty value, and a blank line between frames.
- **102(b):** `16777217` with an embedded frame.
- **102(b2):** the newline cap.
- **103(v):** chunked alone, chunked with `abc`, and chunked with a duplicate `5`/`5`.
- **103(vi):** a GET with an embedded request, with `abc`, with chunked, and with `Content-Length: 2000000`.
- **104:** a project opened mid-stream gets `resources/updated` on GET /mcp.
- **D26 route test:** add the decode case.
- **Windows:** a byte-range `.lock` test in the windows job. It blocks the merge.
- **Evidence:** one probe for each §11 row in `evidence/s3-build/s11_rows/`.
