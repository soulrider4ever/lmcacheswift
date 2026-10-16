# Bounded transfer repair verification — 2026-10-16

Live container: `qwen38-swift-w8a8-lmcache-mtp3-bounded-v1-20261016`.
Image: `local/vllm-mi210:lmcache-mtp3-bounded-transfer-v1-20261016`,
SHA-256 `76acbdb4186b2311c65f29287f1e8a6d60e59f086cb181bcffaf184092cf280c`.

All four patched runtime file SHA-256s matched `overlay/live/` byte-for-byte.
Container definition comparison preserved Env/Cmd/Entrypoint, binds and mounts,
devices, network/IPC, group/security options, limits and privilege state.
One deliberate post-deployment restart proved the persisted image still loads.
The original MTP container is stopped with restart=no; no-MTP remains off.

## Prefix-dependent correctness

Same 20,053-token synthetic prompt, with a secret phrase in its first line:

| Phase | Seconds | Local cached tokens | Additional external tokens | Result |
|---|---:|---:|---:|---|
| Cold store | 60.507 | 0 | 0 | exact `copper lantern`, normal stop |
| Repeat | 0.639 | 19200 | 0 | exact, normal stop |
| After inference-only restart | 39.373 | 0 | 19200 | exact, normal stop |
| Repeat after external retrieve | 0.636 | 19200 | 0 | exact, normal stop |

The external retrieval is longer than the 16,800-token incident trigger and
explicitly reports zero local hits. This verifies real server-cache reuse,
not just a fast repeat from local GPU KV. Source budgets every serialized RPC
below 512 MiB. Cache-server logs confirmed retrieval without EncodeError.
External transfer remains much slower than local reuse; no throughput-tuning
claim is made.

## Short decode smoke

One warmup + three deterministic exact counts from 1 through 30:
median server decode **98.43 tok/s**, median request wall **1.277 s**.
Each measured request accepted 82/84 draft tokens. Pre-repair smoke was about
98.53 tok/s; this small difference is not evidence of a performance change.
This is synthetic short decode, not the canonical LocalMaxxing workload.

## Final health

- Inference health HTTP200; expected model and max context 262144.
- Docker running/unless-stopped, zero automatic restarts, OOMKilled=false.
- No Traceback/EngineDead/EncodeError/ValueError/AssertionError in patched
  container logs during this validation.
- Cache still same PID3755, active, NRestarts0, healthy, chunk800, capacity
  42,949,672,960 bytes; used30,595,481,600 bytes; zero read/write locks and
  zero active sessions. No cache restart or pool clearing was performed.
- 15/15 CPU-source regression tests pass with real PyTorch tensor and
  MessagePack round trips; see `regression-tests.txt`.

This does not validate full256K/concurrent long prompts, general model quality,
or every transport failure. Default KV-load failure policy remains `fail`;
failed loads need not transparently retry, but the identified hybrid/stale
completion assertions are hardened.
