import re
import subprocess
from pathlib import Path


def test_system_radio_session_defaults_on_and_survives_unsupported_stop_action():
    source = Path("public-site/assets/app.js").read_text()
    names = ["defaultSystemMediaControlsEnabled", "preferNativeLiveAudio", "updateLiveMediaSession"]
    functions = "\n".join(
        re.search(rf"function {name}\([^\n]*\) \{{\n.*?\n\}}", source, re.S).group()
        for name in names
    )
    script = (
        r"""
const assert = require('node:assert/strict');
const handlers = {};
const navigator = { userAgent:'iPhone', platform:'iPhone', maxTouchPoints:1,
  mediaSession:{setActionHandler(action,handler){
    if(action==='stop') throw new Error('unsupported action');
    handlers[action]=handler;
  }} };
const window = {MediaMetadata:class {constructor(fields){Object.assign(this,fields);}}};
let systemMediaControlsEnabled = true;
const liveAudio = {paused:false};
let paused = 0, played = 0, cleared = 0;
function isQueuedLiveMode(){return false;}
function pauseLivePlayback(){paused++;}
function connectLive(){played++;}
function closeLiveAudioStream(){}
function clearBrowserMediaSession(){cleared++;}
function channelLabel(c){return c;}
const selectedLiveChannel='14';
"""
        + functions
        + r"""
assert(defaultSystemMediaControlsEnabled());
assert(preferNativeLiveAudio());
navigator.userAgent='Macintosh'; navigator.platform='MacIntel'; navigator.maxTouchPoints=5;
assert(preferNativeLiveAudio());
navigator.maxTouchPoints=0;
assert(!preferNativeLiveAudio());
updateLiveMediaSession('playing');
assert.equal(navigator.mediaSession.metadata.title,'Elliott Bay VHF');
assert.equal(navigator.mediaSession.playbackState,'playing');
assert.equal(cleared,0);
handlers.pause();assert.equal(paused,1);
handlers.play();assert.equal(played,1);
systemMediaControlsEnabled=false;
updateLiveMediaSession();assert.equal(cleared,1);
"""
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)


def test_radio_quiet_source_is_valid_pcm_and_reused():
    source = Path("public-site/assets/app.js").read_text()
    function = re.search(r"function radioQuietAudioUrl\(\) \{\n.*?\n\}", source, re.S).group()
    script = (
        r"""
const assert = require('node:assert/strict');
let quietAudioUrl = null;
let payload = null, created = 0;
const URL = {createObjectURL(blob){payload=blob;created++;return 'blob:quiet';}};
"""
        + function
        + r"""
assert.equal(radioQuietAudioUrl(),'blob:quiet');
assert.equal(radioQuietAudioUrl(),'blob:quiet');
assert.equal(created,1);
(async()=>{
 const buffer=await payload.arrayBuffer(), bytes=new Uint8Array(buffer), view=new DataView(buffer);
 assert.equal(new TextDecoder().decode(bytes.slice(0,4)),'RIFF');
 assert.equal(new TextDecoder().decode(bytes.slice(8,12)),'WAVE');
 assert.equal(view.getUint16(20,true),1);
 assert.equal(view.getUint16(22,true),1);
 assert.equal(view.getUint32(24,true),8000);
 assert.equal(view.getUint16(34,true),16);
 assert.equal(view.getUint32(40,true),160000);
 assert(bytes.slice(44).every(value=>value===0));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)


def test_quiet_playback_rejection_prompts_for_play_and_respects_stop_and_opt_out():
    source = Path("public-site/assets/app.js").read_text()
    function = re.search(
        r"async function playRadioQuietAudio\([^\n]*\) \{\n.*?\n\}", source, re.S
    ).group()
    script = (
        r"""
const assert = require('node:assert/strict');
let active = true, cleared = 0, configured = 0;
let systemMediaControlsEnabled = true;
const liveStatus = {textContent:''};
const liveAudio = {getAttribute(){return '';},load(){},
  play(){return Promise.reject(new Error('gesture required'));}};
function isCurrentLiveQueueSession(){return active;}
function clearLiveQueueAudioSource(){cleared++;}
function configurePlaybackAudioSession(){configured++;}
function configureEverythingQueueAudioElement(){}
function radioQuietAudioUrl(){return 'blob:quiet';}
function pauseLivePlayback(){active=false;}
"""
        + function
        + r"""
(async()=>{
 await playRadioQuietAudio({queueGeneration:1,queueChannel:'everything'});
 assert.equal(active,false);
 assert.equal(liveStatus.textContent,'Press Play to resume radio');
 await playRadioQuietAudio({queueGeneration:1,queueChannel:'everything'});
 assert.equal(configured,1);
 active=true;systemMediaControlsEnabled=false;
 await playRadioQuietAudio({queueGeneration:2,queueChannel:'everything'});
 assert.equal(cleared,1);assert.equal(configured,1);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
