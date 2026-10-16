"""CPU-only regression of actual manager methods, extracted without GPU imports.

The dropped draft boundary must remain registerable alongside the connector's
unshifted boundary. This test fails on the retained pre-patch manager source.
"""
import ast
import pathlib
import types
import unittest

ROOT = pathlib.Path(__file__).parent


def methods(path, class_name, names):
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]


class MambaSpec:
    block_size = 800


def load_manager(path):
    nodes = methods(path, 'SingleTypeKVCacheManager', ['cache_blocks'])
    nodes += methods(path, 'MambaManager', ['reachable_block_mask'])
    namespace = {'MambaSpec': MambaSpec}
    # Production helper, not a test reimplementation.
    helper = next(n for n in ast.parse((ROOT / 'checkpoint_helper.fixture.py').read_text()).body
                  if isinstance(n, ast.FunctionDef) and n.name == 'get_mamba_prefill_checkpoint_position')
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), helper,
                             ast.ClassDef(name='Manager', bases=[], keywords=[], body=nodes, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return namespace['Manager']


class ReplayRetention(unittest.TestCase):
    Manager = load_manager(ROOT / 'single_type_kv_cache_manager.qwen_mtp_retention.py')

    def mask(self, prompt=4050, eagle=True, retention=0, shared=0, start=0, end=5):
        m = self.Manager()
        m.kv_cache_spec = MambaSpec()
        m.drop_eagle_checkpoint_block = eagle
        m.cache_hit_alignment_tokens = 800
        m.block_size = 800
        m.use_eagle = False  # Mamba is a target group, not a draft group.
        m.dcp_world_size = 1
        m.kv_cache_group_id = 0
        m.num_cached_block = {'r': start}
        m.req_to_blocks = {'r': list(range(end))}
        calls = []
        m.block_pool = types.SimpleNamespace(cache_full_blocks=lambda **kw: calls.append(kw))
        request = types.SimpleNamespace(request_id='r', num_prompt_tokens=prompt, shared_prefix_boundary=shared)
        m.cache_blocks(request, end * 800, retention)
        return calls[0]['block_mask'] if calls else []

    def test_reconciled_and_external_boundaries(self):
        self.assertEqual(self.mask(), [False, False, False, True, True])

    def test_non_mtp_unchanged(self):
        self.assertEqual(self.mask(eagle=False), [False, False, False, False, True])

    def test_late_chunk_preserves_replay_checkpoint(self):
        self.assertEqual(self.mask(start=3), [True, True])

    def test_short_prompt_never_retains_negative_boundary(self):
        self.assertEqual(self.mask(prompt=750, end=1), [False])

    def test_exact_boundary_needs_logit_and_draft_replay(self):
        self.assertEqual(self.mask(prompt=4000), [False, False, True, True, False])

    def test_dense_policy_unchanged(self):
        self.assertIsNone(self.mask(retention=None))

    def test_shared_junction_and_segment_preserved(self):
        self.assertEqual(self.mask(shared=1600, retention=2400), [False, True, True, True, True])


if __name__ == '__main__':
    unittest.main()
