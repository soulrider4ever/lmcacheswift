# MI210 Swift Qwen3.8 W8A8 MTP3 + ROCM_AITER_FA + remote LMCache — 2026-10-15

## Latest result — promoted at user request (2026-10-16 UTC)

**Live/default: ROCM_AITER_FA + MTP3 + remote LMCache.** The user explicitly
requested keeping the working MTP service instead of restoring no-MTP.
Container `qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015`
uses `unless-stopped`; the former no-MTP container remains stopped with
`restart=no`. Endpoint: `192.168.1.106:8092/v1`, model `qwen38-swift-w8a8`,
context 262144, max sequences 8, batch 1567. Image ID:
`sha256:275f7b6b258fa87a2e22cf796ea9548bab78953ebe87ce45ff65eee1cd15bdef`.

Two repairs restore genuine local reuse: retain Mamba's shifted replay checkpoint,
then reserve an 800-token local replay tail while preserving full remote-store
accounting and releasing unused lookup locks once at admission. The connector
option `lmcache.mp.lookup_replay_tokens=800` is enabled only for this deployment;
its default is 0. Prior Qwen draft-group/coordinator patches remain included.

| Final derivative phase | Requests | Median wall | Local tokens/request | Extra remote tokens/request |
|---|---:|---:|---:|---:|
| Fresh ~4K prompts | 5 | 11.927 s | 0 | 0 |
| Same-process repeat | 5 | **0.629 s** | 3,200 | 0 |
| After vLLM-only restart | 5 | 6.770 s | 0 | 3,200 |
| Repeat after restart | 5 | **0.628 s** | 3,200 | 0 |

All 20 responses were correct, including a fifth question requiring a synthetic
phrase from the beginning of the cached prefix. The final derivative passed
**41 bounded requests** overall: those 20, text/vision/tools, eight concurrent
short requests, fresh/repeated 16K context, exact counting, red/blue image-KV
reuse/separation, and three synthetic counting decode measurements. The 16,046-
token prompt repeated in **0.790 s**, with 15,200 local/zero extra remote tokens.
Both images repeated correctly with 2,400 local tokens; the different blue image
first missed both caches after the red image, establishing bounded identity
separation. **22 CPU regression checks pass.**

Synthetic 1–100 counting decode: **92.800 tok/s median**, three 391-output-token
requests, using `(output_tokens - 1) / server_decode_time`. Each proposed 294 and
accepted 292 speculative tokens. This highly predictable workload is not general
throughput evidence. No new no-MTP counting A/B was run after the user's request
to leave MTP serving.

After promotion, six additional requests verified text, forced tool calls,
vision, counting 1–30, and fresh/repeated prefix-dependent retrieval. The fresh
prefix took 11.312 s; repeat 0.717 s, 3,200 local/zero extra remote tokens.
Health/models returned 200; actual PID-1 arguments and Docker configuration
confirm MTP3/AITER/port5556/replay800; exactly this container owns port8092.
OOM=false, automatic restarts=0. See `promotion-verification.json`.

### Persistence and preserved recovery

- Both CT115 and CT125 are running with onboot=1; CT115 Docker is active/enabled.
- Current cache: **40 GiB RAM-only L1/LRU**, chunk800, port **5556** on
  CT125 `192.168.1.107`. Persistent `lmcache-mtp-server.service` is active/enabled;
  the transient experimental unit is no longer the live cache.
- Joey approved resizing8→40GiB at2026-10-15 21:35ET. Restart cleared RAM
  objects; inference reconnected without its own restart. Correct4K canaries
  took11.678s cold/0.731s repeat. Roughly40.5GiB process memory and23GiB host
  available afterward. This is capacity, not a transfer/decode speed improvement.
- Original no-MTP cache `lmcache-server.service`, chunk784/port5555, is
  **stopped and disabled**, with definition/files retained. It consumes no
  serving-process RAM and is not an available listener until manually started.
- Cache objects do not survive a cache-service or guest restart. No disk L2.
  Admin API is loopback-only8081; usage telemetry/metrics/script API disabled.
  Startup is configured; guest-reboot behavior has not been exercised.
- Both original snapshots remain present, verified through Proxmox API. No
  snapshot rollback/deletion, Proxmox-host SSH, or Nginx Proxy Manager access.
  Private inspect backups remain only on CT115; none are in this repository.

### Current recovery policy

The user requested leaving working MTP as default. Do not run the experimental
harnesses as production health checks: their EXIT handlers restore the former
no-MTP profile. They are archived experiment drivers only. The no-MTP fallback
is still inspectable/stopped with its port5555 cache definition retained but disabled, but should not
be restored automatically against that instruction. Future maintenance must
retain the current MTP definition and verify the actual listener/model/canaries.
The former main experiment runner completed before promotion; no recovery runner
remains capable of changing this service.

### Remaining limits

Cold store/transfer overhead remains ~12 s for these 4K prompts and ~46 s for the
16K prompt. The native ROCm transfer extension remains unavailable, so this uses
the PyTorch/CPU baseline. The gfx90a AITER config is still an **untuned copy from
gfx942**, not validated hardware tuning. Full 256K prompts, sustained long-context
concurrency, eviction/preemption recovery, video-KV reuse and broad quality were
not validated. Promotion was the user's explicit operating choice after bounded
checks, not a claim that these remaining limits were resolved.

Runtime patch hashes matched repository sources:

- Connector: `6337c4639244b729401769d3c20cc96adc27b550b9e67860b5bfac1aa7c0fcf4`.
- Mamba manager: `84eeda8f6f1df47840a31ae5b0488a25e7263341e65439e858300ff2ef4c9e68`.

Reproduce CPU checks with:
`python3 -m unittest discover -s benchmarks/mi210-lmcache-hybrid-20261015/mtp-aiter -p 'test_*.py'`.
Historical failures and superseded candidates follow; their no-promotion warnings
refer to those earlier images, not the live retrieval-cap derivative above.

## Final live LocalMaxxing benchmark (2026-10-15 ET)

Unchanged live service, one warmup+three serial canonical reasoning-v1 requests:
**71.768tok/s median decode** (71.624–72.148), representative1142.98 prefill tok/s,
246.33ms TTFT,88.92 total tok/s,64.489GB peak device-used VRAM (not process-attributed).
266prompt/1024output, zero cached tokens; prompt below800-token block, so not a
remote-cache performance test. MTP696/987 accepted/proposed. Output truncated;
Verified is speed evidence, not quality. No restarts/OOMs or configuration changes.
[Public Verified run](https://www.localmaxxing.com/en/runs/cmvab17cq0182le01jj43pl4b); [full benchmark/evidence](../../localmaxxing/mi210-swift-mtp3-aiter-lmcache40g-20261015/report.md).

## Earlier candidate results and retained service

A **separate experimental candidate** ran MTP3, `ROCM_AITER_FA`, and `LMCacheMPConnector` together on CT115 (MI210/gfx90a). It answered bounded text, synthetic-red-image, tool-call, eight-concurrent-short-request, and 1–100 generation canaries correctly. Across a vLLM-only restart, four distinct ~4K-token prompts returned the expected arithmetic answers, each reporting **0 local and 4,000 external cached tokens**. The CT125 experimental cache remained running during the restart. MTP drafting/acceptance appeared in vLLM metrics and logs. This proves a working bounded combination, **not** general correctness or a performance win.

**Do not promote this build.** It is much slower than the preserved original MTP3/no-LMCache service on the four ~4K prompts, and repeated same-process requests have **zero local prefix hits**. The known-good no-MTP LMCache container `qwen38-swift-w8a8-lmcache-layout-20261015` was restored to `192.168.1.106:8092/v1`, health 200, correct arithmetic answer, Docker `unless-stopped`, OOM=false, automatic restarts=0. Both experimental MTP containers and the original MTP3 container remain stopped/recoverable. The production cache on CT125 remains unchanged on port 5555, chunk size 784. The separate, transient experiment cache is on port 5556, chunk size 800; both were healthy at final inspection. The original pre-integration snapshots on CT115/CT125 were not rolled back or deleted; there was no Proxmox-host SSH.

## Code-path investigation and isolated patch

- The original `ROCM_ATTN` backend rejects KV connectors at startup; no guard was bypassed. `ROCM_AITER_FA` accepts the connector. MTP graph capture first failed because AITER lacked `gfx90a/triton/attention/unified_attention/DEFAULT.json`. A derivative image copied a `gfx942` Triton config as an **untuned, experimental fallback**; this is not evidence of correct gfx90a tuning. The MTP vLLM block is 800 tokens, requiring a separate 800-chunk LMCache server; production's 784-chunk server was not modified.
- In the initial AITER/MTP candidate, vLLM `kv_cache_utils.py` warned it could identify no draft KV group and therefore treated every group, including Mamba groups [0,1,2], as draft. Its message claimed any external tier would store without ever serving a hit. That is **too broad for this connector**: post-restart responses and `external_prefix_cache_hits_total` showed 4,000-token hits. The warning describes the vLLM *local prefix-cache coordinator's* group fallback, while LMCache's external lookup/transfer can still serve the prompt. It should not be read as proof of external retrieval failure.
- Qwen3.5 MTP registers its one draft full-attention layer under `mtp.layers.*`; target layers are `model.layers.*`, including Mamba. A narrow model/method-scoped patch to `_annotate_eagle_groups` flags groups containing registered `mtp.layers.*` rather than flagging all groups. This removed the warning in the isolated candidate; correctness, drafting, and external restart hits remained intact. See `qwen-mtp-group.patch` and the full patched module/build recipe here. Patched image: `local/vllm-mi210:lmcache-aiter-mtp-qwen-group-20261015`, ID `sha256:ff780b5d304d37257cb806c404b02d149be09df7cde07c0a4e92b4abc3c77899`; stopped candidate: `qwen38-swift-w8a8-lmcache-aiter-mtp3-qwen-group-20261015`, restart=no.
- **Unresolved:** same-process repeats on the patched candidate still reported 0 vLLM cached tokens and 4,000 LMCache cached tokens, median 8.330 s. vLLM's coordinator still sets `drop_eagle_checkpoint_block=True` for every Mamba manager when Eagle-family speculation is enabled, even when the actual draft group is correctly identified. Its Mamba align checkpoint/replay interaction merits a separate targeted investigation; the group-annotation patch alone did not restore local hits. Do not assert the precise remaining cause without instrumenting the group lookup and checkpoint selection. The user-facing external retrieval remains correct in these bounded tests.

### Additional coordinator split experiment (not promoted)

Source review found that `HybridKVCacheCoordinator.verify_and_split_kv_cache_groups()` merged equal target and draft full-attention specs into one `SpecGroup`, promoted `use_eagle=True` to every member, and applied draft replay/drop behavior to the combined lookup. An isolated derivative grouped by `(spec, use_eagle)` instead, while retaining the Qwen layer-annotation patch. This is a plausible correctness issue in local hit selection, **not an established explanation** for missing hits. See `qwen-mtp-coordinator-group.patch`, `kv_cache_coordinator.qwen_mtp.py`, and `Dockerfile.qwen-mtp-coordinator-group`. Candidate image `local/vllm-mi210:lmcache-aiter-mtp-qwen-coordinator-20261015` (`sha256:06785dda90d87fd8ee84b52dfa65c3128c3dc536b6f9fe6fa1927d91c1a37bfc`), stopped container `qwen38-swift-w8a8-lmcache-aiter-mtp3-coordinator-20261015` (restart=no). The clone retained the original experimental connector and cache port 5556.

Four distinct ~4K arithmetic prompts each answered correctly on their first and repeated requests (`coordinator-canary.json`); cold median 12.075 s, repeated median **8.632 s**. All four repeats still reported **zero local and 4,000 external cached tokens**, so the split did **not** remedy local hits or latency. This is another bounded, sequential eight-request check, not a throughput or general correctness result. The test used a shell `EXIT` recovery trap, verified the candidate stopped, and restored the original no-MTP LMCache container (`unless-stopped`, health 200). No snapshot rollback or cache-service restart occurred. Do not promote this derivative. Next: instrument per-group cache-block registration, retained Mamba checkpoints, `find_longest_cache_hit_per_group` lengths, and connector's local/external selection on first and second requests; isolate a source-level repair with tests before another live swap.

## Active fixed-point diagnostic (2026-10-16 UTC)

The first diagnostic instrumented `find_longest_cache_hit_per_group`, but the
scheduler actually uses the combined fixed-point `find_longest_cache_hit` path.
Missing per-group-helper log lines were therefore not evidence of skipped
lookups. The subsequent read-only fixed-point diagnostic logged actual manager
returns. On repeat, group [3] (`FullAttentionSpec`, EAGLE=true) returned 3,200
from a 4,049-token lookup cap; groups [0,1,2] (`MambaSpec`, EAGLE=false) then
returned zero at that 3,200-token candidate. Reconciled local hit: zero; external
hit: 4,000. See `fixedpoint-diag-logs.txt` and
`fixedpoint-diagnostic-canary.json`. This identifies the first failing group
and its lookup boundary, unlike the earlier inference from aggregate counters.

Installed-source inspection found that `MambaManager.reachable_block_mask`
retains the unshifted prompt-minus-one boundary (4,000 here) under retention=0,
while EAGLE attention drops one 800-token unit and requires the Mamba state at
3,200. The existing checkpoint-position helper already applies the EAGLE
shift, but the sparse retention mask does not. A narrow experimental patch
adds the shifted boundary alongside the unshifted boundary, preserving the
connector's original offload opportunity. Seven CPU regression cases exercise
actual extracted manager methods; the original source fails four shifted-
boundary cases, while the derivative passes all seven. These mask-level tests
do not establish GPU state correctness; the controlled canary is separate.

### Replay-retention repair: first controlled canary

The derivative `local/vllm-mi210:lmcache-aiter-mtp-qwen-replay-retention-20261015`
(image ID `sha256:37c9a9546cb2a407f152814041bb472482ccb4f51ecd140aaa4a339187556769`)
passed four fresh and four repeated arithmetic requests. Every fresh request
reported zero local/external cached tokens. Every repeat reported **3,200 local,
4,000 total remote-matched, and only 800 additional remote tokens**. Cold median
11.241 s; repeat median **1.835 s** (1.799–1.974). This restores local prefix hits
for this fresh-prefill workload. Prior patched/coordinator derivatives took
7.913/8.632 s on similar four-prompt repeats, but prefixes differ; the repair's
measured within-run cold/repeat and exact cache counters are the direct evidence.
It does not establish a general performance win over the retained profiles.

Artifacts: `qwen-mtp-replay-retention.patch`, full derivative source,
`Dockerfile.qwen-mtp-replay-retention`, `test_replay_retention.py`,
`checkpoint_helper.fixture.py`, `replay-retention-canary.json`, and diagnostic
logs/metrics. The derivative changes only sparse Mamba retention beyond the
previous group/coordinator patches; it retains the untuned gfx942 AITER fallback,
800-token cache geometry, CPU transfer baseline and existing launch settings.
Cold store/transfer overhead remains. Promotion remains withheld pending broader
correctness, restart behavior and representative performance evidence.

### Retention-only repair: restart limitation and extended checks

After a vLLM-only restart, all four earlier prompts answered correctly with
4,000 external/zero local tokens (median 8.423 s). Repeating those externally
loaded prompts still returned zero local hits (median 8.313 s). The retention
repair alone therefore does **not** restore local reuse after external-only
loads: it cannot retain an earlier checkpoint that was not materialized by the
load. This explicitly limits the first canary's success.

The same retention candidate passed text, red-image vision, structured tools,
eight simultaneous short requests and exact counting 1–100. A fresh 16,047-token
prompt took 46.999 s; its repeat took 2.088 s with **15,200 local / 800 extra
external tokens**, confirming the shifted-boundary retention at a longer context.
These checks are bounded; there was no full-context or sustained long-concurrency
validation. See `replay-retention-restart-canary.json` and
`replay-retention-functional-canaries.json`.

A second experimental connector change introduces opt-in
`lmcache.mp.lookup_replay_tokens` (default 0). Setting 800 truncates only the
remote lookup stream, leaving the full retrieval/offload token stream unchanged.
With aligned remote lookup, a post-restart hit should load the 3,200 checkpoint
and locally recompute the final tail; warm local hits should no longer fetch
800 tokens from the CPU cache. Both eager and ordinary lookup paths share the
same truncation. Five CPU tests pass, including default-disabled behavior,
short prompts, eager lookup, remote-only load and local-hit admission. GPU
validation of this policy is tracked separately; this is not yet a result.

### Lookup-truncation prototype: restart-local recovery, but redundant offload

The opt-in lookup-truncation candidate
`local/vllm-mi210:lmcache-aiter-mtp-qwen-lookup-replay-20261015`
(`sha256:974054387392d0554a9bd7d336ce323c02f06d78cb943f5b6b5e3a247fd00639`)
passed five fresh/repeated prompts and the same five after a vLLM-only restart.
The fifth question retrieves a synthetic phrase from the beginning of the
cached prefix, rather than solving arithmetic entirely from the final tail.
All first requests missed; all repeats returned 3,200 local/zero extra remote
tokens. Post-restart requests returned 3,200 external/zero local tokens; the
next repeats returned 3,200 local/zero extra remote tokens. Medians across five:
cold 11.418 s, repeat 2.288 s, post-restart 8.337 s, repeat-after-restart 2.295 s.
This establishes bounded recovery of local reuse after external loads, unlike
the retention-only candidate.

However, it was slower than the retention-only 1.835 s fresh-prefill repeats.
Source inspection found that truncating lookup also sets `num_stored_tokens`
to 3,200, hiding the already stored 800-token tail. `GetStoreMetadata` therefore
schedules that tail for offload again. The next derivative preserves the full
remote match for store accounting and caps only retrieval eligibility. Unused
tail readers are released once at the scheduler's PREFETCHING-to-admitted
transition, not during repeatable lookup polling. Regression checks cover
allocation retries and disjoint local-prefix/replay-tail lock ranges. GPU results
for this refinement are separate; it has not been promoted.

### Admission-safe retrieval cap: initial controlled results

Candidate `qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015`,
image `local/vllm-mi210:lmcache-aiter-mtp-qwen-replay-cap-v2-20261015`,
ID `sha256:275f7b6b258fa87a2e22cf796ea9548bab78953ebe87ce45ff65eee1cd15bdef`,
retains the sparse Mamba fix and sets the opt-in replay reserve to 800. This
version queries the full remote prefix, keeps the full match in
`num_stored_tokens`, and caps `num_lmcache_hit_tokens` for retrieval. It releases
unused tail locks once at allocation/admission, alongside the preexisting
local-prefix release. Default reserve 0 preserves prior connector behavior.

Five fresh/five repeated prompts all answered correctly. Cold median 11.927 s;
repeat median **0.629 s** (0.624–0.718), with **3,200 local / zero additional
remote tokens** on all repeats. The longer fifth output retrieves the synthetic
phrase from the cached prefix. The truncated-lookup prototype's repeat median
was 2.288 s; preserving known-stored-tail accounting removed its redundant
800-token offload. These are bounded profile/workload comparisons with differing
prefix identifiers, not an isolated randomized performance experiment. Cold
transfer/store latency remains large.

The CPU suite now has **22 passing checks**: 7 retention, 5 lookup-prototype,
and 10 retrieval-cap/admission cases. Runtime restart and extended validation
for this final derivative are recorded in the latest result above.

## Identical-prompt comparison

Sequential four-request phases on the same endpoint and same four ~4K-token arithmetic questions; cold = first request for each unique prompt, warm = repeat in that process (unless explicitly post-restart). `temperature=0`, fixed seed, normal stop, all 24 answers correct. These small samples include transfer and store overhead, not a throughput/quality benchmark. The original `ROCM_ATTN` profile has `max-num-batched-tokens=4096`; AITER candidates use 1567, so this is an **as-deployed profile comparison**, not an isolated backend comparison.

| Profile | Cold median wall | Same-process repeat median | Repeat cache source |
|---|---:|---:|---|
| Original MTP3 + ROCM_ATTN, no LMCache | 2.569 s | 2.588 s | No connector stats; local cache not established |
| Known-good ROCM_AITER_FA + LMCache, no MTP | 11.388 s | 0.275 s | 3,920 local cached tokens each; no external-only hits |
| Patched ROCM_AITER_FA + MTP3 + LMCache | 11.311 s | 7.913 s | 0 local, 4,000 external cached tokens each |

Independent post-vLLM-restart validation of the patched candidate used **four different ~4K prompts**, stored cold before the restart: cold median 11.636 s; post-restart median 8.674 s; all four answers correct with 0 local and 4,000 external cached tokens each. The initial unpatched AITER/MTP candidate also retrieved 4,000 external tokens for each of four post-restart requests, despite the warning. JSON responses, harnesses, and patch are archived here under `comparison-*.json`, `qwen-group-restart-*.json`, `compare_profiles.py`, and `restart_probe_qwen_group.py`. The `canaries_mtp.py` run passed; the experimental cache retained its objects and showed no active sessions/locks at inspection.

## Earlier limitations and next engineering target (historical)

The LMCache PR build remains locally patched and installed with a Python-version metadata override; native GPU transfer is disabled and transfer uses a PyTorch/CPU baseline. The copied gfx942 AITER config is not gfx90a tuning. Full 256K context, sustained long-concurrency performance, image/video KV reuse, and general quality were **not** tested. The two LMCache services are RAM-only; neither survives its own restart with objects intact. Before promotion: instrument Mamba checkpoint/hit selection and external transfer timing, restore local prefix hits safely with regression tests, assess tuning and ROCm-native transfer, then rerun correctness and latency under representative workloads. Do not overwrite the known-good container or the original MTP3 rollback image for this investigation.
