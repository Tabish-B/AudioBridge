"""Output choices shared by the converter and the settings panel."""

FORMATS = {
    'WAV': ('.wav', 'PCM WAV · uncompressed'),
    'FLAC': ('.flac', 'FLAC · lossless compression'),
    'MP3': ('.mp3', 'MP3 · lossy, useful for sharing'),
    'AIFF': ('.aiff', 'AIFF · uncompressed PCM'),
    'Keep original': (None, 'Keep the source audio container; re-encode with the chosen settings'),
}


def output_suffix(input_path, output_format):
    if output_format not in FORMATS:
        raise ValueError(f'Unsupported output format: {output_format}')
    suffix = FORMATS[output_format][0] or input_path.suffix.lower()
    if suffix not in {'.wav', '.flac', '.mp3', '.m4a', '.aac', '.aiff', '.aif', '.opus'}:
        raise ValueError('Choose an audio output format for this source; its container cannot be preserved.')
    return suffix


def codec_options(suffix, bit_depth):
    if bit_depth not in (16, 24):
        raise ValueError(f'Unsupported bit depth: {bit_depth}')
    return {
        '.wav': ['-c:a', 'pcm_s16le' if bit_depth == 16 else 'pcm_s24le'],
        '.aiff': ['-c:a', 'pcm_s16be' if bit_depth == 16 else 'pcm_s24be'],
        '.aif': ['-c:a', 'pcm_s16be' if bit_depth == 16 else 'pcm_s24be'],
        '.flac': ['-c:a', 'flac', '-sample_fmt', 's16' if bit_depth == 16 else 's32', '-bits_per_raw_sample', str(bit_depth)],
        '.mp3': ['-c:a', 'libmp3lame', '-q:a', '2'],
        '.m4a': ['-c:a', 'aac', '-b:a', '192k'],
        '.aac': ['-c:a', 'aac', '-b:a', '192k'],
        '.opus': ['-c:a', 'libopus', '-b:a', '128k'],
    }[suffix]
