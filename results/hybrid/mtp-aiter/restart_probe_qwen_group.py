import urllib.request,json,time,pathlib,sys
base='http://192.168.1.106:8092';out=pathlib.Path('/tmp/lmcache-mi210-mtp-20261015');phase=sys.argv[1]
questions=[('A','17 times 19','323'),('B','144 divided by 12','12'),('C','37 plus 58','95'),('D','9 times 8','72')]
results=[]
for tag,question,answer in questions:
 prefix='External-cache restart validation qwen-group-v2 '+tag+'.\n'+''.join(f'Record {i:04d}: the box contains blue tiles; this is reference material only.\n' for i in range(200))
 payload={'model':'qwen38-swift-w8a8','messages':[{'role':'user','content':prefix+f'\nIgnore the records for the calculation. What is {question}? Reply only with the integer.'}],'max_tokens':32,'temperature':0,'seed':42,'chat_template_kwargs':{'enable_thinking':False},'kv_transfer_params':{'cached_token_stats':True}}
 req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 start=time.monotonic()
 with urllib.request.urlopen(req,timeout=240) as r: result=json.load(r)
 row={'phase':phase,'tag':tag,'elapsed_seconds':time.monotonic()-start,'expected':answer,'response':result};results.append(row)
 (out/('qwen-group-restart-'+phase+'.json')).write_text(json.dumps(results,indent=2))
 print(tag,'elapsed',round(row['elapsed_seconds'],3),'choice',result.get('choices'),'usage',result.get('usage'),'kv',result.get('kv_transfer_params'),flush=True)
 assert result['choices'][0]['message']['content'].strip()==answer
 assert result['choices'][0]['finish_reason']=='stop'
 time.sleep(2)
print('PASSED',phase,len(results),flush=True)
