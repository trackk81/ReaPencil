"""Optional compiled CPU capsule strokes, preserving premultiplied max coverage.

Call get_stroke() once per render to resolve the backend, then call the returned
function with the same arguments as renderer._stroke. No automatic fallback.
"""


def get_stroke():
    from .accelerator import enable
    enable()
    try:
        from ._stroke_kernel import stroke
    except (ImportError, OSError, RuntimeError, AttributeError) as error:
        raise RuntimeError('Compiled CPU stroke accelerator unavailable: %s' % error) from error
    return stroke


def stroke(layer,a,b,width,color):
    """Convenience entry; resolve get_stroke once for a hot render loop."""
    return get_stroke()(layer,a,b,width,color)
