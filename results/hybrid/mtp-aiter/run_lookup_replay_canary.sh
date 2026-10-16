#!/bin/bash
set -euo pipefail
cd /home/ubuntu/lmcache-integration-20261015
live=qwen38-swift-w8a8-lmcache-layout-20261015
candidate=qwen38-swift-w8a8-lmcache-aiter-mtp3-lookup-replay-20261015
healthy() {
  for attempt in $(seq 1 180); do
    if curl -fsS --max-time 2 http://127.0.0.1:8092/health >/dev/null; then return 0; fi
    sleep 2
  done
  return 1
}
recover() {
  result=$?
  trap - EXIT
  docker logs "$candidate" > lookup-replay-full.log 2>&1 || true
  docker stop -t 120 "$candidate" >/dev/null || true
  docker start "$live" >/dev/null
  if healthy; then
    docker inspect "$live" --format 'RECOVERED_LIVE status={{.State.Status}} restart={{.HostConfig.RestartPolicy.Name}} oom={{.State.OOMKilled}}'
  else
    echo RECOVERY_FAILED
    exit 1
  fi
  exit "$result"
}
[ "$(docker inspect "$live" --format '{{.State.Status}}')" = running ]
[ "$(docker inspect "$candidate" --format '{{.HostConfig.RestartPolicy.Name}}')" = no ]
curl -fsS http://127.0.0.1:8092/metrics | python3 -c 'import sys; x=sys.stdin.read(); assert all(float(line.split()[-1]) == 0 for line in x.splitlines() if line.startswith(("vllm:num_requests_running{", "vllm:num_requests_waiting{")))'
trap recover EXIT
# Graceful service handoff only; no cache-server or guest restart.
docker stop -t 120 "$live" >/dev/null
docker start "$candidate" >/dev/null
healthy
python3 lookup_replay_canary.py initial
curl -fsS http://127.0.0.1:8092/metrics > lookup-replay-initial-metrics.txt
docker stop -t 120 "$candidate" >/dev/null
docker start "$candidate" >/dev/null
healthy
python3 lookup_replay_canary.py restart
python3 lookup_replay_functional.py
python3 decode_count_benchmark.py lookup-replay
curl -fsS http://127.0.0.1:8092/metrics > lookup-replay-metrics.txt
