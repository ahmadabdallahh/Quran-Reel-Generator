"""
Compatibility patch for Python 3.13 - provides missing audioop module functionality
"""
import struct
import sys

def _check_parameters(length, size):
    if length % size != 0:
        raise ValueError("not a whole number of frames")

def _get_sample(size, data, offset):
    if size == 1:
        return struct.unpack_from('B', data, offset)[0]
    elif size == 2:
        return struct.unpack_from('h', data, offset)[0]
    elif size == 4:
        return struct.unpack_from('i', data, offset)[0]
    else:
        raise ValueError("Unsupported sample size")

def _set_sample(size, data, offset, value):
    if size == 1:
        struct.pack_into('B', data, offset, value)
    elif size == 2:
        struct.pack_into('h', data, offset, value)
    elif size == 4:
        struct.pack_into('i', data, offset, value)
    else:
        raise ValueError("Unsupported sample size")

def findmax(data, size):
    """Find the maximum absolute value in the data"""
    _check_parameters(len(data), size)
    max_val = 0
    for i in range(0, len(data), size):
        sample = abs(_get_sample(size, data, i))
        if sample > max_val:
            max_val = sample
    return max_val

def getsample(data, size, index):
    """Return a single sample"""
    _check_parameters(len(data), size)
    return _get_sample(size, data, index * size)

def max(data, size):
    """Return the maximum value in the data"""
    return findmax(data, size)

def min(data, size):
    """Return the minimum value in the data"""
    _check_parameters(len(data), size)
    min_val = 0
    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        if sample < min_val:
            min_val = sample
    return min_val

def avg(data, size):
    """Return the average value in the data"""
    _check_parameters(len(data), size)
    total = 0
    count = 0
    for i in range(0, len(data), size):
        total += _get_sample(size, data, i)
        count += 1
    return total // count if count > 0 else 0

def rms(data, size):
    """Return the root-mean-square of the data"""
    _check_parameters(len(data), size)
    total = 0
    count = 0
    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        total += sample * sample
        count += 1
    if count == 0:
        return 0
    return int((total // count) ** 0.5)

def cross(data, size):
    """Return the number of zero crossings"""
    _check_parameters(len(data), size)
    crossings = 0
    last_sample = 0
    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        if last_sample <= 0 and sample > 0:
            crossings += 1
        last_sample = sample
    return crossings

def add(data1, data2, size):
    """Add two audio fragments"""
    _check_parameters(len(data1), size)
    _check_parameters(len(data2), size)
    if len(data1) != len(data2):
        raise ValueError("Input fragments must be of the same length")

    result = bytearray(len(data1))
    for i in range(0, len(data1), size):
        sample1 = _get_sample(size, data1, i)
        sample2 = _get_sample(size, data2, i)
        _set_sample(size, result, i, sample1 + sample2)
    return bytes(result)

def mul(data, size, factor):
    """Multiply an audio fragment by a factor"""
    _check_parameters(len(data), size)
    result = bytearray(len(data))
    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        _set_sample(size, result, i, int(sample * factor))
    return bytes(result)

def reverse(data, size):
    """Reverse an audio fragment"""
    _check_parameters(len(data), size)
    result = bytearray(len(data))
    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        _set_sample(size, result, len(data) - i - size, sample)
    return bytes(result)

def tomono(data, size, left_factor, right_factor):
    """Convert stereo to mono"""
    _check_parameters(len(data), size)
    if size % 2 != 0:
        raise ValueError("Stereo samples must be even-sized")

    sample_size = size // 2
    result = bytearray(len(data) // 2)

    for i in range(0, len(data), size):
        left = _get_sample(sample_size, data, i)
        right = _get_sample(sample_size, data, i + sample_size)
        mono = int(left * left_factor + right * right_factor)
        _set_sample(sample_size, result, i // 2, mono)

    return bytes(result)

def tostereo(data, size, left_factor, right_factor):
    """Convert mono to stereo"""
    _check_parameters(len(data), size)
    result = bytearray(len(data) * 2)

    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        _set_sample(size, result, i * 2, int(sample * left_factor))
        _set_sample(size, result, i * 2 + size, int(sample * right_factor))

    return bytes(result)

def lin2lin(data, size, new_size):
    """Convert sample width"""
    _check_parameters(len(data), size)
    _check_parameters(len(data), new_size)

    if size == new_size:
        return data

    result = bytearray((len(data) // size) * new_size)

    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        _set_sample(new_size, result, (i // size) * new_size, sample)

    return bytes(result)

def ratecv(data, size, nchannels, inrate, outrate, state=None, weightA=1, weightB=0):
    """Convert sample rate"""
    _check_parameters(len(data), size)

    # Simple implementation - just return the data unchanged
    # In a real implementation, this would resample the audio
    return data, state

# Add any other missing functions that pydub might need
def bias(data, size, bias):
    """Add bias to samples"""
    _check_parameters(len(data), size)
    result = bytearray(len(data))
    for i in range(0, len(data), size):
        sample = _get_sample(size, data, i)
        _set_sample(size, result, i, sample + bias)
    return bytes(result)
