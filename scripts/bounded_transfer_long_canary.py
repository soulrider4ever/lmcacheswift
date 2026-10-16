import json,pathlib,time,urllib.request,sys
phase=sys.argv[1]
base='http://127.0.0.1:8092'
prefix='Bounded transfer regression 20261016 v1. Secret test phrase: copper lantern.\n'+''.join(f'Record {i:04d}: the box contains blue tiles; this is reference material only.\n' for i in range(1000))
payload={'model':'qwen38-swift-w8a8','messages':[{'role':'user','content':prefix+'\nWhat is the secret test phrase from the first line? Reply with that phrase only.'}],'max_tokens':32,'temperature':0,'seed':42,'chat_template_kwargs':{'enable_thinking':False},'kv_transfer_params':{'cached_token_stats':True}}
for label in [phase,phase+'_repeat']:
    req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    start=time.monotonic()
    with urllib.request.urlopen(req,timeout=240) as r:result=json.load(r)
    row={'label':label,'seconds':time.monotonic()-start,'result':result}
    path=pathlib.Path('/tmp/mi210-transfer-fix/long-canary-'+label+'.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(row,indent=2))
    print(json.dumps(row),flush=True)
    assert result['choices'][0]['message']['content'].strip().lower()=='copper lantern', result['choices']
    assert result['choices'][0]['finish_reason']=='stop'
    assert result['usage']['prompt_tokens']>16800
    if label == 'external':
        stats=result['kv_transfer_params']['cached_token_stats']
        assert stats['num_vllm_cached_tokens']==0
        assert stats['num_lmcache_extra_cached_tokens']>16800
    time.sleep(3)
