from typing import Iterable, Union
from functools import partial

from k2000.utils import grouper


def encode_n(value: Union[int, bytes], num_bytes: int, n: int) -> bytes:
    """
    Given a single byte value on [0, 255], return a bytestring
    of length `num_bytes` that contains the value packed into
    successive n-bit chunks, right-aligned in each byte.
    """
    if isinstance(value, int):
        if value < 0:
            raise ValueError(
                f"Can't encode negative value {repr(value)} in {num_bytes} {n}-bit bytes."
            )
        if value >= (2 ** (n * num_bytes)):
            raise ValueError(f"Can't encode value {repr(value)} in {num_bytes} {n}-bit bytes.")
    elif isinstance(value, bytes):
        value = int.from_bytes(value, "big")
    else:
        raise TypeError(
            f"Expected either int or bytes to convert to {n}-bit format, but got: {type(value)}!"
        )
    return bytes([(value >> (n * i)) & ((2**n) - 1) for i in reversed(range(num_bytes))])


encode = {i: partial(encode_n, n=i) for i in range(1, 8)}


def bit_array_to_int(bit_array: Iterable[bool]) -> int:
    value = 0
    for i, bit in enumerate(reversed(list(bit_array))):
        value |= int(bit) << i
    return value


def decode_n(value: bytes, n: int) -> bytes:
    """
    Given an n-bit encoded bytestring, return an 8-bit encoded bytestring.
    """
    # Yes, this creates a Python object for every bit of the input data.
    # Could this be more efficient? For sure.
    bits = []
    for input_byte in value:
        if input_byte >> n != 0:
            raise ValueError(
                f"decode_n(n={n}) received a byte with bits "
                f"set above the {n}th: {bin(input_byte)}"
            )
        for i in reversed(range(n)):
            bits.append(bool(input_byte & (1 << i)))

    while len(bits) % 8 != 0:
        bits.insert(0, False)

    return bytes([bit_array_to_int(bit_array) for bit_array in list(grouper(bits, 8))])


decode = {i: partial(decode_n, n=i) for i in range(1, 8)}


def encode_data_field(value: bytes, n: int) -> bytes:
    """Pack a `data` FIELD for transmission, LEFT-aligned with trailing zeros.

    The counterpart to :func:`decode_data_field`, and broken in the same way
    before this existed. `encode_n` treats the payload as one big integer and
    slices `n`-bit groups from the top of a fixed-width field, which *right*-
    aligns it — correct for the numeric fields, wrong for the data field.

    The spec (ch. 30, "Data Formats") describes the bit-stream form as taking the
    data's bits "starting from the left, slicing off groups of 7 bits", and "the
    trailing bits are set to zero". Right-aligning instead pads the front, so
    every group is shifted and the instrument receives a different object than the
    one you meant to send.

    It was invisible in nibble form, where 2 output bytes per input byte always
    divides evenly. The manual's worked example makes the difference plain: 4 data
    bytes must pack to `27 76 00 12 48`, and the old path produced
    `04 7e 60 02 29`.

    This matters more than the decode bug did: `client.write_object` transmits in
    bit-stream form, so writing any object — a macro table, a program — would have
    sent a mis-packed payload into the object database.
    """
    bits = []
    for byte in value:
        for i in reversed(range(8)):
            bits.append(bool(byte & (1 << i)))
    # Pad the TAIL to a whole number of n-bit groups, never the head.
    while len(bits) % n != 0:
        bits.append(False)
    return bytes([bit_array_to_int(bits[start : start + n])
                  for start in range(0, len(bits), n)])


def decode_data_field(value: bytes, n: int, size: int) -> bytes:
    """Decode a `data` FIELD, which is left-aligned — unlike a numeric field.

    The K2 SysEx spec (K2vx Musician's Guide ch. 30, "Data Formats") uses two
    different bit alignments, and `decode_n` implements only one of them:

    * **Numeric fields** (`type`, `idno`, `size`, `offs`) are *right* justified —
      "The significant bits are right justified in a field." `decode_n` front-pads
      to suit, which is correct here.
    * **The `data` field** in bit-stream form is *left* aligned: the payload is
      made "starting from the left, slicing off groups of 7 bits", and "the
      trailing bits are set to zero".

    Front-padding a left-aligned stream shifts every byte. It goes unnoticed in
    nibble form because 2 MIDI bytes per data byte always lands on a multiple of
    8 — but 722 data bytes in bit-stream form is 5776 bits carried in 826 MIDI
    bytes, i.e. 5782 bits, so `decode_n` inserts 2 leading zero bits and every
    decoded byte is wrong by a 2-bit shift. The two forms then disagree
    completely for the same object, which reads like a protocol subtlety and is
    not one.

    Verified against the manual's own worked example (4F D8 01 29 as both
    `04 0F 0D 08 00 01 02 09` and `27 76 00 12 48`) and against the instrument:
    both forms of one 722-byte program now decode identically, checksums valid.
    """
    bits = []
    for input_byte in value:
        if input_byte >> n != 0:
            raise ValueError(
                f"decode_data_field(n={n}) received a byte with bits "
                f"set above the {n}th: {bin(input_byte)}"
            )
        for i in reversed(range(n)):
            bits.append(bool(input_byte & (1 << i)))
    # Take whole bytes from the LEFT and drop the trailing pad, rather than
    # padding the front and taking from the right.
    out = bytearray()
    for start in range(0, len(bits) - 7, 8):
        out.append(bit_array_to_int(bits[start : start + 8]))
        if len(out) == size:
            break
    return bytes(out)
