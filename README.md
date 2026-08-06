Live Voice Isolator (Windows)
Removes background noise from live audio using DeepFilterNet3, a pretrained
neural noise-suppression model (the same category of tool as Krisp/RTX
Voice — not a simple gate/EQ). It handles non-stationary noise like crowd
chatter, subway/airport ambience, traffic, keyboards, fans, etc.
It can clean audio in two directions independently:
Your mic → cleaned → sent into Discord/Zoom/etc. (others hear only you)
Their voice coming out of Discord/Zoom → cleaned → your speakers (you
hear only them)
You can run either one alone, or both at once.
How it works / limits
This is a real, working DIY denoiser — not a toy. Two honest caveats:
Latency. It processes audio in short chunks (default ~0.6s, plus
~0.3s of "warm-up" context) rather than sample-by-sample, so there's
roughly ~0.7–1s of delay by default. That's noticeably more than
Krisp's ~20-30ms. You can lower `--chunk`/`--context` for less delay at
a slight quality cost (see Tuning below). For a live back-and-forth
conversation ~1s delay is usually fine; for something latency-critical
(live singing, etc.) it will feel laggy.
CPU use. It runs on your CPU (no GPU required). A modern
multi-core CPU can run one pipeline comfortably in real time; running
both pipelines at once roughly doubles the load. If your CPU is old/weak,
increase `--chunk` to reduce overhead.
---
Just want an .exe, no Python?
You have two options — pick one:
Option A — build it yourself once (5-10 min, needs Python once)
Do steps 1–2 below (install Python 3.10/3.11 and VB-CABLE).
Double-click `build_exe.bat` in this folder and follow the prompts.
When it finishes, `dist\VoiceIsolator.exe` is a real standalone app.
Copy just that one file anywhere (even a different PC) — it needs
nothing else installed. Double-click it and it'll ask you simple
questions instead of command-line flags.
Option B — build it in the cloud, install nothing locally
Create a free GitHub account if you don't have one, and push this
folder to a new repo (or ask someone technical to do this part for
you once).
In the repo, go to the Actions tab → Build Windows exe →
Run workflow.
Wait a few minutes, then open the finished run and download the
`VoiceIsolator-windows` artifact — it's the `.exe`, ready to run.
No Python, no pip, nothing installed on your own machine.
Either way, you'll still separately need to install VB-CABLE (step 2
below) — that's a Windows audio driver, not something that can be baked
into a regular .exe.
Note: the built exe is large (roughly 500MB–1GB, since it bundles the
whole AI model runtime) and takes ~10-20 seconds to start up the first
time you run it each session — that's normal.
---
1. Install Python
Install Python 3.10 or 3.11 from python.org (64-bit). Not 3.12+ — the
compiled noise-suppression engine doesn't yet ship prebuilt Windows wheels
for newer Python versions, and you don't want to be compiling Rust code.
During install, check "Add python.exe to PATH."
2. Install the virtual audio cables
You need a virtual audio cable to pipe audio in and out of Discord/Zoom, and
you need two separate cable pairs — one per direction. The easiest free
option is VB-Audio's "VB-CABLE A+B" driver pack, which installs two
cables at once ("Cable A" and "Cable B"):
Go to https://vb-audio.com/Cable/ and download VB-CABLE A+B.
Run the installer as Administrator, reboot if it asks.
You'll now have 4 new devices in Windows: `CABLE-A Input`,
`CABLE-A Output`, `CABLE-B Input`, `CABLE-B Output`.
(If you only care about ONE direction, the regular single VB-CABLE
download is enough — skip the "A+B" version.)
3. Set up the project
Open Command Prompt in this folder and run:
```
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
The first time you run the app it will also download the pretrained model
(~30MB) automatically — needs internet once.
4. Find your device indices
```
python app.py --list-devices
```
Note the index numbers for:
Your physical microphone (e.g. "Microphone (Realtek Audio)")
Your physical headphones/speakers (e.g. "Headphones (Realtek Audio)")
`CABLE-A Input`
`CABLE-A Output`
`CABLE-B Input`
`CABLE-B Output`
5. Route Windows/Discord audio through the cables
For your mic (outgoing) pipeline:
In Discord/Zoom's mic settings, set the input device to `CABLE-A Output`.
The app will read your real mic, clean it, and write to `CABLE-A Input`
(which Discord picks up as `CABLE-A Output`).
For the incoming call (their voice) pipeline:
In Discord/Zoom's speaker/output settings, set the output device to
`CABLE-B Input`.
The app will read from `CABLE-B Output`, clean it, and play it to your
real headphones/speakers.
6. Run it
If you built the .exe (Option A/B above): just double-click
`VoiceIsolator.exe`. It'll list your devices and ask plain questions
(which pipeline you want, which device numbers) — no flags needed.
If you're running from Python directly:
Both directions:
```
python app.py --mic-in <physical_mic_index> --mic-out <CABLE-A_Input_index> --call-in <CABLE-B_Output_index> --call-out <physical_headphones_index>
```
Just cleaning what you hear from a call:
```
python app.py --call-in <CABLE-B_Output_index> --call-out <physical_headphones_index>
```
Just cleaning your mic before it goes out:
```
python app.py --mic-in <physical_mic_index> --mic-out <CABLE-A_Input_index>
```
Leave it running in the background during your call. Ctrl+C to stop.
Tuning
`--chunk 0.3 --context 0.15` — lower latency (~0.45s), slightly less
smooth on very difficult noise.
`--chunk 1.0 --context 0.4` — higher quality/stability, more delay.
`--atten 20` — cap noise reduction at 20dB instead of max removal, if you
want to keep a little ambience instead of dead silence.
`--post-filter` — a bit more aggressive suppression on very noisy input
(can very slightly affect voice naturalness).
Troubleshooting
"Device unavailable" / crash on start — double check the index
numbers with `--list-devices` (they can shift after driver installs).
Choppy audio / a lot of "overflow" messages — your CPU can't keep up
at the current chunk size; increase `--chunk`.
No sound at all — confirm Discord/Zoom's device settings actually
point at the cable devices (step 5), and that Windows isn't muting the
cable device in the Volume Mixer.
pip install fails trying to compile Rust — you're likely on Python
3.12+. Reinstall with Python 3.10/3.11 as described in step 1.
