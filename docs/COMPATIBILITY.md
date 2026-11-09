# Compatibility Matrix

| Source or target | Portable trajectory | Target mapping | Native resume |
| --- | --- | --- | --- |
| Claude Code | **Verified:** supported JSONL records normalize to ATIF v1.7 | N/A | N/A |
| Antigravity | N/A | **Verified:** reference derived-log payload | **Blocked:** no supported historical-session import API identified |
| Codex | **Bounded:** supported rollout JSONL records normalize to ATIF v1.7; unsupported content is reported | No direct target mapping | Not implemented or verified by TFB |

The Codex adapter is limited to the source shapes described in [CODEX_IMPORT.md](CODEX_IMPORT.md); it does not support every Codex version or event type. Antigravity export is a mapping to observed derived-log JSONL structures, not a claim that the log is an authoritative native ingestion schema. ATIF portability does not change that boundary.
