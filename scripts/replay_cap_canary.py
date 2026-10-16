"""Assert local/remote token provenance before and after vLLM-only restart."""
import json
import pathlib
import statistics
import sys
import time
import urllib.request

root=pathlib.Path('/home/ubuntu/lmcache-integration-20261015')
phases=('cold','repeat') if sys.argv[1]=='initial' else ('post_restart','repeat_after_restart')
questions=[('A','17 times 19','323'),('B','144 divided by 12','12'),('C','37 plus 58','95'),('D','9 times 8','72'),('E','prefix retrieval','VIOLET_LANTERN_7391')]
results=[]
for phase in phases:
 for tag,question,answer in questions:
  prefix='Lookup replay experiment 20261016 fresh03 '+tag+'.\n'+''.join(f'Record {i:04d}: the box contains blue tiles; this is reference material only.\n' for i in range(200))
  if tag=='E':
   prefix='The exact fictional retrieval phrase is VIOLET_LANTERN_7391.\n'+prefix
  suffix=f'\nIgnore the records for the calculation. What is {question}? Reply only with the integer.' if tag!='E' else '\nReply only with the exact fictional retrieval phrase given at the beginning.'
  payload={'model':'qwen38-swift-w8a8','messages':[{'role':'user','content':prefix+suffix}],'max_tokens':32,'temperature':0,'seed':42,'chat_template_kwargs':{'enable_thinking':False},'kv_transfer_params':{'cached_token_stats':True}}
  req=urllib.request.Request('http://127.0.0.1:8092/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  start=time.monotonic()
  with urllib.request.urlopen(req,timeout=240) as response: result=json.load(response)
  row={'phase':phase,'tag':tag,'elapsed_seconds':time.monotonic()-start,'expected':answer,'response':result};results.append(row)
  (root/('replay-cap-'+sys.argv[1]+'.json')).write_text(json.dumps(results,indent=2))
  assert result['choices'][0]['message']['content'].strip()==answer
  assert result['choices'][0]['finish_reason']=='stop'
  stats=result['kv_transfer_params']['cached_token_stats']
  boundary=(result['usage']['prompt_tokens']-1)//800*800-800
  local=boundary if phase in ('repeat','repeat_after_restart') else 0
  extra=boundary if phase=='post_restart' else 0
  print(phase,tag,round(row['elapsed_seconds'],3),stats,flush=True)
  assert stats['num_vllm_cached_tokens']==local,(phase,stats,local)
  assert stats['num_lmcache_extra_cached_tokens']==extra,(phase,stats,extra)
  if phase=='cold': assert stats['num_lmcache_cached_tokens']==0
  time.sleep(1)
 print('median',phase,statistics.median(r['elapsed_seconds'] for r in results if r['phase']==phase),flush=True)
print('PASSED',sys.argv[1],len(results),flush=True)
