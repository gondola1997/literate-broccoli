"""
Live Voice Isolator
====================
Strips background noise (crowds, traffic, subway/airport ambience, fans,
keyboard clatter, etc.) from live audio in near-real-time, using the
pretrained DeepFilterNet3 neural noise-suppression model -- the same class
of deep-learning approach Krisp/RTX Voice use (not simple EQ/gating).

It can run TWO independent pipelines at once:

  MIC pipeline    : your microphone -> denoise -> a virtual cable that you
                    set as your mic in Discord/Zoom/etc. (so others hear a
                    clean you).
  INCOMING pipeline: the other person's audio (routed out of Discord/Zoom
                    into a second virtual cable) -> denoise -> your real
                    speakers/headphones (so you hear a clean them).

Run with --list-devices first to find the right device indices.
See README.md for the one-time Windows audio routing setup (VB-CABLE).

USAGE EXAMPLES
--------------
List devices:
    python app.py --list-devices

Run both directions:
    python app.py ^
        --mic-in 1 --mic-out 5 ^
        --call-in 6 --call-out 3

Run only the incoming/other-person direction:
    python app.py --call-in 6 --call-out 3
"""

import argparse
import queue
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import torch

SAMPLE_RATE = 48000  # DeepFilterNet is trained/fixed at 48kHz


def list_devices():
    print("\nAvailable audio devices (use the index on the left):\n")
    print(sd.query_devices())
    print(
        "\nTip: your physical mic and headphones are usually the ones with "
        "your hardware's name. Virtual cable devices show up as things like "
        "'CABLE Input (VB-Audio Virtual Cable)' / 'CABLE Output (VB-Audio "
        "Virtual Cable)' -- see README.md.\n"
    )


class Pipeline(threading.Thread):
    """One direction of audio: read from in_device, denoise, write to out_device."""

    def __init__(
        self,
        name,
        in_device,
        out_device,
        chunk_sec,
        context_sec,
        atten_db,
        post_filter,
        stop_event,
    ):
        super().__init__(daemon=True, name=name)
        self.name = name
        self.in_device = in_device
        self.out_device = out_device
        self.chunk_sec = chunk_sec
        self.context_sec = context_sec
        self.atten_db = atten_db
        self.stop_event = stop_event
        self.error = None

        # Each pipeline gets its OWN model instance. DeepFilterNet resets
        # its recurrent hidden state at the start of every enhance() call,
        # and that state lives on the model object -- sharing one model
        # across two threads running concurrently would let the two audio
        # streams corrupt each other's state. Two instances costs a bit of
        # extra RAM/load time but keeps the streams fully independent.
        from df.enhance import init_df

        # DeepFilterNet tries to log its own git commit hash/branch on
        # startup by shelling out to `git`. On a machine without Git
        # installed (true for most end users running the packaged exe),
        # that raises FileNotFoundError, which the library only partially
        # handles -- it crashes instead of just skipping the log line.
        # Neuter those lookups; they're purely informational.
        import df.logger as _df_logger
        _df_logger.get_commit_hash = lambda: None
        _df_logger.get_branch_name = lambda: None

        print(f"[{self.name}] Loading DeepFilterNet model...")
        self.model, self.df_state, _ = init_df(post_filter=post_filter)
        print(f"[{self.name}] Model ready.")

    def run(self):
        from df.enhance import enhance

        chunk_samples = int(self.chunk_sec * SAMPLE_RATE)
        context_samples = int(self.context_sec * SAMPLE_RATE)
        prev_tail = np.zeros(context_samples, dtype=np.float32)

        try:
            with sd.InputStream(
                device=self.in_device,
                channels=1,
                samplerate=SAMPLE_RATE,
                dtype="float32",
                blocksize=chunk_samples,
            ) as instream, sd.OutputStream(
                device=self.out_device,
                channels=1,
                samplerate=SAMPLE_RATE,
                dtype="float32",
                blocksize=chunk_samples,
            ) as outstream:
                print(
                    f"[{self.name}] Running. in='{instream.device}' "
                    f"out='{outstream.device}' chunk={self.chunk_sec}s "
                    f"context={self.context_sec}s "
                    f"(~{self.chunk_sec + self.context_sec:.2f}s latency)"
                )
                while not self.stop_event.is_set():
                    audio, overflowed = instream.read(chunk_samples)
                    if overflowed:
                        print(f"[{self.name}] input overflow (buffer underrun)")
                    audio = audio[:, 0].astype(np.float32)

                    # Prepend previous chunk's tail as "warm-up" context so
                    # the model's recurrent state isn't cold at the start
                    # of every chunk. We throw the context part of the
                    # *output* away and only keep/play the new part.
                    combined = np.concatenate([prev_tail, audio])
                    prev_tail = audio[-context_samples:] if context_samples > 0 else prev_tail

                    tensor = torch.from_numpy(combined).unsqueeze(0)  # [1, T]
                    with torch.no_grad():
                        enhanced = enhance(
                            self.model,
                            self.df_state,
                            tensor,
                            atten_lim_db=self.atten_db,
                        )
                    enhanced = enhanced.squeeze(0).cpu().numpy()
                    out_chunk = enhanced[context_samples:]
                    out_chunk = np.clip(out_chunk, -1.0, 1.0).astype(np.float32)
                    outstream.write(out_chunk.reshape(-1, 1))
        except Exception as e:  # surfaced to main thread after join
            self.error = e
            print(f"[{self.name}] ERROR: {e}")


def _prompt_int(prompt, allow_blank=False):
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            return int(raw)
        except ValueError:
            print("  Please enter a number from the device list above.")


def interactive_setup():
    """Plain-language walkthrough for people double-clicking the exe with
    no command-line arguments. Returns an argparse.Namespace matching what
    the CLI parser would produce."""
    print("=" * 60)
    print(" Live Voice Isolator - guided setup")
    print("=" * 60)
    print(
        "\nNo options were given, so here's a step-by-step setup instead.\n"
        "(Run with --list-devices or --help for the command-line version.)\n"
    )
    list_devices()

    print("What do you want to clean?")
    print("  1) Just what I hear from a call (their voice, remove their background noise)")
    print("  2) Just my microphone (so others hear a clean me)")
    print("  3) Both directions")
    while True:
        choice = input("Enter 1, 2, or 3: ").strip()
        if choice in ("1", "2", "3"):
            break
        print("  Please type 1, 2, or 3.")

    ns = argparse.Namespace(
        mic_in=None, mic_out=None, call_in=None, call_out=None,
        chunk=0.6, context=0.3, atten=None, post_filter=False,
        list_devices=False,
    )

    if choice in ("2", "3"):
        print("\n-- Microphone pipeline --")
        ns.mic_in = _prompt_int("Device index of your PHYSICAL microphone: ")
        ns.mic_out = _prompt_int("Device index of the virtual cable INPUT (e.g. 'CABLE-A Input'): ")

    if choice in ("1", "3"):
        print("\n-- Incoming call pipeline --")
        ns.call_in = _prompt_int("Device index of the virtual cable OUTPUT that your call app plays into (e.g. 'CABLE-B Output'): ")
        ns.call_out = _prompt_int("Device index of your real headphones/speakers: ")

    print(
        "\nUsing default quality settings (~0.9s delay). Edit the script or "
        "use the command-line flags (--chunk/--context) later to tune this.\n"
    )
    return ns


def main():
    # Beginner path: double-clicking the exe gives no arguments at all.
    if len(sys.argv) == 1:
        args = interactive_setup()
        run_pipelines(args)
        return

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list-devices", action="store_true", help="List audio devices and exit.")

    p.add_argument("--mic-in", type=int, default=None, help="Device index: your physical microphone.")
    p.add_argument("--mic-out", type=int, default=None, help="Device index: virtual cable INPUT that Discord/Zoom uses as its mic.")

    p.add_argument("--call-in", type=int, default=None, help="Device index: virtual cable OUTPUT that Discord/Zoom is playing into.")
    p.add_argument("--call-out", type=int, default=None, help="Device index: your real speakers/headphones.")

    p.add_argument("--chunk", type=float, default=0.6, help="Seconds of audio processed per pass. Lower = less latency but more CPU overhead and slightly choppier processing. Default 0.6.")
    p.add_argument("--context", type=float, default=0.3, help="Seconds of prior audio fed in as 'warm-up' context each pass (improves quality at chunk boundaries, adds to total latency). Default 0.3.")
    p.add_argument("--atten", type=float, default=None, help="Optional attenuation limit in dB (e.g. 20). Leave unset for max noise removal.")
    p.add_argument("--post-filter", action="store_true", help="Slightly more aggressive suppression on very noisy audio.")

    args = p.parse_args()

    if args.list_devices:
        list_devices()
        return

    run_pipelines(args)


def run_pipelines(args):
    if args.mic_in is None and args.call_in is None:
        print(
            "Nothing to do: pass --mic-in/--mic-out for the outgoing mic "
            "pipeline and/or --call-in/--call-out for the incoming call "
            "pipeline. Run --list-devices first.\n"
        )
        sys.exit(1)

    stop_event = threading.Event()
    pipelines = []

    if args.mic_in is not None:
        if args.mic_out is None:
            print("--mic-in given but --mic-out is missing.")
            sys.exit(1)
        pipelines.append(
            Pipeline(
                "MIC->OUT",
                args.mic_in,
                args.mic_out,
                args.chunk,
                args.context,
                args.atten,
                args.post_filter,
                stop_event,
            )
        )

    if args.call_in is not None:
        if args.call_out is None:
            print("--call-in given but --call-out is missing.")
            sys.exit(1)
        pipelines.append(
            Pipeline(
                "CALL->SPEAKERS",
                args.call_in,
                args.call_out,
                args.chunk,
                args.context,
                args.atten,
                args.post_filter,
                stop_event,
            )
        )

    for pipe in pipelines:
        pipe.start()

    print("\nRunning. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(0.3)
            if any(pipe.error for pipe in pipelines):
                break
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_event.set()
        for pipe in pipelines:
            pipe.join(timeout=5)

    if sys.argv[0].lower().endswith((".exe",)) or len(sys.argv) == 1:
        input("\nDone. Press Enter to close this window...")


if __name__ == "__main__":
    main()
