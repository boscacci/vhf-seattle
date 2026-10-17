# Phone background radio

Listen live defaults system media controls on for all devices, including iPhone
and iPad. An explicitly saved off setting remains respected. Playback publishes
the station and selected channel/group through Media Session; Play, Pause and
Stop work independently so one unsupported action cannot erase other controls.
Pause disables queue processing before pausing audio, including native media
pause events. Pending queue responses cannot restart a paused session.

Phones use the native audio element instead of routing its sound through the
Web Audio visualizer. The optional Audio Session API requests the playback
category when supported. These changes avoid reliance on a running visualizer
context for phone audio. Desktop visualization remains available.

The same audio element is reused for direct streams and grouped clip playback.
When an enabled queue has no transmission to play, it loops ten seconds of local
PCM silence representing quiet radio time. The WAV is constructed once in memory;
it requires no server mixer, cloud requests or added transcription work. The
next queued clip replaces that quiet source, and its end returns to quiet playback.
The first quiet playback starts from the user's Play gesture, before network
requests, to establish the audio session. Browser rejection returns to a Play
prompt rather than claiming that background playback is working.

Visibility and page-hide events preserve an active radio session. Explicit Stop,
Pause, switching to other app views, or playing another clip retain their existing
stop behavior. The browser and operating system still control whether a page may
run or continue media playback; this does not provide native-app entitlements.

## Verification

The dev release runs `background_radio_browser_smoke.mjs` inside the existing
Playwright suite. Independent iPhone and Android browser profiles exercise native
audio through quiet periods, a new queued transmission while hidden, return to
quiet playback, media Play/Pause/Stop, native pause, and individual live streams.
They check reuse of the same element and no phone Web Audio graph. Audio and
queue fixtures are isolated; other dev tests still check real retained feeds.
Failure screenshots are retained beside the existing ASR smoke artifacts.

Emulated browser lifecycle events do not prove physical phone screen-lock behavior.
Before promoting the exact dev artifact, play a group on the dev site, lock the
phone through a quiet period and the next transmission, then pause and resume
from the lock screen. Repeat for an individual channel and verify Stop releases
the radio. Closing the browser entirely or OS termination can end playback.

References: [Media Session API](https://developer.mozilla.org/en-US/docs/Web/API/Media_Session_API),
[Audio Session API](https://developer.mozilla.org/en-US/docs/Web/API/Audio_Session_API),
and [WebKit background AudioContext report](https://bugs.webkit.org/show_bug.cgi?id=261554).
