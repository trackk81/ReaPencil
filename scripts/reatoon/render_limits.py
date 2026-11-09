"""CPU allocation preflight; no arbitrary per-axis resolution cap."""
import ctypes,os
MAX_NATIVE_SAMPLES=2147483647

def available_memory():
    if os.name=='nt':
        class Status(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        state=Status();state.length=ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):return int(state.available)
    else:
        try:return int(os.sysconf('SC_AVPHYS_PAGES'))*int(os.sysconf('SC_PAGE_SIZE'))
        except (ValueError,OSError,AttributeError):pass
    return None

def check_frame_samples(width,height,supersample,check_memory=True,bytes_per_sample=56):
    width,height,supersample=int(width),int(height),int(supersample)
    if min(width,height)<1 or supersample not in (1,2,3,4):raise ValueError('Resolution must be positive and supersample 1..4')
    samples=width*height*supersample**2
    if samples>MAX_NATIVE_SAMPLES:
        raise ValueError('Image sampling exceeds the native CPU integer index range; reduce resolution or oversampling')
    # Actual live depth/plane/coverage/bounds buffers plus bounded row output
    # temporaries. Renderer supplies extra canvases for effects/hidden output. This is a preflight estimate, not a memory usage guarantee;
    # many simultaneous render elements can require additional memory.
    estimate=samples*int(bytes_per_sample)+max(32*1024**2,width*supersample*16*128)
    free=available_memory() if check_memory else None
    # Actual live buffers are already included in estimate. Keep a bounded
    # reserve instead of rejecting valid large allocations by reserving an
    # additional20% plus256MiB, which exceeded1.7GiB at7.51GiB available.
    reserve=min(int(free*.2),512*1024**2) if free is not None else 0
    usable=max(0,free-reserve) if free is not None else None
    if usable is not None and estimate>usable:
        raise ValueError('Insufficient available memory for CPU render: %d x %d at %dx sampling estimates %.2f GiB; %.2f GiB currently available, %.2f GiB usable after %.2f GiB headroom. Reduce oversampling or resolution, or free memory.'%(width,height,supersample,estimate/1024**3,free/1024**3,usable/1024**3,reserve/1024**3))
    return samples
