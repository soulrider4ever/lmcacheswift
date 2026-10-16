# Reimplementation Guide — MI210 + Swift-Qwen3.8 MTP3 + remote LMCache

Goal: rebuild the exact working stack on fresh hosts. Everything needed is in
this repo **except**: the base `local/vllm-mi210:*` ROCm images (built from
`davetha/mi210-vllm` / AMD `rocm/vllm` lineage, labels pinned below), the model
weights (HF download), and the big 3360d957 hybrid build context (25 MB tarball
kept only on CT115 at `/home/ubuntu/lmcache-integration-20261015/`).

## 1. Architecture

```
CT115 (192.168.1.106)                         CT125 (192.168.1.107)
AMD Instinct MI210 (gfx90a)                   CPU-only, ~64 GiB RAM class
┌─────────────────────────────────────┐       ┌──────────────────────────┐
│ Docker: vllm serve qwen38-swift-…   │       │ lmcache server (ZMQ)     │
│  vLLM 12dadcb41 + MTP3 + AITER FA   │◄─────►│  port 5556  (MTP, live)  │
│  LMCacheMPConnector (kv_both)       │ ZMQ   │  40 GiB L1 RAM, LRU      │
│  chunk/lookup_replay 800            │ KV    │  chunk 800, blake3       │
│  :8092  →  OpenAI /v1               │       │  HTTP admin 127.0.1:8081 │
└─────────────────────────────────────┘       │  (fallback 5555 chunk784 │
                                              │   is stopped+disabled)   │
                                              └──────────────────────────┘
```

The model is a **hybrid** architecture (`model_type=qwen3_5`): full-attention
layers plus Mamba/linear-attention layers. Hybrid KV handling
(`--mamba-cache-mode align`) plus MTP speculative decode is precisely what the
local patches below repair. Cache objects are RAM-only: they vanish on
cache-service restart; there is no disk L2.

## 2. Exact component inventory

| Item | Value |
|---|---|
| Checkpoint | `rovangju/Swift-Qwen3.8-27b-W8A8`, revision `bf37ab853e8dafbd531dee9cb6d0fbe813b69873`, local `config.json` SHA-256 `641acbaf484679c6973be457a68b4e28a660c2bcf23b341139122fe42dde0614` |
| vLLM in image | `0.1.dev1+g12dadcb41` — repo `https://github.com/davetha/vllm` @ `12dadcb4134ab41cf99b60a22e1222b7479e1a58` (MI210 fork; also mirrored via `davetha/mi210-vllm`) |
| vLLM image base lineage | `rocm/vllm@sha256:b8a082f346d069376d35784250e38b23a043efe979408ae3a33d7c6b62ee3276` → `local/vllm-mi210:mi210.7-aiter` → `local/vllm-mi210:avesed-qwen38-gdncdna-20261015-aiter` (`88880be6638e`) |
| LMCache inside vLLM image | source commit `3360d9570b29620e18ef264a411d2fbfee5f3915` (engine-driven MP connector + hybrid/PR4410 lineage), Python 3.14 site-packages |
| LMCache server on CT125 | upstream clone @ `3e11e10812b448142c6cdb177a3058652bd826fa`, `lmcache 0.5.7.dev22`, Python 3.12 venv at `/opt/lmcache/.venv` |
| Live vLLM image | `local/vllm-mi210:lmcache-aiter-mtp-qwen-replay-cap-v2-20261015` (`275f7b6b258f`) |
| Container runtime | Docker on CT115 (LXC with `/dev/kfd`,`/dev/dri` passed through), `--ipc host`, shm 16 GiB |

## 3. CT125 — cache server

1. `useradd --system --home /var/lib/lmcache --shell /usr/sbin/nologin lmcache`
2. `git clone https://github.com/LMCache/LMCache.git /opt/lmcache && git -C /opt/lmcache checkout 3e11e10812b448142c6cdb177a3058652bd826fa`
3. `python3.12 -m venv /opt/lmcache/.venv && /opt/lmcache/.venv/bin/pip install -e /opt/lmcache` (version must report `0.5.7.dev22`).
4. Install `systemd/lmcache-mtp-server.service`, then:
   ```
   systemctl daemon-reload
   systemctl enable --now lmcache-mtp-server.service
   ```
   Sizing note: the unit was raised from 8 → **40 GiB** (`--l1-size-gb 40`) with
   the owner's approval on 2026-10-15; the host had ≈40.5 GiB reclaimable and
   retains ≈23 GiB free while loaded. Do not size above reclaimable RAM.
5. Verify: `curl -fsS http://127.0.0.1:8081/healthcheck` → `{"status":"healthy"}`
   and `/status` shows `"chunk_size":800`, `blake3`, `memory_configured_bytes: 42949672960`.
6. Fallback unit `systemd/orig/lmcache-server.service` (+ drop-in `hybrid.conf`
   adding `--chunk-size 784 --separate-object-groups --isolated-ipc`, port 5555)
   is installed **stopped and disabled**. Chunk size is negotiated with the
   connector; a vLLM profile must point at the cache whose chunk size it
   expects (MTP lineage ⇔ 800; no-MTP fallback ⇔ 784).

## 4. CT115 — model + base image

1. Download the checkpoint to `/home/ubuntu/models/swift-qwen38-27b-w8a8`
   (read-only bind at `/models/swift-qwen38`), pinned revision above; verify
   `config.json` hash before serving.
2. Have the MI210 base image lineage available
   (`local/vllm-mi210:avesed-qwen38-gdncdna-20261015-aiter` or rebuild from
   `davetha/mi210-vllm` with AITER v0.1.21 + CDNA2 ref v1.6 per image labels).
3. Build `local/vllm-mi210:lmcache-hybrid-3360d957`: install LMCache source
   @ `3360d9570b29620e18ef264a411d2fbfee5f3915` into the image's Python 3.14
   site-packages (`/opt/python/lib/python3.14/site-packages`). The exact build
   context (25 MB) is `build.tar.gz` in `/home/ubuntu/lmcache-integration-20261015/`
   on CT115; build logs preserved in `docker/build-logs/`.
4. Apply the LMCache layout fix and AITER fallback config layers per
   `docker/Dockerfile.*` — build context = this repo root, e.g.:
   ```
   docker build -f docker/Dockerfile.layout -t local/vllm-mi210:lmcache-layout-20261015 .
   docker build -f docker/Dockerfile.aiter-mtp -t local/vllm-mi210:lmcache-aiter-mtp-gfx90a-20261015 .
   docker build -f docker/Dockerfile.qwen-mtp-group -t local/vllm-mi210:lmcache-aiter-mtp-qwen-group-20261015 .
   docker build -f docker/Dockerfile.qwen-mtp-coordinator-group -t local/vllm-mi210:lmcache-aiter-mtp-qwen-coordinator-20261015 .
   docker build -f docker/Dockerfile.qwen-mtp-fixedpoint-diag -t local/vllm-mi210:lmcache-aiter-mtp-qwen-fixedpoint-diag-20261015 .
   docker build -f docker/Dockerfile.qwen-mtp-replay-retention -t local/vllm-mi210:lmcache-aiter-mtp-qwen-replay-retention-20261015 .
   docker build -f docker/Dockerfile.qwen-mtp-replay-cap -t local/vllm-mi210:lmcache-aiter-mtp-qwen-replay-cap-20261015 .
   ```
   `Dockerfile.qwen-mtp-coordinator-diag` is a read-only diagnostic side-branch
   (not on the live path). The live `…-replay-cap-v2` image additionally carries
   the final `lmcache_mp_connector` revision whose **exact bytes** are pinned in
   `overlay/live/lmcache_mp_connector.py` (COPY that file over the replay-cap
   stage to reproduce v2 byte-for-byte).

   ⚠ Context note: the shipped `docker/Dockerfile.*` expect overlay files at the
   context root with their original flat names (`kv_cache_utils.qwen_mtp.py` …).
   When building from this repo, either copy files from `overlay/` into the
   context root or edit the COPY sources. `overlay/live/` is authoritative.

## 5. Launch the inference container

Use `launch/docker-run-mtp3-live.sh` (generated from the live container;
non-secret fields only). Key knobs, full argv in `launch/live-args.json`:

- `ROCM_AITER_FA`, `--mamba-cache-mode align`, MTP `num_speculative_tokens=3`
- `--max-model-len 262144 --max-num-seqs 8 --max-num-batched-tokens 1567`
  (1567 = odd tail so scheduler blocks stay aligned; batch 1567 with chunked
  prefill), `--gpu-memory-utilization 0.99`, FULL_DECODE_ONLY cudagraphs,
  async scheduling, `--enable-prefix-caching`, seed 42, qwen3 reasoning parser,
  qwen3_xml tool parser, port 8092
- `--kv-transfer-config`:
  ```json
  {"kv_connector":"LMCacheMPConnector",
   "kv_connector_module_path":"lmcache.integration.vllm.lmcache_mp_connector",
   "kv_role":"kv_both",
   "kv_connector_extra_config":{
     "lmcache.mp.host":"tcp://192.168.1.107","lmcache.mp.port":5556,
     "lmcache.mp.mp_transfer_mode":"engine_driven",
     "lmcache.mp.isolated_ipc":true,
     "lmcache.mp.lookup_replay_tokens":800}}
  ```
- Env: AITER v1 knobs (`VLLM_ROCM_USE_AITER=1`, `AITER_ROCM_ARCH=gfx942;gfx950`
  with `PYTORCH_ROCM_ARCH=gfx90a`, `HSA_NO_SCRATCH_RECLAIM=1`,
  `HIP_FORCE_DEV_KERNARG=1`, `GPU_PINNED_MIN_XFER_SIZE=67108864`) plus JIT/cache
  volume mounts (`/cache/aiter`, `/opt/aiter-jit`, inductor, triton, vllm caches).
- `--restart unless-stopped`; container name
  `qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015`.

First boot JIT-compiles AITER/Triton (slow once); subsequent boots reuse the
mounted caches.

## 6. Pinned ground-truth hashes (live container files, 2026-10-16)

`overlay/live/` — if any patch-derived file differs, these bytes win:

```
71271ca62b31e623292f0888de44cda1faf0f30028dbe4fede0c4190f37d30fa  kv_cache_utils.py   (vllm/v1/core/)
f1764178cf8e31dd0a974c5f95b5a2807e917d9ca168771526298b2c8c43a21a  kv_cache_coordinator.py (vllm/v1/core/)
84eeda8f6f1df47840a31ae5b0488a25e7263341e65439e858300ff2ef4c9e68  single_type_kv_cache_manager.py (vllm/v1/core/)
6337c4639244b729401769d3c20cc96adc27b550b9e67860b5bfac1aa7c0fcf4  lmcache_mp_connector.py (lmcache/integration/vllm/)
6ac1e91f7201a3acfb4a6365bbe1feef12d7e0035dfc51571832df8b4130c159  kv_cache_group_edits.py (lmcache/integration/vllm/)
6b81bd3bfff7723722dc99d28bdc75a4f8bd507a200e897a97d8986cf57d9d2f  DEFAULT.gfx90a-from-gfx942.json (aiter/ops/triton/configs/gfx90a/triton/attention/unified_attention/DEFAULT.json)
```
Full-tree checksums are pinned in `checksums-sha256.txt` at the repo root.

Live connectors/overloads map 1:1 to the stage files `overlay/vllm/kv_cache_utils.qwen_mtp.py`,
`overlay/vllm/kv_cache_coordinator.qwen_mtp_diag.py` (⚠ the live coordinator is
the **diag** variant, which includes the coordinator-group split),
`overlay/vllm/single_type_kv_cache_manager.qwen_mtp_retention.py`,
`overlay/lmcache/lmcache_mp_connector.replay_cap.py`,
`overlay/lmcache/kv_cache_group_edits.py`, `overlay/aiter/DEFAULT.gfx90a-from-gfx942.json`.

## 7. Bring-up verification (do all of these)

1. `GET :8092/health`, `GET :8092/v1/models`.
2. Correctness canaries (see `docs/validation-playbook.md`): five ~4K-token
   factual prompts must be correct on first pass and on repeat; repeats must
   report **3,200 local / 0 extra remote** prompt tokens via LMCache metrics
   (`scripts/replay_cap_functional.py`).
3. vLLM-only restart (`docker restart`): repeats fall back to remote refill
   (~6.8 s) then stay local (~0.63 s). The LMCache server keeps objects; a
   **cache** restart empties the RAM L1 (cold again).
4. `scripts/verify_promoted_mtp.py` — confirms container image/env/args match
   (MTP3, AITER, port 5556, replay 800) and sole port-8092 owner.
5. Optional: canonical LocalMaxxing submission — `results/localmaxxing-20261015/`
   reproduces the verified run contract (`run_benchmark.py`; credential is a
   separate protected file, never stored here).

## 8. Fallback & recovery

- **Roll back to no-MTP** (documented, not automatic):
  `docker update --restart=no` + `docker stop` the MTP container;
  `docker start qwen38-swift-w8a8-lmcache-layout-20261015`;
  `systemctl enable --now lmcache-server.service` (5555/784). The MTP profile
  returns the same way in reverse (5556 must be free before starting it).
- Proxmox snapshot `pre-lmcache-integration-20261015` exists on both CTs.
  Rollback/deletion requires the owner's two separate explicit approvals
  (workspace interlock) — never automated.
- Experimental harnesses restore the old profile in EXIT traps — do **not**
  run them as production health checks.

## 9. Measured performance (as-deployed, not microbenchmarks)

| Scenario | Median |
|---|---|
| Fresh ~4K prompt (cold remote) | 11.927 s |
| Same-prompt repeat (local L1+RAM reuse) | **0.629 s** (3,200 local tokens) |
| After vLLM-only restart / repeat | 6.770 s / 0.628 s |
| 16K prompt repeat | 0.790 s (15,200 local tokens) |
| Canonical LocalMaxxing reasoning-v1 | decode **71.768** tok/s, prefill 1142.98, TTFT 246.33 ms, 64.489 GB device VRAM peak |
| Synthetic counting decode | 92.800 tok/s |
| MTP depth sweep (pre-LMCache profile, ROCM_ATTN) | MTP=3 winner: 55.06–55.08 decode tok/s |

## 10. Known limitations (do not silently "fix" these)

- AITER JIT config for `gfx90a` is a **copied gfx942 profile**, not tuned.
- Cold fill and first request are slow; RAM cache is volatile; guest-reboot
  behavior configured but not exercised.
- Full 256K-context, sustained concurrent load, video-KV, and eviction/
  preemption pressure scenarios are unvalidated.
- The 266-token LocalMaxxing prompt sits below one 800-token chunk → **zero
  cache hits there is expected**, not a regression signal.
- `lmcache.mp.lookup_replay_tokens` must be a multiple of the scheduler block
  size (16) or the connector raises; 800 satisfies it.
- Do not bypass the ROCM_ATTN incompatible-KV-layout guard — that backend is a
  fallback only, and AITER FA is the live path.
