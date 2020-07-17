# system imports:
from abc import ABCMeta, abstractmethod
from functools import partial
import logging
from mypy_extensions import KwArg, VarArg # pip install mypy_extensions
import trio # pip install trio trio-typing
import trio.testing
from typing import Any, Callable, Coroutine, Iterator, List, Union, Type
import unittest

# mail_proto imports:
import itrustme
import smtp_proto as proto
import smtp_trio
from util import b2s, b64_encode_str

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
			
			# event loop exception handler testing is going to be tricky
			# create a custom Event object (PrintMoneyEvent)
			# smtp_trio.Server won't have an on_PrintMoneyEvent()
			# so it will throw an AttributeError.
			class PrintMoneyEvent ( proto.Event ):
				pass
			# here's what we need to send/recv our new custom verb that will generate the bogus event:
			@proto.request_verb ( 'XMONEY' )
			class PrintMoneyRequest ( proto.Request[proto.SuccessResponse] ):
				def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
					yield from proto.client_util.send_recv_done ( 'XMONEY\r\n' )
				def server_protocol ( self, server: proto.Server, moreargtext: str ) -> proto.RequestProtocolGenerator:
					with test.assertRaises ( AttributeError ):
						try:
							yield PrintMoneyEvent()
						except AttributeError as e:
							test.assertEqual ( e.args[0], "'TestServer' object has no attribute 'on_PrintMoneyEvent'" )
							raise
					raise proto.ResponseEvent ( 421, 'printer out of ink' )
			# finally see inside client_task() where we trigger all this to test it.
			
			async def test_pass (
				func: Callable[[],Coroutine[Any,Any,proto.Response]],
				responserepr: str,
				responsecls: Type[proto.Response] = proto.SuccessResponse,
			) -> None:
				try:
					r: Union[proto.Response,Exception] = await func()
				except Exception as e:
					r = e
				test.assertEqual ( repr ( r ), responserepr )
				test.assertEqual ( type ( r ), responsecls )
			
			async def test_fail (
				func: Callable[[],Coroutine[Any,Any,proto.Response]],
				responserepr: str,
				responsecls: Type[proto.Response] = proto.ErrorResponse,
			) -> None:
				try:
					r = await func()
				except Exception as e:
					test.assertEqual ( repr ( e ), responserepr )
					test.assertEqual ( type ( e ), responsecls )
				else:
					test.fail ( f'function returned {r=} but was expecting it to throw {responsrepr}' )
			
			TEST_FUNC = Union[
				Callable[[],Coroutine[Any,Any,proto.ResponseType]],
				#Callable[[],Coroutine[Any,Any,proto.SuccessResponse]],
				#Callable[[],Coroutine[Any,Any,proto.ExpnResponse]],
				#Callable[[],Coroutine[Any,Any,proto.EhloResponse]],
			]
			
			async def test_helo_first ( func: TEST_FUNC[proto.ResponseType] ) -> None:
				await test_fail (
					func,
					"smtp_proto.ErrorResponse(503, 'Say HELO first')",
				)
			
			async def test_dup_helo ( func: TEST_FUNC[proto.ResponseType] ) -> None:
				await test_fail (
					func,
					"smtp_proto.ErrorResponse(503, 'you already said HELO RFC1869#4.2')",
				)
			
			async def test_must_auth ( func: TEST_FUNC[proto.ResponseType] ) -> None:
				await test_fail (
					func,
					"smtp_proto.ErrorResponse(513, 'Must authenticate')",
				)
			
			async def client_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'test_client_server.client_task' )
				xport = smtp_trio.Transport ( stream )
				xport.ssl_context = trust.client_context()
				tls = False
				cli = smtp_trio.Client ( xport, tls, 'milliways.local' )
				
				async def test_bad_param ( bad_param: str, bad_code: int, errtext: str ) -> None:
					class BadRequest ( proto.RsetRequest ): # << base class doesn't matter much with this test...
						bad_param: str
						def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
							#log = logger.getChild ( 'BadStartTlsRequest.client_protocol' )
							yield from proto.client_util.send_recv_ok (
								f'{self.bad_param} FUBAR\r\n',
							)
					r = BadRequest()
					r.bad_param = bad_param
					r.base_response = None
					await test_fail ( lambda: cli._request ( r ), # type: ignore
						f"smtp_proto.ErrorResponse({bad_code!r}, '{errtext}')",
					)
				
				try:
					await test_pass (
						cli.greeting,
						"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
					)
					
					await test_fail (
						lambda: cli._request ( PrintMoneyRequest() ), # type: ignore
						"smtp_proto.ErrorResponse(421, 'printer out of ink')",
					)
					
					await test_helo_first ( cli.starttls )
					await test_helo_first ( lambda: cli.expn ( 'ford' ) )
					await test_helo_first ( lambda: cli.mail_from ( 'ceo_test.com' ) )
					await test_helo_first ( lambda: cli.rcpt_to ( 'to@test.com' ) )
					await test_helo_first ( lambda: cli.data ( b'foo' ) )
					
					# NOTE we can't (currently) test a successful HELO and EHLO in a single session, so I'll test HELO in a different unittest
					r1 = await cli.ehlo ( 'localhost' )
					test.assertEqual ( type ( r1 ), proto.EhloResponse )
					test.assertEqual ( r1.code, 250 )
					test.assertEqual ( sorted ( r1.esmtp_features.items() ), [
						( '8BITMIME', '' ),
						( 'FOO', 'BAR' ),
						( 'PIPELINING', '' ),
						( 'STARTTLS', '' ),
					] )
					#test.assertEqual ( sorted ( r1.esmtp_auth ), [ 'LOGIN', 'PLAIN' ] )
					
					await test_dup_helo ( lambda: cli.helo ( 'localhost' ) )
					await test_dup_helo ( lambda: cli.ehlo ( 'localhost' ) )
					
					test.assertEqual ( repr ( await cli.rset() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					await test_must_auth ( lambda: cli.expn ( 'ford' ) )
					await test_must_auth ( lambda: cli.mail_from ( 'cel@test.com' ) )
					await test_must_auth ( lambda: cli.rcpt_to ( 'to@test.com' ) )
					await test_must_auth ( lambda: cli.data ( b'foo' ) )
					
					if True:
						# make sure server doesn't allow us to use tls-required AUTH method outside of TLS
						await test_fail (
							lambda: cli.auth_login ( 'Arthur', 'Dent' ),
							"smtp_proto.ErrorResponse(535, 'SSL/TLS connection required')",
						)
					
					await test_bad_param ( 'STARTTLS FUBAR', 501, 'Syntax error (no extra parameters allowed)' )
					
					test.assertEqual (
						repr ( await cli.starttls() ),
						"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
					)
					
					await test_helo_first ( lambda: cli.auth_login ( 'Authur', 'Dent' ) )
					
					test.assertEqual (
						repr ( await cli.helo ( 'localhost' ) ),
						"smtp_proto.SuccessResponse(250, 'milliways.local greets localhost')",
					)
					
					await test_fail ( lambda: cli.starttls(),
						"smtp_proto.ErrorResponse(535, 'Command not available in SSL/TLS')",
					)
					
					if True:
						await test_bad_param ( 'AUTH LOGIN FUBAR', 501, 'Syntax error (no extra parameters allowed)' )
						await test_bad_param ( 'DATA FUBAR', 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
						await test_bad_param ( 'QUIT FUBAR', 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
						await test_bad_param ( 'RSET FUBAR', 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
						await test_bad_param ( 'X123', 500, 'Command not recognized' ) # <<< trigger command parsing regex failure
					
					if True: # request a non-existent AUTH mechanism
						class AuthFubarRequest ( proto.Request[proto.SuccessResponse] ):
							def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
								log = logger.getChild ( 'AuthFubarRequest.client_protocol' )
								yield from proto.client_util.send_recv_done ( f'AUTH FUBAR\r\n' )
							def server_protocol ( self, server: proto.Server, moreargtext: str ) -> proto.RequestProtocolGenerator:
								assert False
						with test.assertRaises ( proto.ErrorResponse ):
							try:
								await cli._request ( AuthFubarRequest() )
							except proto.ErrorResponse as e:
								test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(504, 'Unrecognized authentication mechanism: FUBAR')" )
								raise
					
					if True: # construct an invalid AUTH PLAIN request to trigger specific error handling in the server-side protocol
						class BadAuthPlain1Request ( proto.AuthPlain1Request ):
							def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
								log = logger.getChild ( 'HeloRequest.client_protocol' )
								yield from proto.client_util.send_recv_done ( f'AUTH PLAIN BAADF00D\r\n' )
						with test.assertRaises ( proto.ErrorResponse ):
							try:
								await cli._request ( BadAuthPlain1Request ( 'baad', 'f00d' ) )
							except proto.ErrorResponse as e:
								test.assertEqual ( repr ( e ),
									"smtp_proto.ErrorResponse(501, 'malformed auth input RFC4616#2')"
								)
								raise
					
					if False:
						class BadAuthLoginRequest ( proto.AuthLoginRequest ):
							def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
								#log = logger.getChild ( 'AuthLoginRequest.client_protocol' )
								yield from proto.client_util.send_recv_ok ( 'AUTH LOGIN FUBAR\r\n' )
								yield from proto.client_util.send_recv_ok ( f'{b64_encode_str(self.uid)}\r\n' )
								yield from proto.client_util.send_recv_done ( f'{b64_encode_str(self.pwd)}\r\n' )
						r3 = BadAuthLoginRequest ( 'foo', 'bar' )
						with test.assertRaises ( proto.ErrorResponse ):
							try:
								await cli._request ( r3 )
							except proto.ErrorResponse as e:
								test.assertEqual ( repr ( e ),
									"smtp_proto.ErrorResponse(501, 'Syntax error (no extra parameters allowed)')",
								)
								raise
					
					if True:
						class BadAuthLoginRequest2 ( proto.AuthLoginRequest ):
							def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
								#log = logger.getChild ( 'AuthLoginRequest.client_protocol' )
								yield from proto.client_util.send_recv_ok ( 'AUTH LOGIN\r\n' )
								yield from proto.client_util.send_recv_ok ( 'BADF00D\r\n' )
								yield from proto.client_util.send_recv_done ( 'BADF00D\r\n' )
						r4 = BadAuthLoginRequest2 ( 'foo', 'bar' )
						with test.assertRaises ( proto.ErrorResponse ):
							try:
								await cli._request ( r4 )
							except proto.ErrorResponse as e:
								test.assertEqual ( repr ( e ),
									"smtp_proto.ErrorResponse(501, 'malformed auth input RFC4616#2')"
								)
								raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.auth_login ( 'Arthur', 'Dent' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(535, 'Authentication failed')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.auth_plain1 ( 'Ford', 'Prefect' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(535, 'Authentication failed')" )
							raise
					
					test.assertEqual (
						repr ( await cli.auth_plain2 ( 'Zaphod', 'Beeblebrox' ) ),
						"smtp_proto.SuccessResponse(235, 'Authentication successful')",
					)
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.auth_plain1 ( 'Ford', 'Prefect' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'already authenticated (RFC4954#4 Restrictions)')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						r = proto.ExpnRequest ( 'ford' )
						r.mailbox = ''
						try:
							await cli._request ( r )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'missing required mailbox parameter')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.expn ( 'allusers' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'Access Denied!')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.vrfy ( 'admin@test.com' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'Access Denied!')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						class MaleFromRequest ( proto.MailFromRequest ):
							def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
								yield from proto.client_util.send_recv_done ( f'MALE FROM:<{self.mail_from}>\r\n' )
						try:
							await cli._request ( MaleFromRequest ( 'foo@bar.com' ) )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(500, 'Command not recognized')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						class MailFrumRequest ( proto.MailFromRequest ):
							def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
								yield from proto.client_util.send_recv_done ( f'MAIL FRUM:<{self.mail_from}>\r\n' )
						try:
							await cli._request ( MailFrumRequest ( 'foo@bar.com' ) )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed MAIL input')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'no from address received yet')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.mail_from ( 'ceo@test.com' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'address rejected')" )
							raise
					
					test.assertEqual ( repr ( await cli.mail_from ( 'from@test.com' ) ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					with test.assertRaises ( proto.ErrorResponse ):
						class RcptTooRequest ( proto.RcptToRequest ):
							def client_protocol ( self, client: proto.Client ) -> proto.RequestProtocolGenerator:
								yield from proto.client_util.send_recv_done ( f'RCPT TOO:<{self.rcpt_to}>\r\n' )
						try:
							await cli._request ( RcptTooRequest ( 'foo@bar.com' ) )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed RCPT input')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'no rcpt address(es) received yet')" )
							raise
					
					with test.assertRaises ( proto.ErrorResponse ):
						try:
							await cli.rcpt_to ( 'zaphod@beeblebrox.com' )
						except proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'address rejected')" )
							raise
					
					test.assertEqual ( repr ( await cli.rcpt_to ( 'to@test.com' ) ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					test.assertEqual ( repr ( await cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test.\r\n'
						b'.<<< Evil line beginning with a dot\r\n'
						b'Last line of message\r\n'
						b'.' # << trigger an edge case inside DataRequest.client_protocol() for code coverage reasons
					) ), "smtp_proto.SuccessResponse(250, 'Message accepted for delivery')" )
					
					test.assertEqual ( repr ( await cli.rset() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					test.assertEqual ( repr ( await cli.noop() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					test.assertEqual ( repr ( await cli.quit() ), "smtp_proto.SuccessResponse(221, 'Closing connection')" )
				
				except proto.ErrorResponse as e: # pragma: no cover
					log.exception ( f'server error: {e=}' )
				except proto.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					await cli.close()
			
			async def server_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.server_task' )
				class TestServer ( smtp_trio.Server ):
					async def on_EhloAcceptEvent ( self, event: proto.EhloAcceptEvent ) -> None:
						event.esmtp_features['FOO'] = 'BAR'
						event.accept()
					
					async def on_StartTlsAcceptEvent ( self, event: proto.StartTlsAcceptEvent ) -> None:
						event.accept()
					
					async def on_AuthEvent ( self, event: proto.AuthEvent ) -> None:
						if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
							event.accept()
						else:
							event.reject()
					
					async def on_MailFromEvent ( self, event: proto.MailFromEvent ) -> None:
						if event.mail_from == 'from@test.com':
							event.accept()
						else:
							event.reject()
					
					async def on_RcptToEvent ( self, event: proto.RcptToEvent ) -> None:
						if event.rcpt_to.endswith ( '@test.com' ):
							event.accept()
						else:
							event.reject()
					
					async def on_CompleteEvent ( self, event: proto.CompleteEvent ) -> None:
						test.assertEqual ( event.mail_from, 'from@test.com' )
						test.assertEqual ( event.rcpt_to, [ 'to@test.com' ] )
						lines = b''.join ( event.data ).split ( b'\r\n' )
						test.assertEqual ( lines[0], b'From: from@test.com' )
						test.assertEqual ( lines[1], b'To: to@test.com' )
						test.assertEqual ( lines[2], b'Subject: Test email' )
						test.assertEqual ( lines[3], b'Date: 2000-01-01T00:00:00Z' )
						test.assertEqual ( lines[4], b'' )
						test.assertEqual ( lines[5], b'This is a test.' )
						test.assertEqual ( lines[6], b'.<<< Evil line beginning with a dot' )
						test.assertEqual ( lines[7], b'Last line of message' )
						test.assertEqual ( lines[8], b'.' )
						test.assertEqual ( lines[9], b'' )
						with test.assertRaises ( IndexError ):
							test.assertEqual ( lines[10], b'?????' )
						event.accept() # or .reject()
				
				xport = smtp_trio.Transport ( stream )
				xport.ssl_context = trust.server_context()
				tls = False
				srv = TestServer ( xport, tls, 'milliways.local' )
				
				try:
					await srv.run()
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
