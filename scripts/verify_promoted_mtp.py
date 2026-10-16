"""Bounded post-promotion API/runtime/correctness/cache provenance checks."""
import base64,json,pathlib,re,struct,subprocess,time,urllib.request,zlib
root=pathlib.Path('/home/ubuntu/lmcache-integration-20261015')
base='http://127.0.0.1:8092'
name='qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015'
rollback='qwen38-swift-w8a8-lmcache-layout-20261015'
for attempt in range(180):
 try:
  with urllib.request.urlopen(base+'/health',timeout=2) as r: assert r.status==200
  break
 except Exception: time.sleep(2)
else: raise RuntimeError('MTP readiness deadline exceeded')

def inspect(n): return json.loads(subprocess.check_output(['docker','inspect',n]))[0]
def call(content,**extra):
 p={'model':'qwen38-swift-w8a8','messages':[{'role':'user','content':content}],'max_tokens':32,'temperature':0,'seed':42,'chat_template_kwargs':{'enable_thinking':False},**extra}
 started=time.monotonic()
 with urllib.request.urlopen(urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'}),timeout=180) as r: result=json.load(r)
 return {'elapsed_seconds':time.monotonic()-started,'response':result}

with urllib.request.urlopen(base+'/v1/models',timeout=10) as r: models=json.load(r)
assert models['data'][0]['id']=='qwen38-swift-w8a8'
assert models['data'][0]['max_model_len']==262144,models
c=inspect(name);cmd=c['Config']['Cmd']
assert c['HostConfig']['RestartPolicy']['Name']=='unless-stopped'
assert json.loads(cmd[cmd.index('--speculative-config')+1])=={'method':'mtp','num_speculative_tokens':3}
assert cmd[cmd.index('--attention-backend')+1]=='ROCM_AITER_FA'
kv=json.loads(cmd[cmd.index('--kv-transfer-config')+1]);extra=kv['kv_connector_extra_config']
assert extra['lmcache.mp.port']==5556 and extra['lmcache.mp.lookup_replay_tokens']==800
actual=subprocess.check_output(['docker','exec',name,'cat','/proc/1/cmdline']).decode().split('\0')
assert '--speculative-config' in actual and '--attention-backend' in actual
results={'models':models,'checks':{}}
results['checks']['text']=call('What is 17 times 19? Reply only with the integer.')
assert results['checks']['text']['response']['choices'][0]['message']['content'].strip()=='323'
results['checks']['tool']=call('Call ready_check with status set to ok.',tools=[{'type':'function','function':{'name':'ready_check','description':'Report readiness','parameters':{'type':'object','properties':{'status':{'type':'string','enum':['ok']}},'required':['status'],'additionalProperties':False}}}],tool_choice='required')
f=results['checks']['tool']['response']['choices'][0]['message']['tool_calls'][0]['function'];assert f['name']=='ready_check' and json.loads(f['arguments'])=={'status':'ok'}
def chunk(t,b):return struct.pack('!I',len(b))+t+b+struct.pack('!I',zlib.crc32(t+b)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',64,64,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+b'\xff\x00\x00'*64)*64))+chunk(b'IEND',b'')
results['checks']['vision']=call([{'type':'text','text':'Name the color in the image. Reply one word.'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(png).decode()}}])
assert 'red' in results['checks']['vision']['response']['choices'][0]['message']['content'].lower()
prefix='Post-promotion prefix verification 20261016. Fictional retrieval phrase: VIOLET_LANTERN_9462.\n'+''.join(f'Record {i:04d}: the box contains blue tiles; this is reference material only.\n' for i in range(200))+'\nReply only with the exact fictional retrieval phrase given at the beginning.'
for phase in ('cold','repeat'):
 row=call(prefix,kv_transfer_params={'cached_token_stats':True});results['checks']['prefix_'+phase]=row
 r=row['response'];assert r['choices'][0]['message']['content'].strip()=='VIOLET_LANTERN_9462'
 stats=r['kv_transfer_params']['cached_token_stats']
 if phase=='cold': assert stats['num_vllm_cached_tokens']==0 and stats['num_lmcache_cached_tokens']==0
 else:
  expected=(r['usage']['prompt_tokens']-1)//800*800-800
  assert stats['num_vllm_cached_tokens']==expected and stats['num_lmcache_extra_cached_tokens']==0,stats
 print('promotion prefix',phase,round(row['elapsed_seconds'],3),stats,flush=True)
results['checks']['counting']=call('Count from 1 through 30 inclusive, separated by commas. Output nothing else.',max_tokens=256)
r=results['checks']['counting']['response'];assert list(map(int,re.findall(r'\d+',r['choices'][0]['message']['content'])))==list(range(1,31)) and r['choices'][0]['finish_reason']=='stop'
with urllib.request.urlopen(base+'/metrics',timeout=10) as r: metrics=r.read().decode()
spec={key:sum(float(line.split()[-1]) for line in metrics.splitlines() if line.startswith(key+'{')) for key in ('vllm:spec_decode_num_draft_tokens_total','vllm:spec_decode_num_accepted_tokens_total')}
assert all(v>0 for v in spec.values()),spec
results['speculation_metrics']=spec
for key,n in [('active',name),('rollback',rollback)]:
 x=inspect(n);results[key]={'name':n,'image':x['Image'],'status':x['State']['Status'],'restart':x['HostConfig']['RestartPolicy']['Name'],'oom':x['State']['OOMKilled'],'automatic_restarts':x['RestartCount']}
assert results['active']['status']=='running' and not results['active']['oom'] and results['active']['automatic_restarts']==0
assert results['rollback']['status']=='exited' and results['rollback']['restart']=='no'
ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
owners=[]
for container_id in ids:
 x=inspect(container_id);cmd=x['Config']['Cmd'] or []
 ports=x['HostConfig'].get('PortBindings') or {}
 if ('--port' in cmd and cmd[cmd.index('--port')+1]=='8092') or any(v.get('HostPort')=='8092' for bindings in ports.values() for v in (bindings or [])):
  owners.append(x['Name'].lstrip('/'))
assert owners==[name],owners
results['port_8092_owners']=owners
with urllib.request.urlopen(base+'/health',timeout=5) as r: assert r.status==200
(root/'promotion-verification.json').write_text(json.dumps(results,indent=2)+'\n')
print('PROMOTED_MTP_VERIFIED',results['active'],spec,flush=True)
