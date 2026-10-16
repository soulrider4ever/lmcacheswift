"""Three bounded deterministic decode requests with per-request server metrics."""
import json
import pathlib
import re
import statistics
import sys
import time
import urllib.request

base='http://127.0.0.1:8092'
root=pathlib.Path('/home/ubuntu/lmcache-integration-20261015')
phase=sys.argv[1]

def metrics():
 with urllib.request.urlopen(base+'/metrics',timeout=10) as r: text=r.read().decode()
 wanted=('vllm:request_decode_time_seconds_sum','vllm:request_decode_time_seconds_count','vllm:spec_decode_num_draft_tokens_total','vllm:spec_decode_num_accepted_tokens_total')
 return {name:sum(float(line.split()[-1]) for line in text.splitlines() if line.startswith(name+'{')) for name in wanted}

rows=[]
for index in range(3):
 before=metrics()
 payload={'model':'qwen38-swift-w8a8','messages':[{'role':'user','content':'Count from 1 through 100 inclusive, in order, separated by commas. Output nothing else.'}],'max_tokens':512,'temperature':0,'seed':42,'chat_template_kwargs':{'enable_thinking':False}}
 req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 started=time.monotonic()
 with urllib.request.urlopen(req,timeout=120) as r: result=json.load(r)
 elapsed=time.monotonic()-started
 after=metrics();delta={k:after[k]-v for k,v in before.items()}
 assert list(map(int,re.findall(r'\d+',result['choices'][0]['message']['content'])))==list(range(1,101))
 assert result['choices'][0]['finish_reason']=='stop'
 assert delta['vllm:request_decode_time_seconds_count']==1,delta
 tokens=result['usage']['completion_tokens']
 seconds=delta['vllm:request_decode_time_seconds_sum']
 row={'index':index,'elapsed_seconds':elapsed,'decode_tokens_per_second':(tokens-1)/seconds,'metric_delta':delta,'response':result};rows.append(row)
 (root/('decode-count-'+phase+'.json')).write_text(json.dumps(rows,indent=2))
 print('decode-count',phase,index,round(row['decode_tokens_per_second'],3),result['usage'],delta,flush=True)
print('decode-count median',phase,statistics.median(r['decode_tokens_per_second'] for r in rows),flush=True)
