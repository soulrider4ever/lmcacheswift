import ast,threading,unittest,time
from pathlib import Path
from types import SimpleNamespace as NS
from concurrent.futures import Future,ThreadPoolExecutor
import torch
scope=dict(MessagingFuture=Future,torch=torch,_get_kv_device=lambda _:None,synchronize_device=lambda _:None,logger=__import__('logging').getLogger('test'))
tree=ast.parse((Path(__file__).resolve().parents[1]/'overlay/live/transfer_context/async_engine_driven.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));cls.bases=[];cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_snapshot_and_commit_hybrid'];exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'test','exec'),scope)
C=scope['AsyncEngineDrivenTransferContext']
class Tests(unittest.TestCase):
 def setUp(self):
  self.c=C();c=self.c;c._is_closing=False;c._hybrid_commit_slots=threading.BoundedSemaphore(2);c._commit_lock=threading.Lock();c._commit_executor=ThreadPoolExecutor(2);c._instance_id=1;c._layout_hints={};c._engine_type=None;c._group_states=[NS(blocks_in_chunk=1,layout_desc=NS(shapes=[(2,)],dtypes=[torch.float32]),layer_names=['x'],engine_kv_format=None,blocks_per_window=1)]*2
  self.source=torch.tensor([1.,2.]);scope['gather_paged_kv_to_cpu']=lambda *a,**kw:[self.source];self.gate=threading.Event();self.payloads=[]
  def commit(*args):self.gate.wait(4);self.payloads.append(args[-1]);return True
  c._engine_driven_context=NS(prepare_store=lambda *a:None,commit_store=commit)
 def tearDown(self):self.gate.set();self.c._commit_executor.shutdown(wait=True)
 def call(self):return self.c._snapshot_and_commit_hybrid(None,{'x':self.source},[[1],[2]],NS(wait=lambda:None))
 def test_nonblocking_and_snapshot_owned(self):
  t=time.monotonic();f=self.call();self.assertLess(time.monotonic()-t,.5);self.assertFalse(f.done());self.source.fill_(9);self.gate.set();self.assertTrue(f.result(3));self.assertEqual(self.payloads[0][0][0].tolist(),[1.,2.]);self.assertEqual(len(self.payloads[0]),2)
 def test_saturation_drops_without_blocking_and_recovers(self):
  a=self.call();b=self.call();self.assertFalse(self.call().result(.1));self.gate.set();self.assertTrue(a.result(3));self.assertTrue(b.result(3));self.assertTrue(self.call().result(3))
 def test_error_releases_slots(self):
  self.c._engine_driven_context.prepare_store=lambda *a:(_ for _ in ()).throw(ValueError());self.assertFalse(self.call().result(3));self.assertFalse(self.call().result(3));self.assertFalse(self.call().result(3));self.assertTrue(self.c._hybrid_commit_slots.acquire(False))
 def test_oversize_skips_before_gather(self):
  self.c._group_states[0].layout_desc.shapes=[(1024**3,)];self.assertFalse(self.call().result(.1));self.assertTrue(self.c._hybrid_commit_slots.acquire(False))
 def test_closing_skips(self):
  self.c._is_closing=True;self.assertFalse(self.call().result(.1))
if __name__=='__main__':unittest.main()
