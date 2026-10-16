import urllib.request,json,time,concurrent.futures,pathlib
base='http://127.0.0.1:8092'
pathlib.Path('/tmp/mi210-latency-fix').mkdir(exist_ok=True)
prefix='Latency repair 20261016-v1. Secret phrase: silver compass.\n'+''.join(f'Record {i:04d}: the box contains blue tiles; this is reference material only.\n' for i in range(1000))
payload={'model':'qwen38-swift-w8a8','messages':[{'role':'user','content':prefix+'\nWhat is the secret phrase? Reply with that phrase only.'}],'max_tokens':32,'temperature':0,'chat_template_kwargs':{'enable_thinking':False},'kv_transfer_params':{'cached_token_stats':True}}
def run(label,p):
 t=time.monotonic();req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=240) as r:d=json.load(r)
 row={'label':label,'seconds':time.monotonic()-t,'result':d};pathlib.Path('/tmp/mi210-latency-fix/'+label+'.json').write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True);return d
import sys
phase=sys.argv[1]
if phase=='cold':
 with concurrent.futures.ThreadPoolExecutor(2) as pool:
  long=pool.submit(run,'cold',payload);time.sleep(2)
  short=dict(payload,messages=[{'role':'user','content':'What is 17 times 19? Reply with the number only.'}])
  a=pool.submit(run,'concurrent_short',short);d=long.result();s=a.result();assert s['choices'][0]['message']['content'].strip()=='323'
else:d=run(phase,payload)
assert d['choices'][0]['message']['content'].strip().lower()=='silver compass'
assert d['choices'][0]['finish_reason']=='stop'
run(phase+'_repeat',payload)
