import os,signal,pathlib,subprocess,time
runner=b'/home/ubuntu/lmcache-integration-20261015/run_replay_cap_canary.sh'
found=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try: args=(p/'cmdline').read_bytes().split(b'\0')
 except (OSError,ProcessLookupError): continue
 if len(args)>1 and args[0]==b'bash' and args[1]==runner: found.append(int(p.name))
for pid in found: os.kill(pid,signal.SIGTERM)
for pid in found:
 for _ in range(30):
  if not pathlib.Path('/proc',str(pid)).exists(): break
  time.sleep(0.1)
 else: raise RuntimeError('old recovery controller still present')
print('cancelled_recovery_waiters',found,flush=True)
root=pathlib.Path('/home/ubuntu/lmcache-integration-20261015')
nomtp='qwen38-swift-w8a8-lmcache-layout-20261015'
mtp='qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015'
for label,name in [('nomtp',nomtp),('mtp',mtp)]:
 p=root/('promotion-20261016-'+label+'.inspect.json')
 p.write_bytes(subprocess.check_output(['docker','inspect',name]));p.chmod(0o600)
subprocess.run(['docker','update','--restart=no',nomtp],check=True)
subprocess.run(['docker','update','--restart=unless-stopped',mtp],check=True)
subprocess.run(['docker','stop','-t','120',nomtp],check=True)
subprocess.run(['docker','start',mtp],check=True)
for name in (mtp,nomtp):
 subprocess.run(['docker','inspect',name,'--format','{{.Name}} status={{.State.Status}} restart={{.HostConfig.RestartPolicy.Name}} oom={{.State.OOMKilled}}'],check=True)
