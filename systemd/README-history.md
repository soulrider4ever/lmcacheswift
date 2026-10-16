# Unit history on CT125 (192.168.1.107)

| Unit | Port | Status | Notes |
|---|---|---|---|
| `lmcache-mtp-server.service` | 5556 | **active + enabled** | Live MTP-compatible cache, 40 GiB L1 (resized from 8 GiB on 2026-10-15 with owner approval), chunk 800. |
| `lmcache-mtp-experiment-20261015.service` | 5556 | removed (was transient) | Original experiment unit; the persistent unit used `ExecCondition` to avoid double-binding while it existed. |
| `lmcache-server.service` + drop-in `hybrid.conf` | 5555 | inactive + disabled (stopped) | Original no-MTP hybrid cache, chunk 784, 40 GiB. Fallback only; start manually if rolling back inference to the no-MTP container. |

Drop-in note: `hybrid.conf` overrides ExecStart to add `--chunk-size 784 --separate-object-groups --isolated-ipc` to the base unit.
