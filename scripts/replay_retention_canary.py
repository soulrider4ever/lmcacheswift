"""Bounded cold/repeat experiment on the staged coordinator-split candidate."""
import json
import pathlib
import statistics
import time
import urllib.request

base = "http://127.0.0.1:8092"
root = pathlib.Path("/home/ubuntu/lmcache-integration-20261015")
questions = [("A", "17 times 19", "323"), ("B", "144 divided by 12", "12"), ("C", "37 plus 58", "95"), ("D", "9 times 8", "72")]
results = []
for phase in ("cold", "repeat"):
    for tag, question, answer in questions:
        prefix = "Replay retention fix experiment 20261016 unique01 " + tag + ".\n" + "".join(f"Record {i:04d}: the box contains blue tiles; this is reference material only.\n" for i in range(200))
        payload = {"model": "qwen38-swift-w8a8", "messages": [{"role": "user", "content": prefix + f"\nIgnore the records for the calculation. What is {question}? Reply only with the integer."}], "max_tokens": 32, "temperature": 0, "seed": 42, "chat_template_kwargs": {"enable_thinking": False}, "kv_transfer_params": {"cached_token_stats": True}}
        req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=240) as response:
            result = json.load(response)
        row = {"phase": phase, "tag": tag, "elapsed_seconds": time.monotonic() - start, "expected": answer, "response": result}
        results.append(row)
        (root / "replay-retention-canary.json").write_text(json.dumps(results, indent=2))
        content = result["choices"][0]["message"]["content"].strip()
        assert content == answer and result["choices"][0]["finish_reason"] == "stop", (tag, content)
        print(phase, tag, round(row["elapsed_seconds"], 3), "kv", result.get("kv_transfer_params"), flush=True)
        time.sleep(2)
    print("median", phase, statistics.median(x["elapsed_seconds"] for x in results if x["phase"] == phase), flush=True)
print("PASSED", len(results), flush=True)
