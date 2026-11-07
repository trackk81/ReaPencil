"""Shared bounds for full-frame CPU image allocations."""
MAX_FRAME_SAMPLES=33_554_432


def check_frame_samples(width,height,supersample):
    samples=int(width)*int(height)*int(supersample)**2
    if samples>MAX_FRAME_SAMPLES:
        raise ValueError('CPU render sample budget exceeded: %d x %d at %dx sampling uses %.1fM samples; maximum is 32 Mi samples. Reduce resolution or oversampling.' %
                         (width,height,supersample,samples/1_000_000))
    return samples
