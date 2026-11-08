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
