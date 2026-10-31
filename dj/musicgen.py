"""AI track generation: optional MusicGen via an isolated venv.
The main app stays stdlib-only — generation runs as a subprocess of
~/.config/djjamal/gen-env/bin/python (created by the user, see README).
Auto-disabled when the venv or model is absent."""
import os
import subprocess
import tempfile
from pathlib import Path

ENABLED = os.environ.get("DJ_MUSICGEN", "1") == "1"
# venv layout differs: bin/python (POSIX) vs Scripts\python.exe (Windows)
_VENV_BIN = ("Scripts/python.exe" if os.name == "nt" else "bin/python")
VENV_PY = Path(os.environ.get(
    "DJ_GEN_PYTHON",
    Path.home() / ".config/djjamal/gen-env" / _VENV_BIN))
DEFAULT_SECS = 12

# runs inside the venv: load MusicGen-small, write one wav, exit
_SCRIPT = """
import sys
from scipy.io.wavfile import write
import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

out_wav, prompt, secs = sys.argv[1], sys.argv[2], int(sys.argv[3])
proc = AutoProcessor.from_pretrained("facebook/musicgen-small")
model = MusicgenForConditionalGeneration.from_pretrained(
    "facebook/musicgen-small", torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32)
inputs = proc(text=[prompt], padding=True, return_tensors="pt")
with torch.no_grad():
    audio = model.generate(**inputs, max_new_tokens=int(secs * 51), do_sample=True)
rate = model.config.audio_encoder.sampling_rate
write(out_wav, rate, audio[0, 0].cpu().numpy())
"""


def available():
    return ENABLED and VENV_PY.is_file()


def generate(prompt, secs=DEFAULT_SECS, timeout=600):
    """Generate one wav for prompt. Returns (wav_path, None) or (None, error).
    Blocks for the whole synthesis — call from a worker thread."""
    prompt = " ".join(prompt.split())[:200]
    if not prompt or not available():
        return None, "musicgen unavailable"
    secs = max(4, min(int(secs), 30))
    fd, wav = tempfile.mkstemp(suffix=".wav", prefix="djgen-")
    os.close(fd)
    try:
        subprocess.run(
            [str(VENV_PY), "-c", _SCRIPT, wav, prompt, str(secs)],
            check=True, timeout=timeout,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return wav, None
    except subprocess.CalledProcessError as e:
        return None, (e.stderr or b"generation failed").decode()[-300:]
    except Exception as e:
        return None, str(e)
