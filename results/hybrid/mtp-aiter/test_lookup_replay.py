"""Exercise actual connector lookup/admission methods without Torch/ROCm imports."""
import ast
import pathlib
import types
import unittest
import time

ROOT = pathlib.Path(__file__).parent
STATES = types.SimpleNamespace(PREFETCHING='prefetching', READY='ready', BYPASS_LMCACHE='bypass')


def load_connector():
    path=ROOT/'lmcache_mp_connector.lookup_replay.py'
    tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LMCacheMPConnector')
    names={'get_num_new_matched_tokens','_get_lookup_token_ids','on_new_request'}
    nodes=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),ast.ClassDef(name='Connector',bases=[],keywords=[],body=nodes,decorator_list=[])],type_ignores=[])
    ns={'time':time,'LMCacheMPRequestState':STATES,'RequestStatus':types.SimpleNamespace(PREEMPTED='preempted'), 'KVConnectorRole':types.SimpleNamespace(SCHEDULER='scheduler'),'logger':types.SimpleNamespace(debug=lambda *a:None,info=lambda *a:None)}
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),ns)
    return ns['Connector']


class LookupReplay(unittest.TestCase):
    def connector(self, length=4050, reserve=800):
        c=load_connector()()
        tokens=list(range(length))
        tracker=types.SimpleNamespace(state=STATES.PREFETCHING,lookup_started_at=None,cache_salt='same',request_configs={},get_token_ids=lambda:tokens)
        submitted=[]
        def submit(request_id, **kwargs): submitted.append(kwargs)
        def result(request_id):
            # Remote server has the entire original prompt; its lookup is
            # chunk aligned and reserves the final logit token as requested.
            return max(0,len(submitted[-1]['token_ids'])-1)//800*800
        c._lookup_replay_tokens=reserve;c._hit_alignment_tokens=800;c._reserve_last_token_for_lookup=True
        c._get_or_create_request_tracker=lambda request:tracker
        c.scheduler_adapter=types.SimpleNamespace(maybe_submit_lookup_request=submit,check_lookup_result=result,lmcache_tokens_per_chunk=800)
        c._connector_stats=types.SimpleNamespace(record_lookup=lambda x:None)
        c.role='scheduler';c._eager_prefetch=True
        request=types.SimpleNamespace(request_id='r',num_computed_tokens=0,status='waiting',all_token_ids=tokens,resumable=False)
        return c,request,tracker,submitted

    def test_restart_loads_shifted_checkpoint(self):
        c,r,t,calls=self.connector()
        self.assertEqual(c.get_num_new_matched_tokens(r,0),(3200,True))
        self.assertEqual(t.num_lmcache_hit_tokens,3200)
        self.assertEqual(t.num_stored_tokens,3200)
        self.assertEqual(calls[0]['token_ids'],r.all_token_ids[:3250])
        self.assertEqual(len(t.get_token_ids()),4050)  # Offload stream unchanged.

    def test_local_hit_does_not_fetch_costly_tail(self):
        c,r,t,_=self.connector()
        self.assertEqual(c.get_num_new_matched_tokens(r,3200),(0,False))
        self.assertEqual(t.num_vllm_hit_tokens,3200)

    def test_disabled_is_original_behavior(self):
        c,r,t,_=self.connector(reserve=0)
        self.assertEqual(c.get_num_new_matched_tokens(r,3200),(800,True))

    def test_short_prompt_is_miss(self):
        c,r,t,_=self.connector(length=700)
        self.assertEqual(c.get_num_new_matched_tokens(r,0),(0,False))

    def test_eager_prefetch_uses_identical_prefix(self):
        c,r,t,calls=self.connector()
        c.on_new_request(r)
        self.assertEqual(calls[0]['token_ids'],r.all_token_ids[:3250])


if __name__=='__main__': unittest.main()
