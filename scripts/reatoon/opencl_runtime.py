"""Small OpenCL 1.2 binding. GPU devices only; never silently select a CPU ICD.

Uses the installed graphics driver's ICD, no Python package/NumPy replacement.
Reference: https://registry.khronos.org/OpenCL/specs/1.2/html/OpenCL_API.html
"""
import ctypes as C
import ctypes.util
import numpy as np


class OpenCLError(RuntimeError):
    pass


def check(code):
    if code:
        raise OpenCLError('OpenCL error %d' % code)


class Buffer:
    def __init__(self, runtime, size):
        self.runtime = runtime
        self.size = max(4, int(size))
        err = C.c_int()
        self.handle = C.c_void_p(runtime.lib.clCreateBuffer(runtime.context, 1, self.size, None, C.byref(err)))
        check(err.value)

    def close(self):
        if self.handle:
            self.runtime.lib.clReleaseMemObject(self.handle)
            self.handle = None

    def __del__(self):
        self.close()


class Runtime:
    def __init__(self):
        lib = C.WinDLL('OpenCL.dll') if hasattr(C, 'WinDLL') else C.CDLL(C.util.find_library('OpenCL'))
        self.lib = lib
        P, I, U, S = C.c_void_p, C.c_int, C.c_uint, C.c_size_t
        specs = {
            'clGetPlatformIDs': (I, [U, P, P]),
            'clGetDeviceIDs': (I, [P, C.c_ulonglong, U, P, P]),
            'clGetDeviceInfo': (I, [P, U, S, P, P]),
            'clCreateContext': (P, [P, U, P, P, P, P]),
            'clCreateCommandQueue': (P, [P, P, C.c_ulonglong, P]),
            'clCreateBuffer': (P, [P, C.c_ulonglong, S, P, P]),
            'clCreateProgramWithSource': (P, [P, U, P, P, P]),
            'clBuildProgram': (I, [P, U, P, C.c_char_p, P, P]),
            'clGetProgramBuildInfo': (I, [P, P, U, S, P, P]),
            'clCreateKernel': (P, [P, C.c_char_p, P]),
            'clGetKernelWorkGroupInfo': (I, [P, P, U, S, P, P]),
            'clSetKernelArg': (I, [P, U, S, P]),
            'clEnqueueNDRangeKernel': (I, [P, P, U, P, P, P, U, P, P]),
            'clEnqueueWriteBuffer': (I, [P, P, U, S, S, P, U, P, P]),
            'clEnqueueReadBuffer': (I, [P, P, U, S, S, P, U, P, P]),
            'clFinish': (I, [P]),
            'clReleaseMemObject': (I, [P]), 'clReleaseKernel': (I, [P]),
            'clReleaseProgram': (I, [P]), 'clReleaseCommandQueue': (I, [P]),
            'clReleaseContext': (I, [P]),
        }
        for name, (ret, args) in specs.items():
            fn = getattr(lib, name)
            fn.restype, fn.argtypes = ret, args
        count = U()
        check(lib.clGetPlatformIDs(0, None, C.byref(count)))
        platforms = (P * count.value)()
        check(lib.clGetPlatformIDs(count, platforms, None))
        choices = []
        for platform in platforms:
            n = U()
            if lib.clGetDeviceIDs(platform, 4, 0, None, C.byref(n)) != 0:
                continue
            devices = (P * n.value)()
            check(lib.clGetDeviceIDs(platform, 4, n, devices, None))
            for device in devices:
                name = C.create_string_buffer(1024)
                check(lib.clGetDeviceInfo(device, 0x102B, len(name), name, None))
                extensions = C.create_string_buffer(16384)
                check(lib.clGetDeviceInfo(device, 0x1030, len(extensions), extensions, None))
                memory = C.c_ulonglong()
                check(lib.clGetDeviceInfo(device, 0x101F, C.sizeof(memory), C.byref(memory), None))
                unified, units = U(), U()
                check(lib.clGetDeviceInfo(device, 0x1035, C.sizeof(unified), C.byref(unified), None))
                check(lib.clGetDeviceInfo(device, 0x1002, C.sizeof(units), C.byref(units), None))
                if b'cl_khr_fp64' in extensions.value:
                    choices.append((not unified.value, units.value, memory.value, device, name.value.decode()))
        if not choices:
            raise OpenCLError('No OpenCL GPU with double precision support is available')
        _, _, self.global_memory_bytes, device, self.name = max(choices)
        self.device = P(device)
        extensions=C.create_string_buffer(16384)
        check(lib.clGetDeviceInfo(device,0x1030,len(extensions),extensions,None))
        self.extensions=set(extensions.value.decode().split())
        allocation = C.c_ulonglong()
        check(lib.clGetDeviceInfo(device, 0x1010, C.sizeof(allocation), C.byref(allocation), None))
        self.max_allocation_bytes = allocation.value
        err = I()
        self.context = P(lib.clCreateContext(None, 1, C.byref(self.device), None, None, C.byref(err)))
        check(err.value)
        self.queue = P(lib.clCreateCommandQueue(self.context, self.device, 0, C.byref(err)))
        check(err.value)
        self.program = None
        self.kernels = {}

    def build(self, source):
        encoded = C.c_char_p(source.encode())
        err = C.c_int()
        self.program = C.c_void_p(self.lib.clCreateProgramWithSource(self.context, 1, C.byref(encoded), None, C.byref(err)))
        check(err.value)
        result = self.lib.clBuildProgram(self.program, 1, C.byref(self.device), b'-cl-std=CL1.2', None, None)
        if result:
            log = C.create_string_buffer(65536)
            self.lib.clGetProgramBuildInfo(self.program, self.device, 0x1183, len(log), log, None)
            raise OpenCLError(log.value.decode(errors='replace'))

    def buffer(self, value):
        size = value if isinstance(value, int) else np.asarray(value).nbytes
        if size > self.max_allocation_bytes:
            raise OpenCLError('OpenCL buffer requires %d bytes; device allocation limit is %d' %
                              (size, self.max_allocation_bytes))
        if isinstance(value, int):
            return Buffer(self, value)
        array = np.ascontiguousarray(value)
        buf = Buffer(self, array.nbytes)
        self.write(buf, array)
        return buf

    def write(self, buffer, array, offset=0):
        array = np.ascontiguousarray(array)
        if offset<0 or offset+array.nbytes > buffer.size:
            raise ValueError('OpenCL write exceeds allocation')
        if array.nbytes:
            check(self.lib.clEnqueueWriteBuffer(self.queue, buffer.handle, 1, offset, array.nbytes, C.c_void_p(array.ctypes.data), 0, None, None))

    def read(self, buffer, shape, dtype=np.float64, offset=0):
        out = np.empty(shape, dtype=dtype)
        if offset<0 or offset+out.nbytes > buffer.size:
            raise ValueError('OpenCL read exceeds allocation')
        if out.nbytes:
            check(self.lib.clEnqueueReadBuffer(self.queue, buffer.handle, 1, offset, out.nbytes, C.c_void_p(out.ctypes.data), 0, None, None))
        return out

    def run(self, name, count, *args, local_size=None):
        if not count:
            return
        if name not in self.kernels:
            err = C.c_int()
            kernel = C.c_void_p(self.lib.clCreateKernel(self.program, name.encode(), C.byref(err)))
            check(err.value)
            self.kernels[name] = kernel
        kernel = self.kernels[name]
        for i, arg in enumerate(args):
            value = arg.handle if isinstance(arg, Buffer) else (C.c_double(arg) if isinstance(arg, float) else C.c_int(arg))
            check(self.lib.clSetKernelArg(kernel, i, C.sizeof(value), C.byref(value)))
        local=None
        if local_size is not None:
            maximum=C.c_size_t()
            check(self.lib.clGetKernelWorkGroupInfo(kernel,self.device,0x11B0,C.sizeof(maximum),C.byref(maximum),None))
            group=1 << (min(int(local_size),maximum.value).bit_length()-1)
            count=((count+group-1)//group)*group
            local=C.c_size_t(group)
        size = C.c_size_t(count)
        check(self.lib.clEnqueueNDRangeKernel(self.queue, kernel, 1, None, C.byref(size),C.byref(local) if local is not None else None, 0, None, None))

    def finish(self):
        check(self.lib.clFinish(self.queue))

    def close(self):
        for kernel in getattr(self,'kernels',{}).values():
            self.lib.clReleaseKernel(kernel)
        if hasattr(self,'kernels'):
            self.kernels.clear()
        for attr, function in [('program', 'clReleaseProgram'), ('queue', 'clReleaseCommandQueue'), ('context', 'clReleaseContext')]:
            value = getattr(self, attr, None)
            if value:
                getattr(self.lib, function)(value)
                setattr(self, attr, None)

    def __del__(self):
        self.close()
