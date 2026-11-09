# Harbor Claude errors through TFB consumers

## Finding

On 2026-11-08, TFB baseline `5603fd2d8a0e33689bbe5f8b0399e50e2d560e80`
accepted Harbor-generated ATIF but reported a recorded Claude tool failure as a
normal result and exported its tool span with status `OK`.

The input was the existing sanitized, provider-generated Claude Code 2.1.266
[controlled session](../../fixtures/real-session/README.md), not a newly invented
provider transcript. The independent converter was Harbor 0.25.0 at
[`9c7a39b991d7e2205019f6be0598cbd22d84bfc3`](https://github.com/harbor-framework/harbor/blob/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/src/harbor/agents/installed/claude_code.py).
Its actual conversion produced 8 steps, 6 calls, 6 correlated results, and one
`extra.tool_result_is_error: true` on the intentional missing-file Read result.
TFB only read `extra.is_error`. Neither spelling is an ATIF-standard status field.

| Observation on the complete converted session | Baseline | Fixed |
| --- | --- | --- |
| Harbor source error flags | 1 | 1 |
| TFB report error count | 0 | 1 |
| TFB projected tool ERROR statuses | 0 | 1 |
| TFB projected tool OK statuses | 6 | 5 |

This fixes TFB's consumer interpretation; it does not claim a superior Claude
converter. Harbor correctly retained the error. TFB provides a readable report
and historical OpenTelemetry projection that can now interpret this known peer
convention. No universal cross-converter error vocabulary is claimed.

## Evidence and minimization

The published source's manifest pins its SHA-256. Before Harbor conversion,
`reproduce.py` removes dictionary fields whose value is the sanitizer sentinel
`[dropped]`. In particular, the public fixture uses this identical placeholder
for all UUIDs; feeding it as an actual UUID would make Harbor deduplicate unrelated
events. This adaptation removes unavailable data, not real provider IDs. Original
message IDs, tool IDs, arguments, result contents, error flags, and timestamps in
the public fixture remain unchanged. No private transcript is copied or published.

The committed [peer fixture](../../fixtures/interoperability/harbor-claude-error.atif.json)
retains the single failing step from that actual conversion, renumbers it to step 1,
and removes step metrics and trajectory final metrics. Harbor's optional cost
estimate is irrelevant to the error reproduction. All remaining fields come from
the peer output. Regeneration was checked for JSON-object equality.

Evidence tier: previously captured genuine provider output, sanitized and adapted
as described. The multi-result, conflicting-flag, missing-result, and privacy
variations in the regression suite are synthetic mutations, not additional observed
provider sessions. No chargeable provider session was started.

## Reproduce

Use a separate Python 3.12+ environment for the comparator:

```text
python -m pip install "harbor @ git+https://github.com/harbor-framework/harbor.git@9c7a39b991d7e2205019f6be0598cbd22d84bfc3"
python experiments/harbor_tool_errors/reproduce.py --output work/harbor-claude-error.atif.json
```

Run the following in a TFB environment with `.[dev,observability]` installed:

```text
python -m pytest -q tests/test_peer_tool_errors.py
tfb explain fixtures/interoperability/harbor-claude-error.atif.json
tfb observe --from atif --endpoint http://localhost:6006/v1/traces fixtures/interoperability/harbor-claude-error.atif.json
```

The last command requires a local OTLP HTTP receiver. Validation used an actual
CLI subprocess and OpenTelemetry HTTP exporter with a loopback receiver decoding
the protobuf request: 15 spans from the full Harbor artifact, six tool spans,
five `OK` and one `ERROR`, and no input/output content attributes in metadata-only
mode. This establishes the OTLP wire boundary, not Phoenix UI behavior or a
production deployment. The normal regression tests use the real OpenTelemetry
SDK with an in-memory exporter, isolated from the global tracer provider.

## Local Phoenix backend validation (2026-11-08)

With Windows, Python 3.12.14, Phoenix 21.0.0 and the pinned Harbor conversion
above, the complete public sanitized source was converted and exported with TFB
at main commit `f05fc6b6bfbdfb44598e64fb5cbd06e72f65cdbd`. Phoenix used a new
local SQLite database and a loopback-only listener. The TFB observability runtime
used Python 3.14.7, ATIF 1.8.0 and OpenTelemetry SDK/exporter 1.45.2.

```text
python -m pip install arize-phoenix==21.0.0
phoenix serve
python experiments/harbor_tool_errors/reproduce.py --output work/minimal.json --full-output work/full.json
tfb observe --from atif --endpoint http://127.0.0.1:16006/v1/traces work/full.json
```

For this run, `PHOENIX_HOST=127.0.0.1`, `PHOENIX_PORT=16006`, and
`PHOENIX_WORKING_DIR` pointed to an isolated local directory. The full Harbor
artifact was generated from the public source using the same sentinel-removal
procedure as `reproduce.py`, without the final one-step minimization. In the
Phoenix database, one trace contained 15 spans: one CHAIN, eight AGENT and six
TOOL. Five tool statuses were OK; the `tool-call-0003` Read was ERROR with generic
description. Each TOOL was parented by an AGENT under the CHAIN. No span stored
an input or output attribute in the default metadata-only mode. The Phoenix UI
trace tree also displayed `Read ERROR`. Since the source timestamps are historical,
the UI's default seven-day window did not show it; a 56-day range did.
To rerun the optional database integration check, point `TFB_PHOENIX_DB` at the
SQLite database of a dedicated Phoenix instance containing only this one exported
trace and run `python -m pytest -q tests/test_phoenix_backend_optional.py`. The
check opens the database read-only; it skips when the variable is absent. Phoenix
is not a core test dependency.

This was one local backend and one controlled real-provider session, not Phoenix
cloud, arbitrary provider versions, production validation, or independent adoption.

## Validation and boundaries

The two initial regression tests failed on baseline: the report had zero errors,
and the tool span was `OK` instead of `ERROR`. The fix recognizes the known error
flags consistently, considers all correlated results, and leaves tools without
results `UNSET`. See [outcome interpretation](../../docs/OBSERVABILITY.md#tool-outcome-interpretation)
for precedence and privacy behavior.

The original Claude parser, ATIF version label, redaction defaults, and timing
policy are unchanged. Unknown converter error conventions remain unsupported.
Provider resumption, multimodal mapping, and production backend validation were
not established. The historical delayed-result comparison with `atifact` was not
rerun and is not evidence for this fix.
