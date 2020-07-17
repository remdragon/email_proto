# python imports:
import logging
from pathlib import Path
import sys
import trio # pip install trio trio-typing
import unittest

if __name__ == '__main__': # pragma: no cover
	sys.path.append ( str ( Path ( __file__ ).parent.parent.absolute() ) )

# email_proto imports:
import transport
from util import BYTES

logger = logging.getLogger ( __name__ )

class Tests ( unittest.TestCase ):
	def test_coverage ( self ) -> None:
		async def _test() -> None:
			class ST ( transport.SyncTransport ):
				def read ( self ) -> bytes:
					return super().read()
				def write ( self, data: BYTES ) -> None:
					super().write ( data )
				def starttls_client ( self, server_hostname: str ) -> None:
					super().starttls_client ( server_hostname )
				def starttls_server ( self ) -> None:
					super().starttls_server()
				def close ( self ) -> None:
					super().close()
			st = ST()
			with self.assertRaises ( NotImplementedError ):
				st.read()
			with self.assertRaises ( NotImplementedError ):
				st.write ( b'foo' )
			with self.assertRaises ( NotImplementedError ):
				st.starttls_client ( 'localhost' )
			with self.assertRaises ( NotImplementedError ):
				st.starttls_server()
			with self.assertRaises ( NotImplementedError ):
				st.close()
			class AT ( transport.AsyncTransport ):
				async def read ( self ) -> bytes:
					return await super().read()
				async def write ( self, data: BYTES ) -> None:
					await super().write ( data )
				async def starttls_client ( self, server_hostname: str ) -> None:
					await super().starttls_client ( server_hostname )
				async def starttls_server ( self ) -> None:
					await super().starttls_server()
				async def close ( self ) -> None:
					await super().close()
			at = AT()
			with self.assertRaises ( NotImplementedError ):
				await at.read()
			with self.assertRaises ( NotImplementedError ):
				await at.write ( b'foo' )
			with self.assertRaises ( NotImplementedError ):
				await at.starttls_client ( 'localhost' )
			with self.assertRaises ( NotImplementedError ):
				await at.starttls_server()
			with self.assertRaises ( NotImplementedError ):
				await at.close()
		trio.run ( _test )

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()