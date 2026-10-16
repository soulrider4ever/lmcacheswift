import json, re, time, urllib.request, statistics
base='http://127.0.0.1:8092'
def get(path):
    with urllib.request.urlopen(base+path, timeout=10) as r:
        return r.status, r.read()
status, _ = get('/health')
assert status == 200, status
status, raw = get('/v1/models')
models=json.loads(raw)['data']
assert any(m.get('id')=='qwen38-swift-w8a8' for m in models), [m.get('id') for m in models]
metric_names=['vllm:request_decode_time_seconds_sum','vllm:request_decode_time_seconds_count','vllm:spec_decode_num_draft_tokens_total','vllm:spec_decode_num_accepted_tokens_total']
def metrics():
    _, body=get('/metrics')
    text=body.decode()
    out={}
    for name in metric_names:
        vals=[]
        for line in text.splitlines():
            if line.startswith(name+'{') or line.startswith(name+' '):
                try: vals.append(float(line.split()[-1]))
                except ValueError: pass
        out[name]=sum(vals)
    return out
payload={'model':'qwen38-swift-w8a8','messages':[{'role':'user','content':'Count from 1 through 30 inclusive, in order, separated by commas. Output nothing else.'}], 'max_tokens':128,'temperature':0,'seed':42,'chat_template_kwargs':{'enable_thinking':False}}
def run(label):
    before=metrics()
    req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    t=time.monotonic()
    with urllib.request.urlopen(req,timeout=90) as r: result=json.load(r)
    wall=time.monotonic()-t
    after=metrics()
    delta={k:after[k]-v for k,v in before.items()}
    content=result['choices'][0]['message']['content']
    seq=list(map(int,re.findall(r'\d+',content)))
    assert seq==list(range(1,31)), {'label':label,'seq':seq,'content':content}
    assert result['choices'][0]['finish_reason']=='stop', result['choices'][0]['finish_reason']
    assert delta[metric_names[1]]==1, {'label':label,'metric_delta':delta,'note':'other concurrent traffic can contaminate metrics'}
    completion=result['usage']['completion_tokens']
    decode=delta[metric_names[0]]
    return {'label':label,'wall_s':round(wall,3),'completion_tokens':completion,'wall_tok_s':round(completion/wall,2),'server_decode_tok_s':round((completion-1)/decode,2) if decode>0 else None,'mtp_accepted':int(delta[metric_names[3]]),'mtp_proposed':int(delta[metric_names[2]])}
rows=[]
rows.append(run('warmup'))
for i in range(1,4): rows.append(run(f'measured-{i}'))
measured=rows[1:]
print(json.dumps({'health':'HTTP 200','served_model':'qwen38-swift-w8a8','correctness':'exact count 1..30; stop','requests':rows,'median_server_decode_tok_s':round(statistics.median(r['server_decode_tok_s'] for r in measured),2),'median_wall_s':round(statistics.median(r['wall_s'] for r in measured),3)},indent=2))
