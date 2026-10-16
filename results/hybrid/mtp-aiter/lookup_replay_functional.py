import urllib.request,json,pathlib,base64,struct,zlib,concurrent.futures
base='http://127.0.0.1:8092'
out=pathlib.Path('/home/ubuntu/lmcache-integration-20261015')
def call(p):
 payload={'model':'qwen38-swift-w8a8','max_tokens':96,'temperature':0,'seed':42,'chat_template_kwargs':{'enable_thinking':False},**p}
 with urllib.request.urlopen(urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=180) as r:return json.load(r)
def chunk(t,b):return struct.pack('!I',len(b))+t+b+struct.pack('!I',zlib.crc32(t+b)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',64,64,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+b'\xff\x00\x00'*64)*64))+chunk(b'IEND',b'')
results={}
results['text']=call({'messages':[{'role':'user','content':'What is 17 times 19? Reply only with the integer.'}]})
assert results['text']['choices'][0]['message']['content'].strip()=='323'
results['vision']=call({'messages':[{'role':'user','content':[{'type':'text','text':'Name the color in this image. Reply one word.'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(png).decode()}}]}]})
assert 'red' in results['vision']['choices'][0]['message']['content'].lower()
results['tool']=call({'messages':[{'role':'user','content':'Call ready_check with status set to ok.'}],'tools':[{'type':'function','function':{'name':'ready_check','description':'Report readiness','parameters':{'type':'object','properties':{'status':{'type':'string','enum':['ok']}},'required':['status'],'additionalProperties':False}}}],'tool_choice':'required'})
tc=results['tool']['choices'][0]['message']['tool_calls'][0]['function']; assert tc['name']=='ready_check' and json.loads(tc['arguments'])=={'status':'ok'}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 results['concurrent8']=list(pool.map(lambda i:call({'messages':[{'role':'user','content':f'Request {i}: What is 17 times 19? Reply only with the integer.'}]}),range(8)))
assert all(r['choices'][0]['message']['content'].strip()=='323' and r['choices'][0]['finish_reason']=='stop' for r in results['concurrent8'])
(out/'lookup-replay-functional-canaries.json').write_text(json.dumps(results,indent=2)); print('PASSED text, vision, tool, eight simultaneous short requests',flush=True)
print('vision',results['vision']['choices'][0]['message']['content'],'tool',tc,flush=True)
# A separate, longer fresh prompt checks shifted-boundary retention beyond 4K.
import time, re
prefix='Lookup replay longer boundary 20261016 fresh02.\n'+''.join(f'Record {i:04d}: the box contains blue tiles; this is reference material only.\n' for i in range(800))
payload={'messages':[{'role':'user','content':prefix+'\nWhat is 17 times 19? Reply only with the integer.'}], 'max_tokens':32, 'kv_transfer_params':{'cached_token_stats':True}}
results['longer']=[]
for phase in ('cold','repeat'):
 t=time.monotonic();result=call(payload)
 assert result['choices'][0]['message']['content'].strip()=='323'
 row={'phase':phase,'elapsed_seconds':time.monotonic()-t,'response':result}
 results['longer'].append(row)
 print('longer',phase,round(row['elapsed_seconds'],3),result.get('usage'),result.get('kv_transfer_params'),flush=True)
 if phase=='repeat':
  stats=result['kv_transfer_params']['cached_token_stats']
  expected=(result['usage']['prompt_tokens']-1)//800*800-800
  assert stats['num_vllm_cached_tokens']==expected,(stats,expected)
results['counting']=call({'messages':[{'role':'user','content':'Count from 1 through 100 inclusive, in order, separated by commas. Output nothing else.'}],'max_tokens':512})
content=results['counting']['choices'][0]['message']['content']
assert list(map(int,re.findall(r'\d+',content)))==list(range(1,101)),content
assert results['counting']['choices'][0]['finish_reason']=='stop'
(out/'lookup-replay-functional-canaries.json').write_text(json.dumps(results,indent=2))
print('PASSED longer cold/repeat exact shifted local boundary; counting 1-100',flush=True)
# Put the image BEFORE the long common text so a local prefix hit includes
# image-conditioned KV. Distinct image bytes must not alias across requests.
blue_png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',64,64,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+b'\x00\x00\xff'*64)*64))+chunk(b'IEND',b'')
image_prefix='Image KV identity experiment 20261016 unique02.\n'+''.join(f'Record {i:04d}: this entry is neutral reference material for caching.\n' for i in range(220))
results['image_kv']=[]
for color,picture in [('red',png),('blue',blue_png)]:
 for phase in ('cold','repeat'):
  payload={'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(picture).decode()}},{'type':'text','text':image_prefix+'\nIgnore the records. Name the solid color of the image. Reply one word.'}]}], 'max_tokens':16,'kv_transfer_params':{'cached_token_stats':True}}
  started=time.monotonic();result=call(payload)
  row={'color':color,'phase':phase,'elapsed_seconds':time.monotonic()-started,'response':result};results['image_kv'].append(row)
  (out/'lookup-replay-functional-canaries.json').write_text(json.dumps(results,indent=2))
  text=result['choices'][0]['message']['content'].strip().lower()
  print('image-kv',color,phase,round(row['elapsed_seconds'],3),text,result.get('kv_transfer_params'),flush=True)
  assert color in text,(color,phase,text)
  if phase=='repeat': assert result['kv_transfer_params']['cached_token_stats']['num_vllm_cached_tokens']>0
print('PASSED red/blue image-conditioned KV reuse and separation',flush=True)
