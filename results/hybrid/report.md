# MI210 Swift W8A8 + remote LMCache — 2026-10-15

> **Current cache override (2026-10-15 21:35 ET):** MTP port5556 is now40GiB, active/enabled `lmcache-mtp-server.service`; no-MTP port5555 is stopped/disabled. The earlier8GiB/transient and5555-running descriptions below are historical. See [current final report](mtp-aiter/report.md).

## Current/default after engineering follow-up

**ROCM_AITER_FA + MTP3 + remote LMCache is now live**, at the user's explicit
request to keep working MTP rather than restore no-MTP. Endpoint/model/context
remain `192.168.1.106:8092/v1`, `qwen38-swift-w8a8`, 262144. Active container:
`qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015`;
`unless-stopped`, no OOM/automatic restarts, sole port8092 owner. The no-MTP
container described below is retained stopped with restart=no.

The final local-retention/retrieval-accounting repairs passed 22 CPU regressions,
41 bounded validation requests, and six post-promotion requests. Five ~4K prompts:
cold/repeat medians 11.927/**0.629 s**; vLLM-only-restart/repeat medians
6.770/**0.628 s**. Repeats report 3,200 **local** tokens and zero extra external
tokens. A 16K repeat took 0.790 s with 15,200 local tokens. Text, vision, tools,
eight concurrent short requests, prefix-dependent retrieval, and red/blue image-
conditioned KV reuse/separation passed. Synthetic counting decoded at 92.800 tok/s
median, not a general throughput result. Cold transfer overhead remains large.

MTP uses the separate 800-token/8-GiB cache on CT125 port5556. Its running transient
cache was preserved; a syntax-verified persistent `lmcache-mtp-server.service`
is enabled for the next boot, without restarting the live RAM cache. Original
784-token/40-GiB port5555 cache and both Proxmox snapshots remain intact. Both
CTs have onboot=1; CT115 Docker is active/enabled. Full-context, sustained long
concurrency, video-KV and eviction/preemption behavior remain unvalidated; AITER
uses an untuned gfx942 config copy and native ROCm cache transfer is unavailable.
See [engineering report](mtp-aiter/report.md) for source, patches, raw evidence,
startup wiring, retained recovery and limitations. Earlier results below are
historical no-MTP and failed/superseded experimental profiles.

## Initial no-MTP outcome (now retained fallback)

Verified remote RAM KV-cache store and retrieval across a controlled vLLM restart, serving the same Swift Qwen3.8 W8A8 checkpoint on the original endpoint. Promoted the verified profile to Docker `unless-stopped`. **MTP is disabled**; this is not the former MTP=3 performance profile.

### Earlier isolated AITER + MTP3 experiments (superseded)

A later derivative combined `ROCM_AITER_FA`, MTP=3, and remote `LMCacheMPConnector` on a separate 800-token/chunk experimental cache (`192.168.1.107:5556`); production remains 784 tokens/chunk on `:5555`. A narrow Qwen3.5 draft-group patch removed an incorrect vLLM grouping warning. Bounded text, vision, tool-call, eight-concurrent-short-request, and vLLM-only-restart tests passed. Four ~4K-token prompts after restart each retrieved 4,000 **external** tokens with zero **local** tokens. Draft and accepted speculative tokens were measured. The unpatched candidate also retrieved externally, despite the warning.

The four-prompt identical-request A/B did **not** show a performance win: original `ROCM_ATTN` MTP3 (without LMCache) median cold/repeated wall 2.569/2.588 s; this live no-MTP LMCache profile 11.388/0.275 s; patched AITER+MTP3+LMCache 11.311/7.913 s. The original profile has a different max-batched-token setting, so these are as-deployed profiles, not an isolated kernel comparison. A second isolated coordinator-split derivative (separating target and draft full-attention groups) passed eight arithmetic responses but still reported **zero local hits** and 4,000 **external hits** on all four repeats; median cold/repeated wall was 12.075/8.632 s. Neither derivative established a local-hit fix or a performance win. The later active fixed-point diagnostic identified a sparse-retention/replay-boundary mismatch: draft attention asks for 3,200 tokens while Mamba retention kept only 4,000. An isolated replay-retention derivative keeps both boundaries. Its first four fresh/four repeated requests all answered correctly; every repeat reported 3,200 local tokens and only 800 additional external tokens, with median cold/repeat 11.241/1.835 s. This repairs the fresh-prefill local-hit failure in the bounded canary; cold transfer overhead and broader validation remain outstanding. Its AITER gfx90a config is an unvalidated copy from gfx942. **Do not promote on external hits alone.** See [experimental report](mtp-aiter/report.md) and its preserved patches, harness, JSON results, and recovery identifiers. Both patched candidates are stopped (`restart=no`); the verified no-MTP service is live again (health 200, `unless-stopped`). Full-context, sustained concurrency, image/video KV reuse and representative quality/performance remain untested for the candidates.

## Recovery points

Proxmox API snapshots `pre-lmcache-integration-20261015` completed with task exitstatus OK and remain present on CT115 (`mi210`) and CT125 (`lmcache`), node `pve`. No snapshots were deleted or rolled back; no Proxmox-host SSH was used.

The original container `qwen38-swift-w8a8-mtp3-rocm-attn-maxseq8-20261015` is retained stopped, restart=no. Full private inspect: CT115 `/home/ubuntu/docker-backups/lmcache-integration-20261015/original-inspect.json` (0600).

## Initial no-MTP configuration (retained stopped)

- CT115: `192.168.1.106:8092/v1`, model ID `qwen38-swift-w8a8`; unchanged checkpoint `rovangju/Swift-Qwen3.8-27b-W8A8`, revision `bf37ab853e8dafbd531dee9cb6d0fbe813b69873`.
- Container `qwen38-swift-w8a8-lmcache-layout-20261015`; image ID `sha256:55b9bab38540c4264340aa50f67a961a3b3a02ef411a17020eed6e9fe34598ff`, local tag `local/vllm-mi210:lmcache-layout-20261015`.
- Same vLLM `0.1.dev1+g12dadcb41`, PyTorch `2.12.0+rocm10.0.0`, MI210/gfx90a. `ROCM_AITER_FA`, BF16 KV, 262144 context, max sequences 8, max batched tokens 1567, FULL_DECODE_ONLY, prefix caching, Mamba `align`, no speculative config. Startup admitted 518137 KV tokens on first successful start; API/process arguments checked.
- Original full environment, devices, groups, IPC/network and model/cache bind mounts replayed from inspect. Text, vision, Qwen3 reasoning parser and qwen3_xml tool configuration retained.
- Connector `LMCacheMPConnector`, explicit module `lmcache.integration.vllm.lmcache_mp_connector`, role `kv_both`; host `tcp://192.168.1.107`, port 5555, `mp_transfer_mode=engine_driven`, `isolated_ipc=true`.
- CT125: LMCache PR #4410 pinned commit `3360d9570b29620e18ef264a411d2fbfee5f3915`, package version `0.5.7.dev22`. Existing CPU-only venv `/opt/lmcache/.venv`, source worktree `/opt/lmcache-hybrid-3360d957`; 40 GiB RAM L1/LRU, no L2/disk, chunk 784, separate object groups, isolated IPC. ZMQ 5555; HTTP loopback `127.0.0.1:8080`, metrics/script API disabled. Unit drop-in `/etc/systemd/system/lmcache-server.service.d/hybrid.conf`; original unit preserved.
- Both CTs onboot=1; guest Docker enabled; selected container unless-stopped; `lmcache-server.service` enabled with on-failure restart. No changes to exporter or other inference hosts.
- Usage telemetry disabled (`LMCACHE_TRACK_USAGE=false`, client also `VLLM_NO_USAGE_STATS=1`, `DO_NOT_TRACK=1`). No credentials added or changed.

## Experimental build and discovered incompatibilities

1. Unchanged MTP3 + ROCM_ATTN candidate failed at model construction: ROCM_ATTN explicitly rejects KV connectors because its layout is incompatible. No guard was bypassed.
2. AITER/no-MTP candidate reached cache registration but rejected attention group 3 as compressed (`784 tokens / 1 slots`). Root cause: upstream `_SubpagedAttentionViewEdit` emitted an NHD-shaped opaque view under an HND/BLHNC hint, so detection read the synthetic one-head dimension as block size.
3. The final local source change is only four lines in `kv_cache_group_edits.py`: emit a head-first synthetic view under HND/BLHNC, retaining identical bytes and logical paging. `layout-fix.patch` includes this and a four-layout normalization/gather/scatter regression test. **23 tests passed.** An earlier experimental physical-slot/protocol patch was discarded; it is not in the final client or server.
4. LMCache declares Python <3.14, while this serving image uses 3.14.7. Its installation was explicitly tested with `--ignore-requires-python`; Torch/vLLM were not replaced. grpcio-tools was pinned to 1.78.0 to match the preexisting grpc/protobuf runtime. Native common extensions were built; GPU extensions were disabled and the verified transfer path uses the upstream PyTorch baseline. This remains an experimental, locally patched PR build, not an officially supported release combination.

Build context, logs, stopped failed candidates and full final inspect remain on CT115 under `/home/ubuntu/lmcache-integration-20261015/`. No image/code was pushed publicly.

## End-to-end evidence

Four distinct ~4K-token prompts with known arithmetic answers were run cold. CT125 stored five 784-token chunks across four cache groups for each prompt: 80 objects / 4110417920 bytes, with no locks or active sessions left held.

Only vLLM was restarted; CT125 service PID remained 1780 and its RAM objects remained resident. Development/RPC endpoints were not enabled. Each prompt was then requested again:

| Prompt | Prompt tokens | Cold wall (s) | Post-restart wall (s) | Local hit tokens | External hit tokens | Correct answer |
|---|---:|---:|---:|---:|---:|---|
| A | 4045 | 11.419 | 8.142 | 0 | 3920 | 323 |
| B | 4047 | 11.302 | 7.756 | 0 | 3920 | 12 |
| C | 4045 | 11.373 | 7.771 | 0 | 3920 | 95 |
| D | 4043 | 11.353 | 8.081 | 0 | 3920 | 72 |

Client `kv_transfer_params.cached_token_stats` and server `Stored`/`Retrieved` logs agree. All answers matched the known result and cold answer, with normal stop. Median wall: cold 11.363 s, post-restart external hit 7.926 s. These include the new cache profile's transfer/store overhead and **do not establish a performance win against the former no-LMCache MTP3 profile**. The remote pickle/network path is substantial overhead; native ROCm transfer optimization and an MTP-compatible backend are future work.

After restart: text canary 323, synthetic red-image vision canary, structured `ready_check(status=ok)` tool canary, and eight concurrently submitted short arithmetic requests all passed. Health/models HTTP 200, expected model/context, zero automatic restarts/OOM. Server healthy, 80 objects, zero read/write locks and active sessions. 5555 reachable from gateway; 8080 connection refused from LAN.

This initial no-MTP validation did not include a full-256K prompt, eight long-context streams, comprehensive quality score, or image/video KV reuse. Later isolated MTP-with-LMCache and image-KV checks are recorded in the follow-up above and experimental report. Four arithmetic answers are bounded correctness evidence, not a general quality benchmark. The cache is RAM-only and does not survive a CT125/service restart.

## Initial baseline service-only rollback (historical, not executed)

On CT115, disable restart and gracefully stop `qwen38-swift-w8a8-lmcache-layout-20261015`, then set the preserved `qwen38-swift-w8a8-mtp3-rocm-attn-maxseq8-20261015` to unless-stopped and start it. Verify health/models and text/vision/tool canaries. This restores the exact original MTP3 definition without Proxmox snapshot rollback. Snapshot rollback/deletion would separately require the standing two explicit approvals.
