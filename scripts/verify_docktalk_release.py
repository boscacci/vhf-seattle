"""Read-only production acceptance and thirty-minute soak; never claim a node here."""

import argparse
import json
import subprocess
import time
from pathlib import Path

REMOTE = r"""
import json,sys,time,os,subprocess,urllib.request
sys.path.insert(0,'/opt/talkingboats/docktalk/current')
from talkingboats.channel_metadata import ACTIVE_CAPTURE_CHANNELS,LIVE_STREAM_CHANNELS
from talkingboats.receiver_config import channel_blocks,object_blocks
from talkingboats.docktalk import api,load_identity
from pathlib import Path
config=Path('/etc/talkingboats/rtl_airband-voice-net-balanced.conf').read_text()
blocks=channel_blocks(config)
recorded={c for _,_,c,b in blocks
          if any('type = "file"' in o or 'type="file"' in o for _,_,o in object_blocks(b))}
if {b[2] for b in blocks}!=set(LIVE_STREAM_CHANNELS) or recorded!=set(ACTIVE_CAPTURE_CHANNELS):
    raise SystemExit('Receiver outputs do not match accepted policy')
status=json.load(urllib.request.urlopen('http://127.0.0.1:8000/status-json.xsl',timeout=8))['icestats']['source']
status=status if isinstance(status,list) else [status]
mounts={s['listenurl'].rsplit('/',1)[-1] for s in status}
identity=load_identity(Path('/etc/docktalk'))
report=json.loads(api('GET',f"/v1/nodes/{identity['NODE_ID']}/pushage",token=identity['PUSH_TOKEN']))
health=json.loads(Path('/run/docktalk/health.json').read_text())
fresh={c for c,h in health.items() if time.time()-h['last_sent_epoch']<60}
unit=subprocess.check_output(['systemctl','show','docktalk-push.service','-p','NRestarts','-p','MemoryCurrent'],text=True)
peak_temp=int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000
# Watch for unexpected new files in the channels whose history must remain untouched.
now=time.time();unexpected=0
spool=Path('/opt/talkingboats/spool/airband')
for channel in set(LIVE_STREAM_CHANNELS)-set(ACTIVE_CAPTURE_CHANNELS):
    for file in (spool/channel).glob('*'):
        if file.is_file() and file.stat().st_mtime>=float(sys.argv[1]):unexpected+=1
print(json.dumps({'live_mounts':len(mounts),'fresh_relay_channels':len(fresh),'receiver_recorded_channels':sorted(recorded),'docktalk_age_seconds':report.get('age_s'),'temp_c':peak_temp,'relay_unit':unit,'unexpected_live_only_files':unexpected}))
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="rob@192.168.1.114")
    parser.add_argument("--duration-seconds", type=int, default=1800)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration_seconds < 1800:
        parser.error("production soak must last at least thirty minutes")
    started = time.time()
    observations = []
    # Give the relay its first 30-second health snapshot before evaluating it.
    time.sleep(35)
    while True:
        process = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                args.target,
                f"sudo -n python3 - {started}",
            ],
            input=REMOTE,
            text=True,
            capture_output=True,
            timeout=60,
            check=True,
        )
        state = json.loads(process.stdout)
        if (
            state["live_mounts"] != 18
            or state["fresh_relay_channels"] != 18
            or state["receiver_recorded_channels"]
            != ["13", "14", "16", "22A", "65A", "66A", "71", "77", "78A"]
            or state["unexpected_live_only_files"]
        ):
            raise RuntimeError("channel isolation or relay health acceptance failed")
        if (
            state["docktalk_age_seconds"] is None
            or float(state["docktalk_age_seconds"]) > 60
            or state["temp_c"] >= 80
        ):
            raise RuntimeError("DockTalk reception or Pi temperature acceptance failed")
        observations.append({"at_epoch": time.time(), **state})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {"started_epoch": started, "passed": False, "observations": observations}, indent=2
            )
            + "\n"
        )
        print(
            json.dumps(
                {
                    "event": "docktalk_soak_progress",
                    "elapsed_seconds": round(time.time() - started),
                    "fresh_channels": state["fresh_relay_channels"],
                    "server_age_seconds": state["docktalk_age_seconds"],
                }
            ),
            flush=True,
        )
        if time.time() - started >= args.duration_seconds:
            break
        time.sleep(min(30, args.duration_seconds - (time.time() - started)))
    args.output.write_text(
        json.dumps(
            {"started_epoch": started, "passed": True, "observations": observations}, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
