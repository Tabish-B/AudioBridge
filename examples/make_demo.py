"""Make a synthetic recording for trying the player and audio checks."""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def make_demo(destination):
    rate = 48000
    t = np.arange(rate * 12) / rate
    rng = np.random.default_rng(42)
    envelope = np.maximum(0, np.sin(2 * np.pi * 1.6 * t)) ** 2
    envelope *= (t > 1) & (t < 10.8)
    fundamental = 150 + 35 * np.sin(2 * np.pi * .3 * t)
    phase = 2 * np.pi * np.cumsum(fundamental) / rate
    signal = envelope * (.28 * np.sin(phase) + .12 * np.sin(2 * phase) + .06 * np.sin(3 * phase))
    signal += rng.normal(0, .003, len(t))
    signal[8 * rate:8 * rate + 240] = 1
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destination, signal, rate, subtype='PCM_16')
    return destination


if __name__ == '__main__':
    path = make_demo(sys.argv[1] if len(sys.argv) > 1 else 'Synthetic quality-check demo.wav')
    print(path)
