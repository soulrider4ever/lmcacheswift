# Hybrid cache-write latency repair — 2026-10-16

Live container: `qwen38-swift-w8a8-lmcache-mtp3-background-v1-20261016`.
Image tag: `local/vllm-mi210:lmcache-mtp3-background-commit-v1-20261016`.
Source SHA256: `42cd82f29f833cef7a7cf72201f85bb3430a57382f7b4c1f4cc42edbf7edeafa`.
Parent/retained stopped rollback: bounded-transfer-v1; restart policy no.
Full runtime Config/HostConfig/mount comparison passed; only image changed.
Private inspect rollback: CT115 `/root/mi210-pre-background-commit-20261016.json`.

## Cause and change

AsyncEngineDrivenTransferContext explicitly fell back to synchronous stores for
hybrid groups. Logs showed ~1.75–1.85 seconds per 800-token store, alongside
zero-generation periods and queued requests. Kernel-shape JIT was also observed;
not every historical stall has been individually attributed.

Hybrid pickle writes now snapshot GPU data into compact owned CPU tensors before
returning, then run prepare/commit on the existing background executor. No
background task reads mutable GPU KV blocks. Two <=512MiB outstanding snapshots
are allowed. Saturation/oversize/shutdown skips optional writes with a false
completion; failure does not falsely publish successful cache events. This is
latency-first best-effort caching: remote prefixes may have gaps. Existing adapter
logs false completions as generic store errors, including deliberate skips.

Retrieval behavior, 512MiB RPC bound, hybrid failure cleanup, 256K context,
eight sequences, AITER FA, MTP3, 60GiB server and bindings are unchanged.
No cache-server restart; its existing objects survived both inference restarts.

## Validation

- Five new regression tests: background return, snapshot ownership across source
  mutation, all-group preservation, bounded overload/recovery, exception slot
  cleanup, oversize and closing (several assertions share a test).
- Prior 15 transfer/hybrid-failure tests passed unchanged. Total: 20 tests.
- Fresh 20,046-token prefix, exact `silver compass`: **19.397s** cold.
- Concurrent short arithmetic request exact `323`: **3.960s**, sent two seconds
  into the long request (not an idle-latency measurement).
- Local repeat: **1.279s**, 19,200 local tokens, zero additional remote tokens.
- Controlled inference-only restart, same correct answer: **21.381s**, zero
  local tokens, **1,600 additional external tokens**. This proves partial remote
  retrieval, NOT complete 19,200-token remote retention.
- Subsequent local repeat: **1.029s**, 19,200 local tokens.
- Historical comparable 20,053-token cold test took 60.507s; different prefix and
  concurrent short traffic here mean this is not a strict isolated benchmark.
- Container running/unless-stopped, automatic restart count zero, OOM false.
- Cache healthy, configured 64,424,509,440 bytes, zero read/write locks and zero
  pending storage/prefetch work; ~3.4GiB guest memory available. Session metadata
  may outlive requests; do not equate active session count with held locks.

## Limits

Large external loads still cost transport time, first-use shapes can compile,
and long prompts still need prefill. No full-256K or eight-long-request test.
This addresses synchronous write-induced engine stalls; it is not a guarantee
that every prompt has short time-to-first-token or that all prefixes are saved.

Short count canaries: exact 1–40, 150 output tokens, 1.724s/1.715s, normal stop.
Immutable live image: `sha256:432b6062d86507848c5fe4d57c2b161f54e9dbe207a624587544d44c2f1f4cb3`.
