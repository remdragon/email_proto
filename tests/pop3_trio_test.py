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
				xport = pop3_trio.Transport ( stream )
				xport.ssl_context = trust.client_context()
				tls = False
				cli = pop3_trio.Client ( xport, tls, 'milliways.local' )
				try:
					r1 = await cli.greeting()
					test.assertEqual (
						repr ( r1 ),
						"pop3_proto.GreetingResponse(True, 'POP3 server ready <1896.697170952@dbc.mtview.ca.us>')",
					)
					test.assertEqual ( r1.apop_challenge, '<1896.697170952@dbc.mtview.ca.us>' )
					assert r1.apop_challenge is not None # make mypy happy
					
					test.assertEqual (
						repr ( await cli.capa() ),
						"pop3_proto.CapaResponse(True, 'Capability list follows', capa={'STLS': ''})",
					)
					
					test.assertEqual (
						repr ( await cli.apop ( 'mrose', 'tanstaaf', r1.apop_challenge ) ),
						"pop3_proto.SuccessResponse(True, 'maildrop has 42 messages (1492 octets)')",
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
					locked: bool = False
					
					async def on_ApopChallengeEvent ( self, event: proto.ApopChallengeEvent ) -> None:
						event.accept ( '<1896.697170952@dbc.mtview.ca.us>' ) # example from RFC1939#7 example
					
					async def on_StartTlsAcceptEvent ( self, event: proto.StartTlsAcceptEvent ) -> None:
						event.accept()
					
					async def on_ApopAuthEvent ( self, event: proto.ApopAuthEvent ) -> None:
						if event.uid == 'mrose':
							digest = proto.apop_hash ( event.challenge, 'tanstaaf' )
							test.assertEqual ( digest, event.digest )
							event.accept()
							return
						event.reject()
					
					async def on_LockMaildropEvent ( self, event: proto.LockMaildropEvent ) -> None:
						log2 = log.getChild ( 'TestServer.on_LockMaildropEvent' )
						log.debug ( f'{event=}' )
						test.assertFalse ( self.locked )
						self.locked = True
						event.accept ( 42, 1492 )
				
				xport = pop3_trio.Transport ( stream )
				xport.ssl_context = trust.server_context()
				tls = False
				srv = TestServer ( xport, tls, 'milliways.local' )
				
				try:
					await srv.run()
				except proto.Closed:
					pass
				finally:
					await srv.close()
				#test.assertFalse ( srv.locked ) # TODO FIXME: need to implement fail-safe maildrop unlock
			
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
