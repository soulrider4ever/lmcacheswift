import ast
from concurrent.futures import Future
from dataclasses import dataclass, replace
from math import prod
from pathlib import Path
from types import SimpleNamespace as NS
import pickle
import unittest
import torch
ROOT=Path(__file__).resolve().parent
if (ROOT.parent/"overlay/live/transfer_context").is_dir():
    ROOT=ROOT.parent/"overlay/live"

def extract(path, clsname, methods=None, ns=None):
    tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==clsname)
    if methods:
        cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in methods]
        cls.bases=[]
    mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),cls],type_ignores=[])
    scope=ns or {}
    exec(compile(ast.fix_missing_locations(mod),str(path),'exec'),scope)
    return scope[clsname]
class Base:
    def __init__(self, metadata, req_client, mq_timeout):
        self.metadata,self.req_client,self.mq_timeout=metadata,req_client,mq_timeout
Context=extract(ROOT/'transfer_context/pickle.py','EngineDrivenContextPickle',ns=dict(EngineDrivenContext=Base,replace=replace,prod=prod,pickle=pickle,torch=torch))
@dataclass(frozen=True)
class Key:
    start:int=0
    end:int=16800
    request_id:str='original'
    token_ids:tuple=(1,2,3)
    cache_salt:str='salt'
class Client:
    def __init__(self, grouped=True, miss_at=None): self.calls=[];self.grouped=grouped;self.miss_at=miss_at;self.payloads=[]
    def prepare_retrieve(self,key,instance):
        self.calls.append(key)
        chunks=[torch.tensor([i]) for i in range(key.start//800,key.end//800)]
        data=pickle.dumps([chunks,chunks] if self.grouped else chunks)
        f=Future();f.set_result(NS(success=len(self.calls)!=self.miss_at,data=data));return f
    def commit_store(self,key,instance,data):
        self.calls.append(key);self.payloads.append(pickle.loads(data));f=Future();f.set_result(True);return f

def context(grouped=True, miss_at=None):
    # Simulate 120 MiB/group/chunk without allocating those tensors.
    layout=NS(shapes=[(120*1024*1024,)],dtypes=[torch.uint8])
    meta=NS(layout_desc=layout,group_layouts=[layout,layout] if grouped else None,chunk_tokens=800)
    client=Client(grouped,miss_at)
    return Context(meta,client,1),client

class TransferTests(unittest.TestCase):
    def test_large_hybrid_retrieve_batched_and_ordered(self):
        c,r=context();data=c.prepare_retrieve_multigroup(Key(),7)
        self.assertEqual(len(r.calls),11)
        self.assertEqual([[int(t) for t in g] for g in data],[list(range(21))]*2)
        self.assertEqual([(k.start,k.end) for k in r.calls],[(i,min(16800,i+1600)) for i in range(0,16800,1600)])
        self.assertTrue(all(k.request_id=='original' and k.cache_salt=='salt' and k.token_ids==(1,2,3) for k in r.calls))
    def test_single_group_retrieve(self):
        c,r=context(False);self.assertEqual([int(t) for t in c.prepare_retrieve(Key(),7)],list(range(21)));self.assertGreater(len(r.calls),1)
    def test_miss_after_partial_batch_is_all_or_nothing(self):
        c,r=context(miss_at=2);self.assertIsNone(c.prepare_retrieve_multigroup(Key(),7));self.assertEqual(len(r.calls),2)
    def test_offset_range(self):
        c,r=context();data=c.prepare_retrieve_multigroup(Key(start=800,end=4000),7);self.assertEqual([int(t) for t in data[0]],list(range(1,5)))
    def test_hybrid_store_slices_every_group(self):
        c,r=context();chunks=[[torch.tensor([i+100*g]) for i in range(21)] for g in range(2)]
        self.assertTrue(c.commit_store(Key(),7,chunks));self.assertEqual(len(r.calls),11)
        for g in range(2):self.assertEqual([int(t) for batch in r.payloads for t in batch[g]],[i+100*g for i in range(21)])
    def test_single_store(self):
        c,r=context(False);self.assertTrue(c.commit_store(Key(end=1600),7,[torch.tensor([1]),torch.tensor([2])]))
    def test_bad_alignment(self):
        c,r=context();self.assertRaises(ValueError,list,c._batch_keys(Key(start=1)))
    def test_oversized_single_chunk(self):
        c,r=context();c.MAX_PAYLOAD_BYTES=1;self.assertRaises(ValueError,list,c._batch_keys(Key()))
    def test_wrong_chunk_count(self):
        c,r=context();self.assertRaises(ValueError,c.commit_store,Key(),7,[[],[]])
    def test_real_tensor_roundtrip_and_msgpack(self):
        import msgspec
        c,r=context();c.metadata.group_layouts=[NS(shapes=[(1024,)],dtypes=[torch.float32])]*2;c.MAX_PAYLOAD_BYTES=140000
        tensors=[[torch.arange(1024,dtype=torch.float32)+i for i in range(3)] for _ in range(2)]
        self.assertTrue(c.commit_store(Key(end=2400),7,tensors))
        for batch in r.payloads:
            raw=pickle.dumps(batch);self.assertLess(len(raw),c.MAX_PAYLOAD_BYTES);self.assertEqual(msgspec.msgpack.decode(msgspec.msgpack.encode(raw)),raw)

Status=NS(WAITING_FOR_REMOTE_KVS='remote',is_finished=lambda s:s=='finished')
Scheduler=extract(ROOT/'scheduler.py','Scheduler',{'_update_requests_with_invalid_blocks','_update_from_kv_xfer_finished'},dict(RequestStatus=Status,logger=NS(debug=lambda *a:None)))
class SchedulerTests(unittest.TestCase):
    def scheduler(self, groups):
        s=Scheduler();s.kv_cache_manager=NS(get_block_ids=lambda rid:groups);return s
    def test_hybrid_any_group_failure_full_recompute(self):
        for bad in (11,21,31,41):
            s=self.scheduler(([11,12],[21],[31],[41]));r=NS(request_id='r',num_computed_tokens=16800)
            affected,tokens,evict=s._update_requests_with_invalid_blocks([r],{bad},{})
            self.assertEqual((affected,tokens,r.num_computed_tokens),({'r'},16800,0));self.assertEqual(evict,{11,12,21,31,41})
    def test_hybrid_async_no_evict(self):
        s=self.scheduler(([11],[21]));r=NS(request_id='r',num_computed_tokens=1600)
        self.assertEqual(s._update_requests_with_invalid_blocks([r],{21},{},False),({'r'},1600,set()))
    def test_hybrid_unaffected(self):
        s=self.scheduler(([11],[21]));r=NS(request_id='r',num_computed_tokens=1600)
        self.assertEqual(s._update_requests_with_invalid_blocks([r],{99},{}),(set(),0,set()));self.assertEqual(r.num_computed_tokens,1600)
    def test_single_group_preserves_valid_prefix(self):
        s=self.scheduler(([11,12,13],));s.block_size=800;r=NS(request_id='r',num_computed_tokens=2400)
        self.assertEqual(s._update_requests_with_invalid_blocks([r],{12},{}),({'r'},1600,{12,13}));self.assertEqual(r.num_computed_tokens,800)
    def test_stale_duplicate_and_finished_completions(self):
        s=Scheduler();s.connector=None;s.finished_recving_kv_req_ids=set();freed=[];s._free_blocks=lambda r:freed.append(r)
        active=NS(status='running');done=NS(status='finished');waiting=NS(status='remote');s.requests={'a':active,'d':done,'w':waiting}
        s._update_from_kv_xfer_finished(NS(finished_recving={'gone','a','d','w'},finished_sending={'gone','a'}))
        self.assertEqual(s.finished_recving_kv_req_ids,{'w'});self.assertEqual(freed,[done])
if __name__=='__main__':unittest.main(verbosity=2)
