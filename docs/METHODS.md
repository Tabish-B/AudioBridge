# Signal processing and limits

[← User guide](USER_GUIDE.md)

## Source and display

Source measurements read every channel at its native rate. Plotting decodes a mono downmix with FFmpeg at the source rate capped at 48 kHz. This caps display Nyquist at 24 kHz and can cancel opposite-phase stereo content. It does not change the source or choose export settings.

Whole-file envelopes contain at most approximately 12,000 min/max bins. Waveform zoom windows of up to 30 seconds are decoded separately into at most 12,000 local bins. This is visual inspection, not a sample-grid editor. Region export operates on source samples, independent of display downsampling.

## STFT and power density

The streaming STFT retains overlap across decode blocks. It uses a periodic SciPy window, no detrending, an FFT equal to the selected window length, and the selected hop. The final incomplete window is zero-padded. Frame times reference window centers.

One-sided power density is `abs(rFFT(window * frame))² / (sample_rate * sum(window²))`. Interior frequency bins are doubled; DC and Nyquist are not. Values use `10 * log10(max(power, 1e-12))`, in dBFS/Hz for full-scale-normalized samples.

The whole-file image pools maxima into at most 1,600 time columns to keep brief events visible. It isn't a complete per-frame feature matrix. Linear/log axis changes interpolate the display grid; logarithmic frequency begins at the selected lower bound or the first non-zero FFT bin, whichever is higher. Color bounds clip the display, not the underlying power calculation.

## Mel spectrogram

Filters are peak-normalized triangles spaced by `2595 * log10(1 + frequency / 700)`, the HTK Mel frequency formula. They are not Slaney-area normalized. Each frame's one-sided PSD is multiplied by this filterbank, converted to log power, then peak-pooled over display time bins. The legend calls this a Mel-weighted PSD sum rather than physical broadband power or loudness. Frequency labels identify filter centers.

## MFCC

MFCCs use a type-II orthonormal DCT of the per-frame log Mel values, retaining coefficient 0 through the chosen count minus one. There is no pre-emphasis, cepstral lifter, delta calculation, or cepstral mean normalization. MFCC display columns average coefficients in time, rather than taking maxima. The diverging color scale is symmetric around zero using the 99th percentile of absolute displayed values, with a minimum bound of 1.

These conventions are explicit so the display is reproducible. It is not interchangeable with a model's input pipeline or the defaults of another library. In particular, MFCC implementations differ in Mel normalization, power scaling, centering, flooring, and coefficient conventions.

## Editing

Start/end seconds are rounded to source sample indices. FFmpeg trims using those sample indices and resets output timestamps. Exports are staged, then published with exclusive file creation. Split boundaries use the same rounded index in each half, so source-rate lossless halves reassemble without gaps or overlap. Resampling, bit-depth conversion, and lossy encoding follow the selected export settings and may change the resulting samples or duration.

Selection playback is a separate temporary 24-bit PCM media file, so it doesn't depend on a timer stopping the full-source player at the region boundary.

## Measurement caveats

Quiet windows are 20 ms RMS windows below −40 dBFS, not voice activity detection. Near-full-scale means `abs(sample) >= 0.999`; it cannot prove clipping happened earlier. Crest factor is peak minus RMS, not full dynamic range. Digital silence uses a −240 dBFS numerical floor. These measurements do not estimate true SNR, LUFS, true peak, or transcription quality.

Preview decode has a 180-second processing deadline; region/export decode has a 600-second deadline. Failures are reported without replacing the source. Very long recordings have coarser overview time resolution. This release does not provide an unpooled scientific feature export or an ML repair model.

## References

- [SciPy periodic windows](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.get_window.html)
- [SciPy spectrogram scaling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.spectrogram.html)
- [Librosa MFCC API and conventions](https://librosa.org/doc/main/api/generated/librosa.feature.mfcc.html)

The tests compare streamed STFT output with SciPy's independent spectrogram implementation, validate known-tone power, and compare the Mel/DCT calculation with a reference calculation.
