import base64
from typing import Union

BYTES = Union[bytes,bytearray,memoryview]
bytes_types = ( bytes, bytearray, memoryview )

def b2s ( b: BYTES, encoding: str = 'us-ascii', errors: str = 'strict' ) -> str:
	return bytes ( b ).decode ( encoding, errors )

def s2b ( s: str, encoding: str = 'us-ascii', errors: str = 'strict' ) -> bytes:
	return s.encode ( encoding, errors )

def b64_encode_str ( s: str ) -> str:
	return b2s ( base64.b64encode ( s2b ( s ) ) )

def b64_decode_str ( s: str ) -> str:
	return b2s ( base64.b64decode ( s2b ( s ) ) )
