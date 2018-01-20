# -*- cofing: utf-8 -*-

import base64
import binascii
import math

__all__ = ["base64_encode", "base64_decode", "base41_encode", "base41_decode"]

BASE41_CHARSET = b"+,-.0123456789_abcdefghijklmnopqrstuvwxyz"
BASE41_PADDING = b"="

def _chunk(b, size):
    for i in range(math.ceil(len(b) / size)):
        yield b[size * i:size * (i + 1)]

def _convert_decimal(d, base):
    if d == 0:
        return [0]

    output = []

    while d > 0:
        rem = d % base
        d //= base
        output.append(rem)

    return output

def _convert_to_decimal(digits, base):
    result = power = 0

    for digit in digits[::-1]:
        result += digit * base ** power
        power += 1

    return result

def _bytes_to_decimal(b):
    result = power = 0

    for i in b[::-1]:
        result += (i + 1) * 256 ** power
        power += 1

    return result

def _encode_bytes(b, m, n, charset, padding):
    base = len(charset)
    output = b""

    for chunk in _chunk(b, m):
        decimal = _bytes_to_decimal(chunk)
        encoded = b"".join(charset[i:i + 1] for i in _convert_decimal(decimal, base)[::-1])
        encoded += (n - len(encoded)) * padding
        output += encoded

    return output

def _decode_bytes(b, m, n, charset, padding):
    base = len(charset)
    output = b""
    max_decimal = 0

    for i in range(m):
        max_decimal += 256 * 256 ** i

    for chunk in _chunk(b, n):
        if len(chunk) != n:
            raise ValueError("Invalid padding")

        chunk = chunk.rstrip(padding)

        digits = [charset.index(i) for i in chunk]
        decimal = _convert_to_decimal(digits, base)

        if decimal > max_decimal:
            raise ValueError("Encoding range exceeded")

        if decimal > 256:
            b2 = decimal % 256 - 1

            if b2 == -1:
                b2 = 255

            b1 = (decimal - b2) // 256 % 256 - 1

            if b1 == -1:
                b1 = 255

            output += bytes([b1, b2])
        elif decimal == 256:
            output += bytes([255])
        else:
            output += bytes([decimal % 256 - 1])

    return output

def base64_encode(b):
    try:
        return base64.urlsafe_b64encode(b)
    except binascii.Error as e:
        raise ValueError("binascii.Error: %s" % (e,))

def base64_decode(b):
    try:
        return base64.urlsafe_b64decode(b)
    except binascii.Error as e:
        raise ValueError("binascii.Error: %s" % (e,))

def base41_encode(b):
    return _encode_bytes(b, 2, 3, BASE41_CHARSET, BASE41_PADDING)

def base41_decode(b):
    return _decode_bytes(b, 2, 3, BASE41_CHARSET, BASE41_PADDING)