# system imports:
from abc import ABCMeta, abstractmethod
from functools import partial
import logging
import trio # pip install trio trio-typing
import trio.testing
from typing import Iterator
import unittest

# mail_proto imports:
import itrustme
import pop3_proto as proto
import pop3_trio
from util import b2s

logger = logging.getLogger ( __name__ )

trust = itrustme.ServerOnly (
	server_hostname = 'milliways.local',
)

class Tests ( unittest.TestCase ):
	def test_client_server ( self ) -> None:
		test = self
		self.maxDiff = None
		
		async def _test() -> None:
			thing1, thing2 = trio.testing.lockstep_stream_pair()
			
			async def client_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'test_client_server.client_task' )
				cli = pop3_trio.Client()
				try:
					cli.ssl_context = trust.client_context()
					cli.stream = stream
					
					test.assertEqual (
						repr ( await cli._connect ( False ) ),
						"pop3_proto.SuccessResponse(True, 'POP3 server ready <CHALLENGE>')",
					)
					self.assertEqual (
						repr ( await cli.capa() ),
						"pop3_proto.CapaResponse(True, 'Capability list follows', capa={'STLS': ''})",
					)
					test.assertEqual ( repr ( await cli.rset() ), "pop3_proto.SuccessResponse(True, 'TODO FIXME')" )
					test.assertEqual ( repr ( await cli.noop() ), "pop3_proto.SuccessResponse(True, 'TODO FIXME')" )
					test.assertEqual ( repr ( await cli.quit() ), "pop3_proto.SuccessResponse(True, 'Closing connection')" )
				
				except proto.ErrorResponse as e: # pragma: no cover
					log.exception ( f'server error: {e=}' )
				except proto.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					await cli.close()
			
			async def server_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'test_client_server.server_task' )
				class TestServer ( pop3_trio.Server ):
					async def on_StartTlsAcceptEvent ( self, event: proto.StartTlsAcceptEvent ) -> None:
						event.accept()
				
				srv = TestServer ( 'milliways.local' )
				
				apop_challenge = '<CHALLENGE>' # NOTE: NEVER do this in production, this is only useful for testing
				try:
					srv.ssl_context = trust.server_context()
					await srv.run ( stream, False, apop_challenge )
				except proto.Closed:
					pass
				finally:
					await srv.close()
			
			async with trio.open_nursery() as nursery:
				nursery.start_soon ( client_task, thing1 )
				nursery.start_soon ( server_task, thing2 )
		
		trio.run ( _test )
	
	def test_pipelining ( self ) -> None:
		''' TOOD FIXME: use server but raw sockets on the client side to batch submit a bunch of commands to verify pipelining works correctly '''

if __name__ == '__main__':
	logging.basicConfig (
		level = logging.DEBUG,
	)
	unittest.main()
