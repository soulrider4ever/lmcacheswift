# Troubleshooting — failure modes hit during integration, and their fixes

Symptoms → diagnosis → remedy, in the order we actually met them.

## 1. `ROCM_ATTN` incompatible-KV-layout guard trips / garbled reuse
- **Symptom:** vLLM refuses hybrid KV transfer or output corrupts after
  external retrieval when using the ROCM_ATTN fallback backend.
- **Cause:** LMCache sub-paged attention view assumed NHD byte order while the
  transfer core honored `HND`/`BLHNC` hints (patch 1).
- **Fix:** `layout-fix.patch`. Do **not** instead disable the vLLM guard —
  it exists to catch exactly this class of silent corruption.

## 2. MTP enabled → LMCache local hits permanently zero
- **Symptom:** external-store metrics show remote hits/misses, but vLLM-local
  prefix reuse never engages; repeats cost full cold time. Mamba groups
  "reconcile to zero hits".
- **Causes (all three were real, stacked):**
  1. Draft MTP attention group mis-detected (upstream flags the wrong group
     `is_eagle_group` for qwen3_5) → patch 2.
  2. Equal target/draft specs merged into one lookup `SpecGroup`, dragging the
     EAGLE last-block drop across the target → patch 3.
  3. Mamba shifted replay checkpoint dropped from retention, so the draft's
     reconciliation boundary had no state → patch 4.
- **Diagnostic that proved #3:** read-only fixed-point coordinator logging
  (diag lineage, `overlay/vllm/kv_cache_coordinator.qwen_mtp_diag.py`):
  draft asked 3,200 tokens, Mamba retention kept 4,000 — mismatch at the
  sparse-retention/replay boundary.

## 3. Local hits restored but repeats still ~8 s (double fetch)
- **Symptom:** after patch 4, repeats show *both* 3,200 local tokens and 4,000
  external tokens; wall time only improves partially.
- **Cause:** connector looked the full prompt up remotely, retrieving past the
  local replay checkpoint (patch 5, `lmcache.mp.lookup_replay_tokens`).
- **Remedy:** set `lookup_replay_tokens=800` (one chunk; multiple of scheduler
  block 16 required — the connector raises `ValueError` otherwise).

## 4. Progressive degradation after many repeats; locks pending
- **Symptom:** LMCache `/status` shows growing `read_locked_count` /
  `pending_keys_count`; later requests slow down.
- **Cause:** per-block lookup locks from the replay window never released;
  retrieval accounting reserved quota against replayed tail.
- **Fix:** replay-cap patch 6 (release once at admission, cap retrieval
  accounting, keep full offload accounting). Verify drain to 0 after idle.

## 5. Chunk-size mismatch class of bugs
- Cache server and connector must agree: MTP lineage ⇔ **5556 / chunk 800**;
  legacy no-MTP ⇔ 5555 / chunk 784. Symptoms of mismatch: every lookup misses,
  or assertion failures on block sizes at connector init. If a fresh rebuild
  shows 100% miss rates, check this pairing **first**.

## 6. OOM-killed vLLM after enabling LMCache sidecar-ish workloads
- Container runs `--gpu-memory-utilization 0.99` plus pinned host transfer
  buffers (`GPU_PINNED_MIN_XFER_SIZE=67108864`). Before the 40 GiB cache resize
  we had to reclaim ~40.5 GiB of host RAM; the CT125 cache must stay ≤
  reclaimable RAM (40 GiB leaves ≈23 GiB headroom on that box). If vLLM dies
  with OOMKilled=true, check **host** RAM pressure from the cache side and
  any stray second cache server holding 40 GiB (only one of 5555/5556 should
  run at a time for a given profile).

## 7. Slow first boot / slow first request
- First boot JIT-compiles AITER + Triton (many minutes) — cached afterwards in
  the mounted `/cache/aiter`, `/opt/aiter-jit`, `/cache/triton`,
  `/cache/inductor` volumes; wiping those volumes re-triggers it.
- First request after a **cache-service** restart is always cold: RAM L1 is
  volatile, no disk L2. Expected. A `docker restart` of vLLM alone keeps the
  remote store warm (cold refetch ~6.8 s instead of ~11.9 s).

## 8. Zero cache hits on the LocalMaxxing benchmark
- Not a bug: its 266-token prompt is below one 800-token chunk, so 0 prefix
  hits is the correct result. Use the 4K canaries for cache regression.

## 9. AITER config gaps on gfx90a
- Where AITER lacked a gfx90A unified-attention Triton config we installed the
  copied gfx942 `DEFAULT.json` (patch data file). If particular kernels
  regenerate or assert at JIT time, expect it to come from that untuned file;
  options are re-tune on CDNA2 or fall back to ROCM_ATTN target-only (with the
  layout patch), accepting lost MTP local reuse.

## 10. Harness foot-guns
- `run_*_canary.sh` / restart harnesses restore the **no-MTP** profile in their
  EXIT traps. They are experiment tools; never wire them to monitoring or run
  them casually against the live endpoint.
