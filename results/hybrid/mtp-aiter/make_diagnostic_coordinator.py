"""Generate a read-only, bounded coordinator diagnostic from the retained candidate.

Only logs near 4K-token prompts. No KV behavior, allocation, or lookup changes.
Run from this directory and review the diff before building a derivative image.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
source = (root / "kv_cache_coordinator.qwen_mtp.py").read_text()

before = '''            manager.cache_blocks(
                request,
                num_tokens_to_cache,
                retention_interval=self.retention_interval,
            )

    def find_longest_cache_hit('''
after = '''            if 3900 <= request.num_prompt_tokens <= 4200:
                logger.warning(
                    "MTP_DIAG write group=%d spec=%s eagle=%s computed=%d "
                    "cache_to=%d prior=%d block_size=%d retain=%s",
                    manager.kv_cache_group_id,
                    type(manager.kv_cache_spec).__name__,
                    manager.use_eagle,
                    num_computed_tokens,
                    num_tokens_to_cache,
                    manager.num_cached_block.get(request.request_id, 0),
                    manager.block_size,
                    self.retention_interval,
                )
            manager.cache_blocks(
                request,
                num_tokens_to_cache,
                retention_interval=self.retention_interval,
            )

    def find_longest_cache_hit('''
assert source.count(before) == 1
source = source.replace(before, after)

before = '''            for gid, blks in zip(group_ids, blocks):
                hit_blocks[gid] = blks
                hit_lengths[gid] = group_hit

        return tuple(hit_blocks), tuple(hit_lengths)'''
after = '''            if 3900 <= max_cache_hit_length <= 4200:
                logger.warning(
                    "MTP_DIAG lookup group=%s spec=%s eagle=%s max=%d hit=%d "
                    "blocks=%s hash_count=%d",
                    group_ids,
                    type(spec).__name__,
                    use_eagle,
                    max_cache_hit_length,
                    group_hit,
                    [len(b) for b in blocks],
                    len(block_hashes),
                )
            for gid, blks in zip(group_ids, blocks):
                hit_blocks[gid] = blks
                hit_lengths[gid] = group_hit

        return tuple(hit_blocks), tuple(hit_lengths)'''
assert source.count(before) == 1
source = source.replace(before, after)

# The scheduler calls the combined fixed-point lookup. Log each *actual*
# manager result before reconciliation changes its candidate length. The
# separate per-group helper above is not invoked by the observed request path.
before = '''                if drop_eagle_block:
                    eagle_verified.add(idx)
                elif _new_hit_length < curr_hit_length:
'''
after = '''                if 3900 <= max_cache_hit_length <= 4200:
                    logger.warning(
                        "MTP_DIAG step iter=%d group=%s spec=%s eagle=%s "
                        "drop=%s candidate=%d lookup_max=%d hit=%d "
                        "blocks=%s hash_count=%d align=%d",
                        lookup_iteration, group_ids, type(spec).__name__,
                        use_eagle, drop_eagle_block, curr_hit_length,
                        _max_length, _new_hit_length,
                        [len(b) for b in hit_blocks], len(block_hashes),
                        self._cache_hit_alignment_tokens,
                    )
                if drop_eagle_block:
                    eagle_verified.add(idx)
                elif _new_hit_length < curr_hit_length:
'''
assert source.count(before) == 1
source = source.replace(before, after)

before = '''        while True:
            curr_hit_length = hit_length
'''
after = '''        lookup_iteration = 0
        while True:
            lookup_iteration += 1
            curr_hit_length = hit_length
'''
assert source.count(before) == 1
source = source.replace(before, after)

# Log fixed-point reconciliation after each group's result has been observed.
before = '''        return cache_hit_blocks, hit_length, num_uncached_common_prefix_tokens

    def find_longest_cache_hit_per_group('''
after = '''        if 3900 <= max_cache_hit_length <= 4200:
            logger.warning(
                "MTP_DIAG reconcile max=%d hit=%d per_group=%s uncached=%d",
                max_cache_hit_length,
                hit_length,
                hit_length_by_group,
                num_uncached_common_prefix_tokens,
            )
        return cache_hit_blocks, hit_length, num_uncached_common_prefix_tokens

    def find_longest_cache_hit_per_group('''
assert source.count(before) == 1
source = source.replace(before, after)
(root / "kv_cache_coordinator.qwen_mtp_diag.py").write_text(source)
