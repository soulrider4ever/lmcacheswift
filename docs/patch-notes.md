# Patch Notes — every customization, why it exists, what it changes

Six patches (diffs in `patches/`), applied as whole-file `COPY` layers
(Dockerfiles in `docker/`). Ordered by build stage. Two land in **vLLM**
(the MI210 fork @ `12dadcb41`), three in **LMCache** (engine-driven hybrid @
`3360d957` in-image), one is an AITER data-file fallback.

The story in one paragraph: Swift-Qwen3.8 is a hybrid (full-attention +
Mamba/linear) model with an MTP draft head. Upstream vLLM/LMCache hybrid prefix
caching mis-groups draft vs target KV (identical specs get merged into one
lookup group, inheriting the EAGLE last-block drop), mis-views sub-paged
attention layouts (NHD/HND), and never retains the Mamba *shifted* replay
checkpoint the draft needs. Result on MI210: zero local reuse with MTP enabled
("Mamba groups reconcile to zero hits"). The six patches together restore
correct grouping, layout views, checkpoint retention, and lookup boundaries,
taking ~4K repeat latency from "always refetch remote" to 0.629 s local.

---

## 1. `layout-fix.patch` — LMCache `kv_cache_group_edits.py`

**File:** `lmcache/integration/vllm/kv_cache_group_edits.py`
**Stage:** `lmcache-hybrid-3360d957` → `lmcache-layout-20261015`
**Problem:** `_SubpagedAttentionViewEdit` reshaped fused KV pages as
`[blocks, 2, block, heads, dim]` (NHD assumption) even when the transfer
layout hint said `HND`/`BLHNC`. The transfer core interprets hints the other
way for these groups, so gather/scatter byte order silently mismatched →
`ROCM_ATTN` incompatible-KV-layout guard trips / corrupted reuse.
**Fix:** when the layout hint is `HND` or `BLHNC`, view as
`[blocks, 2, heads, block, dim]` instead. Pages are opaque with one synthetic
head, so metadata-only change preserves byte order. Includes CPU regression
test (`tests/v1/test_vllm_kv_cache_group_edits.py`, 22 tests pass) asserting
data_ptr identity, byte equality, and round-trip gather/scatter for all four
hint spellings.

## 2. `qwen-mtp-group.patch` — vLLM `kv_cache_utils.py`

**File:** `vllm/v1/core/kv_cache_utils.py`
**Stage:** `…gfx90a-20261015` → `…qwen-group-20261015`
**Problem:** with `method=mtp`, upstream marks *last* (or, via the DeepSeek
fallback heuristic, effectively the wrong) KV group as `is_eagle_group`. For
Qwen3.5-MTP the single draft full-attention layer registers under
`mtp.layers.*` while the target uses `model.layers.*`; specs otherwise look
identical, so detection cannot distinguish them structurally.
**Fix:** for `hf_config.model_type == "qwen3_5"` with `method=mtp`, mark
exactly the groups whose layer names intersect `mtp.layers.*` as EAGLE groups
and return before the generic fallbacks. Name-based matching only.

## 3. `qwen-mtp-coordinator-group.patch` — vLLM `kv_cache_coordinator.py`

**File:** `vllm/v1/core/kv_cache_coordinator.py`
**Stage:** `…qwen-group-20261015` → `…qwen-coordinator-20261015`
**Problem:** `verify_and_split_kv_cache_groups` batches groups by equal spec
alone; target-full-attention and draft-full-attention share a spec, so they
merge into one `SpecGroup` and *all* inherit `use_eagle=True`, forcing the
draft's last-block drop onto the target side and breaking joint lookup for
the hybrid Mamba path (the coordinator still reported hits while actual local
reuse stayed 0).
**Fix:** group membership now requires `spec ==` **and** `use_eagle ==`;
draft and target full-attention stay separate spec groups with their correct
replay boundaries. Docstrings updated to state the invariant.
**Live note:** the running image carries the extended *diag* variant of this
file (`overlay/vllm/kv_cache_coordinator.qwen_mtp_diag.py`, which equals patch
output + read-only fixed-point instrumentation retained for diagnosis; live
hash matches it). Side branch `Dockerfile.qwen-mtp-coordinator-diag` /
`Dockerfile.qwen-mtp-fixedpoint-diag` were the read-only diagnostic lineage
that located the sparse-retention mismatch (draft wanted 3,200 tokens while
Mamba retention kept only 4,000).

## 4. `qwen-mtp-replay-retention.patch` — vLLM `single_type_kv_cache_manager.py`

**File:** `vllm/v1/core/single_type_kv_cache_manager.py`
**Stage:** `…qwen-fixedpoint-diag-20261015` → `…qwen-replay-retention-20261015`
**Problem:** hybrid prefix-cache alignment only retains the Mamba state at the
unshifted prompt boundary (`num_prompt-1` capped at alignment). MTP draft
lookup reconciles against the **shifted** checkpoint
(`get_mamba_prefill_checkpoint_position(..., shifted=True)`); that checkpoint
block was dropped, so every speculative repeat missed locally (zero-hit
reconciliation).
**Fix:** when a Mamba group has `drop_eagle_checkpoint_block` and cache-hit
alignment configured, also retain the shifted checkpoint boundary. Both
boundaries stay reachable. Pure additive boundary append — CPU unit test
`scripts/test_replay_retention.py` passes.

## 5. `lmcache-lookup-replay.patch` — LMCache `lmcache_mp_connector.py`

**File:** `lmcache/integration/vllm/lmcache_mp_connector.py`
**Stage:** `…qwen-replay-retention-20261015` → `…qwen-lookup-replay-20261015`
**Problem:** the connector looked the *entire* prompt up against the remote
store and retrieved everything past the local replay checkpoint. Retrieved
tokens then collided with locally-replayable tail blocks: external hits were
counted while local hits stayed zero, and EAGLE drop/replay double-counted
the tail.
**Fix:** new connector extra-config knob **`lmcache.mp.lookup_replay_tokens`**
(default 0 = off): the lookup token list is truncated by N tokens so the
last N tokens are always replayed locally from retained checkpoints instead
of being looked up remotely. Validates N ≥ 0 and N % scheduler_block_size == 0
at config time. Tests: `scripts/test_lookup_replay.py`.

## 6. `lmcache-replay-cap.patch` — LMCache `lmcache_mp_connector.py` (live = v2)

**File:** same, final live revision
**Stage:** `…qwen-lookup-replay-20261015` → `…replay-cap` → **v2 (live)**
**Problem:** with lookup-replay active, store-side accounting still reserved
the replay tail against remote retrieval quota, and per-block lookup locks
taken during the replay window leaked until timeout — degrading subsequent
requests (metrics: `pending_keys`, `read_locked_count` climbing).
**Fix:** keep **full remote-store accounting** (offload still records the whole
sequence) but (a) cap retrieval accounting at the replay boundary and (b)
release unused lookup locks **once** at admission instead of per-block.
Deployment sets `lmcache.mp.lookup_replay_tokens=800` — one chunk — matching
server chunk size 800. Tests: `scripts/test_replay_cap.py`.
**After this patch:** fresh 4K 11.927 s → repeat **0.629 s**, 3,200 local /
0 extra remote per repeat, stable across vLLM restarts; 41 bounded validation
requests green (text/vision/tools/16K/concurrency/image-KV separation).

## AITER data fallback (not code)

`overlay/aiter/DEFAULT.gfx90a-from-gfx942.json` → installed at
`aiter/ops/triton/configs/gfx90a/triton/attention/unified_attention/DEFAULT.json`.
Copied gfx942 unified-attention Triton config as the gfx90a fallback where
AITER lacked one. **Untuned** for CDNA2; kept because AITER FA won end-to-end
anyway. Do not present its tuning as MI210-validated.

## Upstreaming status

Patches 1–3 are candidates for upstream issues (LMCache layout-hint bug; vLLM
Qwen3.5-MTP group detection + spec-group split). 4–6 are entangled with the
in-image LMCache `3360d957` engine-driven branch; the `lookup_replay_tokens`
knob is designed to be upstream-shaped (opt-in, validated, default-off).
None have been submitted as of backup time.


## 2026-10-16 bounded transfer and scheduler failure cleanup

See [incident, implementation and validation](bounded-transfer-fix-20261016.md).
Four new authoritative files under `overlay/live/` apply atop the historical
replay-cap-v2 image; no cache-server code change or cache restart is required.
