# Oversized pickle transfer and hybrid failure recovery repair

## Incident

Two automatic vLLM restarts on 2026-10-16 (13:07:40Z and 13:14:50Z)
followed 16,800-token external-cache retrieves. The CPU server pickled all
hybrid groups into one bytes object; MessagePack rejected its length above
`2**32 - 1`. Missing responses eventually reached vLLM's unsupported
single-group invalid-block handler and stale-completion assertion. Neither
restart was classified as an OOM.

## Repair

- `overlay/live/transfer_context/pickle.py`: split both store and retrieve
  into chunk-aligned existing-protocol RPCs. The 512-MiB budget uses the sum
  of all registered group tensor sizes plus 64 KiB overhead per tensor.
  Token history, cache salt, request ID, reader count and request config
  remain unchanged; only `start`/`end` change. Group-major order is preserved.
- `base.py`, `worker_transfer.py`: explicitly carry the logical chunk-token
  count; do not infer it from a sliding-window group's physical size.
- Stores clone batch tensors so backing-storage aliasing cannot serialize
  a much larger tensor allocation. Actual payload length is checked too.
- Retrieval accumulates batches but returns no successful result if any
  batch misses or has the wrong group/chunk count. All groups finish before
  the existing GPU scatter begins. This bounds each serialized RPC, **not
  total gathered/scattered host memory**.
- One individually oversized chunk fails locally with a clear exception;
  changing chunk size for unrelated models is not silently attempted.
- `scheduler.py`: when any hybrid group has a failed block, invalidate the
  complete request's computed state, rather than applying attention block
  geometry to recurrent state. Single-group valid-prefix behavior remains.
  Preserve the configured `kv_load_failure_policy=fail`: a failed load may
  fail that request; this repair does not promise retry on every failure.
- Late completions for absent requests and duplicate completions for active
  requests no longer assert or free active request blocks. Normal finished
  request cleanup remains.

The cache server is unchanged and was not restarted. The 40-GiB pool, port
5556, chunk 800, MTP3, context and all launch flags remain unchanged.
The original MTP replay-cap-v2 container is retained stopped/restart=no.
No no-MTP fallback is started.

## Build

Build the historical image layers documented in `reimplementation.md`, then:

```sh
docker build -f docker/Dockerfile.bounded-transfer \
  -t local/vllm-mi210:lmcache-mtp3-bounded-transfer-v1-20261016 .
```

The Dockerfile applies the four exact source files to the retained replay-cap-v2
image. `launch/docker-run-mtp3-validated.sh` now selects this image and fixes the
old generated launcher's invalid `--image` option/comment continuations;
required security options and the video group are retained.

## Regression tests

`scripts/test_transfer_fix.py` extracts the actual patched class/methods by
AST and uses real CPU PyTorch tensors with mock RPCs and scheduler state.
It automatically locates `overlay/live/` from the repository scripts directory.
15 tests cover simulated >4-GiB hybrid transfers, ordering/range metadata,
partial misses, single groups, offset ranges, size guards, real MessagePack
round trips, all four failure groups, and stale completion handling.
Run with the inference image's Python (PyTorch + msgspec installed).

Live verification results are recorded separately in `results/bounded-transfer-20261016/`.
Historical 71.768 tok/s LocalMaxxing result predates this repair; it is not
new performance evidence for the patched image.
