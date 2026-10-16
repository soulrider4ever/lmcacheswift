#!/usr/bin/env python3
"""Canonical speed run on the unchanged live MI210 AITER FA/MTP3/40GiB LMCache stack. Inference only; does not restart or tune services."""
import datetime as dt
import hashlib
import json
import math
import re
import shlex
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parent
BASE = 'http://192.168.1.106:8092'
MODEL = 'qwen38-swift-w8a8'
HF_ID = 'rovangju/Swift-Qwen3.8-27b-W8A8'
REV = 'bf37ab853e8dafbd531dee9cb6d0fbe813b69873'
MTP_WIDTH = 3
PROMPT = '''You are helping a small robotics club plan a weekend build. Work through each part carefully and show your reasoning.

1. The club has 7 members and a budget of 412 dollars. A motor driver costs 18.50, a microcontroller 23.75, and each member wants one of each plus a shared 3D-printer spool at 27.90. After buying everything, they split the remainder evenly on batteries priced at 6.35 each. How many batteries can they buy in total, and how much money is left over?

2. Two members disagree about wheel size. Alice says a larger wheel gives more torque at the ground; Ben says it gives more speed. Explain who is right, what tradeoff is actually involved, and how gear ratio changes the answer.

3. Write a short, plain-English procedure (six to nine steps) for safely testing a new motor circuit for the first time, including what to check before applying power.

4. Finally, propose one creative feature for the robot that would be unusual for a club project, and give two concrete risks with how you would mitigate each.

Answer all four parts in order with clear headings.'''
PROMPT_SHA = '9000edaadb16fc77ab78b39917245a03d4d7585c3ba770cb045a47a0e0683445'
METRIC_LINE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+([-+0-9.eE]+)\s*$')
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"])*)"')
COUNTERS = {
    'prefill_count': 'vllm:request_prefill_time_seconds_count',
    'prefill_sum_s': 'vllm:request_prefill_time_seconds_sum',
    'decode_count': 'vllm:request_decode_time_seconds_count',
    'decode_sum_s': 'vllm:request_decode_time_seconds_sum',
    'ttft_count': 'vllm:time_to_first_token_seconds_count',
    'ttft_sum_s': 'vllm:time_to_first_token_seconds_sum',
    'prompt_tokens': 'vllm:request_prompt_tokens_sum',
    'completion_tokens': 'vllm:request_generation_tokens_sum',
    'spec_drafts': 'vllm:spec_decode_num_draft_tokens_total',
    'spec_accepted': 'vllm:spec_decode_num_accepted_tokens_total',
    'prefix_hit_tokens': 'vllm:prefix_cache_hits_total',
    'prefix_query_tokens': 'vllm:prefix_cache_queries_total',
    'requests_running': 'vllm:num_requests_running',
    'requests_waiting': 'vllm:num_requests_waiting',
}

def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def http(path, payload=None, timeout=600):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    headers = {'Accept': 'application/json', 'User-Agent': 'LocalMaxxing-canonical-speed-run/1.0'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(BASE + path, data=data, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except HTTPError as e:
        return e.code, e.read()

def parse_metrics():
    status, body = http('/metrics', timeout=20)
    if status != 200:
        raise RuntimeError(f'/metrics HTTP {status}: {body[:500]!r}')
    result = {}
    for line in body.decode('utf-8', 'replace').splitlines():
        m = METRIC_LINE.match(line)
        if not m:
            continue
        name, label_text, number = m.groups()
        labels = {}
        if label_text:
            labels = {k: bytes(v, 'utf-8').decode('unicode_escape') for k, v in LABEL.findall(label_text)}
        result.setdefault(name, []).append((labels, float(number)))
    return result

def series_sum(data, name):
    rows = data.get(name, [])
    matching = [(labels, value) for labels, value in rows if labels.get('model_name') == MODEL]
    return sum(value for _, value in (matching or rows))

def metric_snapshot(data):
    return {k: series_sum(data, metric) for k, metric in COUNTERS.items()}

def wait_metrics(before):
    deadline = time.monotonic() + 5
    after = parse_metrics()
    while time.monotonic() < deadline:
        d = metric_snapshot(after)
        if d['prefill_count'] >= before['prefill_count'] + 1 and d['ttft_count'] >= before['ttft_count'] + 1:
            return after
        time.sleep(0.2)
        after = parse_metrics()
    return after

def stream_request(label, out_path):
    before_raw = parse_metrics()
    before = metric_snapshot(before_raw)
    if before['requests_running'] != 0 or before['requests_waiting'] != 0:
        raise RuntimeError(f'{label}: endpoint not idle before request: running={before["requests_running"]}, waiting={before["requests_waiting"]}')
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': PROMPT}],
        'temperature': 0,
        'top_p': 1,
        'seed': 42,
        'max_tokens': 1024,
        'min_tokens': 256,
        'chat_template_kwargs': {'enable_thinking': False},
        'stream': True,
        'stream_options': {'include_usage': True},
    }
    start_iso = now_iso()
    t0 = time.perf_counter()
    req = Request(BASE + '/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream', 'User-Agent': 'LocalMaxxing-canonical-speed-run/1.0'})
    chunks = []
    usage = None
    finish = None
    first_token_s = None
    status = None
    try:
        with urlopen(req, timeout=600) as response:
            status = response.status
            for raw in response:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                event_text = line[5:].strip()
                if event_text == '[DONE]':
                    break
                try:
                    event = json.loads(event_text)
                except json.JSONDecodeError:
                    continue
                if event.get('usage') is not None:
                    usage = event['usage']
                for choice in event.get('choices') or []:
                    delta = choice.get('delta') or {}
                    for key in ('reasoning_content', 'reasoning', 'content'):
                        value = delta.get(key)
                        if isinstance(value, str) and value:
                            if first_token_s is None:
                                first_token_s = time.perf_counter() - t0
                            chunks.append({'channel': key, 'text': value})
                    if choice.get('finish_reason') is not None:
                        finish = choice['finish_reason']
    except HTTPError as e:
        raise RuntimeError(f'{label}: inference HTTP {e.code}: {e.read()[:1200]!r}')
    wall_s = time.perf_counter() - t0
    if status != 200 or usage is None:
        raise RuntimeError(f'{label}: stream missing HTTP success or terminal usage; status={status}, usage={usage}')
    full_text = ''.join(x['text'] for x in chunks)
    if not full_text.strip():
        raise RuntimeError(f'{label}: empty generated text')
    out_path.write_text(full_text, encoding='utf-8')
    after_raw = wait_metrics(before)
    after = metric_snapshot(after_raw)
    delta = {k: after[k] - before[k] for k in COUNTERS}
    for k in ('prefill_count', 'decode_count', 'ttft_count'):
        if delta[k] != 1:
            raise RuntimeError(f'{label}: expected one authoritative {k} sample, got delta={delta}')
    prompt_tokens = int(usage['prompt_tokens'])
    completion_tokens = int(usage['completion_tokens'])
    if prompt_tokens != int(round(delta['prompt_tokens'])) or completion_tokens != int(round(delta['completion_tokens'])):
        raise RuntimeError(f'{label}: usage/Prometheus token mismatch usage={usage}, deltas={delta}')
    cached = usage.get('prompt_tokens_details', {}).get('cached_tokens')
    if cached is None:
        cached = int(round(delta['prefix_hit_tokens']))
    cached = int(cached)
    if cached != int(round(delta['prefix_hit_tokens'])):
        raise RuntimeError(f'{label}: cached-token usage/Prometheus mismatch cached={cached}, hitDelta={delta["prefix_hit_tokens"]}')
    prefill_s = delta['prefill_sum_s']
    decode_s = delta['decode_sum_s'] / delta['decode_count']
    ttft_s = delta['ttft_sum_s'] / delta['ttft_count']
    if min(prefill_s, decode_s, ttft_s) <= 0:
        raise RuntimeError(f'{label}: non-positive server timing deltas: {delta}')
    if delta['requests_running'] != 0 or delta['requests_waiting'] != 0:
        raise RuntimeError(f'{label}: endpoint not idle after request: running={delta["requests_running"]}, waiting={delta["requests_waiting"]}')
    spec_drafts = int(round(delta['spec_drafts']))
    spec_accepted = int(round(delta['spec_accepted']))
    if spec_drafts <= 0 or spec_accepted < 0 or spec_accepted > spec_drafts:
        raise RuntimeError(f'{label}: invalid request-scoped MTP counters: {delta}')
    row = {
        'label': label,
        'startedAt': start_iso,
        'finishedAt': now_iso(),
        'httpStatus': status,
        'promptTokens': prompt_tokens,
        'completionTokens': completion_tokens,
        'cachedPromptTokens': cached,
        'finishReason': finish,
        'clientWallSeconds': wall_s,
        'clientTtftSeconds': first_token_s,
        'serverPrefillSeconds': prefill_s,
        'serverDecodeSeconds': decode_s,
        'serverTtftSeconds': ttft_s,
        'tokSPrefill': (prompt_tokens - cached) / prefill_s if prompt_tokens > cached else None,
        'tokSOut': (completion_tokens - 1) / decode_s,
        'tokSTotalClient': (prompt_tokens + completion_tokens) / wall_s,
        'specDraftTokens': spec_drafts,
        'specAcceptedTokens': spec_accepted,
        'specAcceptanceRate': spec_accepted / spec_drafts,
        'specMeanAcceptedLength': 1 + spec_accepted / (spec_drafts / MTP_WIDTH),
        'specTokenConsistencyDelta': completion_tokens - (spec_accepted + spec_drafts / MTP_WIDTH),
        'prefixCacheHitTokenDelta': delta['prefix_hit_tokens'],
        'prefixCacheQueryTokenDelta': delta['prefix_query_tokens'],
        'outputSha256': sha(full_text),
        'outputChars': len(full_text),
        'outputTextFile': out_path.name,
        'streamChannels': {k: sum(len(x['text']) for x in chunks if x['channel'] == k) for k in ('reasoning_content', 'reasoning', 'content')},
        'reasoningTokens': usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0),
        'terminalUsage': usage,
        'prometheusMetricDeltas': delta,
    }
    if delta['prefix_hit_tokens'] != 0:
        row['cacheNote'] = 'Prefix-cache hits observed; prefill rate uses fresh prompt tokens only.'
    return row

REMOTE_SAMPLER = r'''import datetime as dt,json,select,subprocess,sys,time
while True:
    began=time.monotonic()
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        p=subprocess.run(['amd-smi','metric','--mem-usage','--gpu','0','--json'],capture_output=True,text=True,timeout=12,check=True)
        d=json.loads(p.stdout)['gpu_data'][0]['mem_usage']
        row={'timestamp':stamp,'used_mb':d['used_vram']['value'],'free_mb':d['free_vram']['value'],'total_mb':d['total_vram']['value']}
    except Exception as e:
        row={'timestamp':stamp,'error':str(e)[:240]}
    print(json.dumps(row,separators=(',',':')),flush=True)
    delay=max(0.0,1.0-(time.monotonic()-began))
    ready,_,_=select.select([sys.stdin],[],[],delay)
    if ready:
        command=sys.stdin.readline().strip()
        if command in ('stop',''): break
'''

def start_gpu_sampler():
    remote = 'python3 -u -c ' + shlex.quote(REMOTE_SAMPLER)
    return subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=6','root@192.168.1.106',remote], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

def sample_objects(text):
    rows=[]
    for line in text.splitlines():
        try: rows.append(json.loads(line))
        except Exception: pass
    return rows

def build_payload(rows, gpu_samples):
    measured = rows[1:]
    ordered = sorted(measured, key=lambda r:r['tokSOut'])
    rep = ordered[len(ordered)//2]
    peak_mb = None
    try:
        t0=dt.datetime.fromisoformat(rep['startedAt']); t1=dt.datetime.fromisoformat(rep['finishedAt'])
        scoped=[s for s in gpu_samples if 'used_mb' in s and t0 <= dt.datetime.fromisoformat(s['timestamp']) <= t1]
        if scoped: peak_mb=max(s['used_mb'] for s in scoped)
    except Exception: scoped=[]
    if peak_mb is None:
        raise RuntimeError('No GPU memory samples within representative request')
    full_text=(OUT / rep['outputTextFile']).read_text(encoding='utf-8')
    output_sample=full_text if len(full_text)<=4000 else full_text[:3000]+'\n…\n'+full_text[-997:]
    outputs=[r['outputSha256'] for r in measured]
    live=json.loads((OUT/'live-container-preflight.json').read_text())
    engine_cmd=shlex.join(['vllm']+live['args'])
    engine_flags={
        'commandSnippet':engine_cmd,
        'tensorParallel':1,
        'concurrency':1,
        'maxRunningSeqs':8,
        'gpuMemUtil':0.99,
        'kvCacheDtype':'bf16',
        'prefixCaching':True,
        'chunkedPrefill':True,
        'prefillChunkSize':1567,
        'attentionBackend':'ROCM_AITER_FA',
        'specDecoding':True,
        'specMethod':'mtp',
        'specNumTokens':3,
        'mtpEnabled':True,
        'specDraftTokens':rep['specDraftTokens'],
        'specAcceptedTokens':rep['specAcceptedTokens'],
        'specAcceptanceRate':rep['specAcceptanceRate'],
        'specMeanAcceptedLength':rep['specMeanAcceptedLength'],
        'temperature':0,
        'topP':1,
        'extraFlags':('Canonical reasoning-v1; 1 warmup excluded + 3 measured serial requests; max_tokens=1024, min_tokens=256; thinking disabled; stream_options.include_usage; Prefix caching enabled; actual per-response hits recorded. Remote LMCache 40 GiB/chunk800; replay reserve800. Canonical prompt is shorter than one800-token block; no cache reset or service restart.')
    }
    engine_timings={
        'source':'vLLM Prometheus request histogram/counter deltas plus OpenAI-compatible streamed terminal usage',
        'decodeFormula':'(outputTokens-1)/serverDecodeSeconds',
        'warmupExcluded':True,
        'measurementCount':3,
        'representativeRun':rep['label'],
        'representativeServer':{k:rep[k] for k in ('serverPrefillSeconds','serverDecodeSeconds','serverTtftSeconds','tokSPrefill','tokSOut','tokSTotalClient','clientWallSeconds','clientTtftSeconds')},
        'terminalUsage':rep['terminalUsage'],
        'representativeRequestMtp':{k:rep[k] for k in ('specDraftTokens','specAcceptedTokens','specAcceptanceRate','specMeanAcceptedLength','specTokenConsistencyDelta')},
        'perRun':[{'label':r['label'],'promptTokens':r['promptTokens'],'completionTokens':r['completionTokens'],'tokSPrefill':r['tokSPrefill'],'tokSOut':r['tokSOut'],'tokSTotal':r['tokSTotalClient'],'ttftMs':r['serverTtftSeconds']*1000,'clientWallSeconds':r['clientWallSeconds'],'outputSha256':r['outputSha256'],'specDraftTokens':r['specDraftTokens'],'specAcceptedTokens':r['specAcceptedTokens'],'prefixCacheHitTokenDelta':r['prefixCacheHitTokenDelta']} for r in measured],
        'decodeRangeTokS':[min(r['tokSOut'] for r in measured),max(r['tokSOut'] for r in measured)],
        'outputHashesIdentical':len(set(outputs))==1,
        'measurementCacheHitTokens':[r['prefixCacheHitTokenDelta'] for r in measured],
    }
    notes=(
        'LocalMaxxing canonical reasoning-v1 prompt, exact canonical SHA-256; one warmup excluded and three measured serial requests, temperature 0/seed 42, thinking disabled. '
        '1024-token cap with 256-token minimum; representative fields and output are from the median-decode measured request. '
        'Per-request MTP counters are Prometheus before/after deltas; MTP width is fixed at 3. '
        'No nonce or cache reset: service benchmarked as deployed; canonical266-token prompt is below800-token cache geometry; observed hit deltas recorded. '
        'Peak VRAM is one-second AMD-SMI total-device used-VRAM sampling on the MI210 LXC; amd-smi process listing returned no processes, so memory is not process-attributed. '
        'Speed verification is not an answer-quality score.'
    )
    payload={
        'hfId':HF_ID,
        'modelRevision':REV,
        'hardware':{'hwClass':'DISCRETE_GPU','gpuName':'AMD Instinct MI210','gpuCount':1,'vramGb':64,'cpu':'Intel Xeon Platinum 8268','ramGb':100.93,'os':'Ubuntu 24.04.5 LTS'},
        'engineName':'vllm',
        'engineVersion':'0.1.dev1+g12dadcb41',
        'engineRepository':'https://github.com/davetha/vllm',
        'engineBuild':'Custom ROCm 10/gfx90a vLLM MTP build; image digest sha256:275f7b6b258fa87a2e22cf796ea9548bab78953ebe87ce45ff65eee1cd15bdef',
        'engineCommit':'12dadcb4134ab41cf99b60a22e1222b7479e1a58',
        'backend':'rocm',
        'quantization':'INT8_W8A8',
        'promptTokens':rep['promptTokens'],
        'outputTokens':rep['completionTokens'],
        'contextLength':262144,
        'batchSize':1,
        'prefillTokens':rep['cachedPromptTokens'],
        'ttftMs':rep['serverTtftSeconds']*1000,
        'tokSOut':rep['tokSOut'],
        'tokSPrefill':rep['tokSPrefill'],
        'tokSTotal':rep['tokSTotalClient'],
        'peakVramGb':peak_mb/1000 if peak_mb is not None else None,
        'notes':notes,
        'engineFlags':engine_flags,
        'promptSha256':PROMPT_SHA,
        'promptSample':PROMPT,
        'outputSha256':rep['outputSha256'],
        'outputSample':output_sample,
        'engineTimingsRaw':engine_timings,
    }
    if peak_mb is None: payload.pop('peakVramGb')
    result={
        'schema':'localmaxxing-mi210-swift-mtp3-canonical-v1',
        'createdAt':now_iso(),
        'benchmarkClass':'canonical LocalMaxxing speed test; reasoning-v1',
        'endpoint':BASE,
        'servedModelId':MODEL,
        'huggingFace':{'id':HF_ID,'revision':REV,'public':True,'registrySearchMatches':0},
        'runtime':{'container':'qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015','imageDigest':'sha256:275f7b6b258fa87a2e22cf796ea9548bab78953ebe87ce45ff65eee1cd15bdef','vllmVersion':'0.1.dev1+g12dadcb41','attentionBackend':'ROCM_AITER_FA','contextLength':262144,'mtpDepth':3},
        'protocol':{'promptId':'reasoning-v1','promptSha256':PROMPT_SHA,'temperature':0,'seed':42,'thinking':False,'maxTokens':1024,'minTokens':256,'streaming':True,'includeUsage':True,'concurrency':1,'warmups':1,'measuredRuns':3},
        'warmup':rows[0],
        'measuredRows':measured,
        'representativeRun':rep['label'],
        'decodeMedianTokS':statistics.median(r['tokSOut'] for r in measured),
        'decodeRangeTokS':[min(r['tokSOut'] for r in measured),max(r['tokSOut'] for r in measured)],
        'allMeasuredOutputHashesIdentical':len(set(outputs))==1,
        'gpuMemorySamples':gpu_samples,
        'gpuMemorySampling':{'source':'amd-smi metric --mem-usage on MI210 LXC','reportedPeakMb':peak_mb,'processTable':'amd-smi process returned no running processes; device-level sampling used'},
        'submissionPayload':payload,
    }
    (OUT/'payload.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (OUT/'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (OUT/'gpu-memory-samples.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in gpu_samples),encoding='utf-8')
    print(json.dumps({'representativeRun':rep['label'],'decodeMedianTokS':result['decodeMedianTokS'],'decodeRangeTokS':result['decodeRangeTokS'],'prefillTokS':rep['tokSPrefill'],'ttftMs':payload['ttftMs'],'promptTokens':rep['promptTokens'],'outputTokens':rep['completionTokens'],'mtpDrafts':rep['specDraftTokens'],'mtpAccepted':rep['specAcceptedTokens'],'mtpTokenConsistencyDelta':rep['specTokenConsistencyDelta'],'prefixHitDeltas':[r['prefixCacheHitTokenDelta'] for r in measured],'allOutputsIdentical':result['allMeasuredOutputHashesIdentical'],'peakVramGb':payload.get('peakVramGb'),'gpuSamples':len(gpu_samples),'payloadPath':str(OUT/'payload.json'),'resultsPath':str(OUT/'results.json')},indent=2))

def main():
    if sha(PROMPT) != PROMPT_SHA:
        raise RuntimeError('canonical prompt SHA mismatch')
    health_status, health_body = http('/health', timeout=15)
    models_status, models_body = http('/v1/models', timeout=15)
    models=json.loads(models_body)
    model=next((m for m in models.get('data',[]) if m.get('id')==MODEL),None)
    if health_status != 200 or models_status != 200 or model is None or model.get('max_model_len') != 262144:
        raise RuntimeError(f'live identity preflight failed: health={health_status}, models={models_status}, model={model}')
    (OUT/'preflight.json').write_text(json.dumps({'timestamp':now_iso(),'healthHttp':health_status,'healthBodyBytes':len(health_body),'modelsHttp':models_status,'servedModel':model,'promptSha256':sha(PROMPT)},indent=2)+'\n')
    sampler=start_gpu_sampler()
    time.sleep(1.2)
    rows=[]
    try:
        rows.append(stream_request('warmup',(OUT/'output-warmup.txt')))
        for i in range(1,4):
            rows.append(stream_request(f'measured-{i}',OUT/f'output-{i}.txt'))
            print(json.dumps({'completedMeasured': i, 'decodeTokS': rows[-1]['tokSOut']}), flush=True)
    finally:
        try:
            stdout,stderr=sampler.communicate(input='stop\n',timeout=20)
        except subprocess.TimeoutExpired:
            sampler.terminate()
            stdout,stderr=sampler.communicate(timeout=8)
        if sampler.returncode not in (0,None) and stderr.strip():
            (OUT/'gpu-sampler.stderr.txt').write_text(stderr,encoding='utf-8')
    gpu_samples=sample_objects(stdout or '')
    errors=[x for x in gpu_samples if 'error' in x]
    valid=[x for x in gpu_samples if 'used_mb' in x]
    if not rows or len(rows)!=4:
        raise RuntimeError(f'incomplete measured rows: {len(rows)}')
    for row in rows:
        if row['completionTokens'] < 256:
            raise RuntimeError(f'{row["label"]}: output below canonical verification minimum: {row["completionTokens"]}')
    if errors and not valid:
        (OUT/'gpu-sampler.stderr.txt').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    build_payload(rows,gpu_samples)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'BENCHMARK_FAILED: {type(e).__name__}: {e}',file=sys.stderr)
        raise
