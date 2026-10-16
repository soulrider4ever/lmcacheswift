import urllib.request,json,pathlib,base64,struct,zlib,concurrent.futures
base='http://192.168.1.106:8092'
out=pathlib.Path('/tmp/lmcache-mi210-mtp-20261015')
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
(out/'canaries.json').write_text(json.dumps(results,indent=2)); print('PASSED text, vision, tool, eight simultaneous short requests',flush=True)
print('vision',results['vision']['choices'][0]['message']['content'],'tool',tc,flush=True)
