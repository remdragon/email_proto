# system imports:
from abc import ABCMeta, abstractmethod
import logging
import trio # pip install trio trio-typing
import trio.testing
from typing import Iterator
import unittest

# mail_proto imports:
import itrustme
import smtp_proto
import smtp_trio

logger = logging.getLogger ( __name__ )

b2s = smtp_proto.b2s

trust = itrustme.ServerOnly (
	server_hostname = 'milliways.local',
)

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ) -> None:
		test = self
		self.maxDiff = None
		
		async def _test() -> None:
			thing1, thing2 = trio.testing.lockstep_stream_pair()
			
			async def client_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.client_task' )
				cli = smtp_trio.Client()
				try:
					cli.ssl_context = trust.client_context()
					cli.stream = stream
					
					test.assertEqual ( repr ( await cli._connect ( False ) ), "smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')" )
					
					# NOTE we can't (currently) test a successful HELO and EHLO in a single session, so I'll test HELO in a different unittest
					r = await cli.ehlo ( 'localhost' )
					test.assertEqual ( type ( r ), smtp_proto.EhloResponse )
					test.assertEqual ( r.code, 250 )
					test.assertEqual ( sorted ( r.lines ), [
						'8BITMIME',
						#'AUTH PLAIN LOGIN', # not available because we're not encrypted yet
						'FUBAR',
						'PIPELINING',
						'STARTTLS',
						'milliways.local greets localhost',
					] )
					self.assertTrue ( r.esmtp_8bitmime )
					#test.assertEqual ( sorted ( r.esmtp_auth ), [ 'LOGIN', 'PLAIN' ] )
					self.assertTrue ( r.esmtp_pipelining )
					self.assertTrue ( r.esmtp_starttls )
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.helo ( 'localhost' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'you already said HELO RFC1869#4.2')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.ehlo ( 'localhost' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'you already said HELO RFC1869#4.2')" )
							raise
					test.assertEqual ( repr ( await cli.rset() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					test.assertEqual (
						repr ( await cli.starttls() ),
						"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
					)
					
					if True: # request a non-existent AUTH mechanism
						class AuthFubarRequest ( smtp_proto.Request ):
							def _client_protocol ( self, client: smtp_proto.Client ) -> smtp_proto.RequestProtocolGenerator:
								log = logger.getChild ( 'AuthFubarRequest._client_protocol' )
								yield from smtp_proto._client_proto_send_recv_done ( f'AUTH FUBAR\r\n' )
							def _server_protocol ( self, server: smtp_proto.Server, moreargtext: str ) -> smtp_proto.RequestProtocolGenerator:
								assert False
						with test.assertRaises ( smtp_proto.ErrorResponse ):
							try:
								await cli._send_recv ( AuthFubarRequest() )
							except smtp_proto.ErrorResponse as e:
								test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(504, 'Unrecognized authentication mechanism: FUBAR')" )
								raise
					
					if True: # construct an invalid AUTH PLAIN request to trigger specific error handling in the server-side protocol
						class BadAuthPlain1Request ( smtp_proto.AuthPlain1Request ):
							def _client_protocol ( self, client: smtp_proto.Client ) -> smtp_proto.RequestProtocolGenerator:
								log = logger.getChild ( 'HeloRequest._client_protocol' )
								yield from smtp_proto._client_proto_send_recv_done ( f'AUTH PLAIN BAADF00D\r\n' )
						with test.assertRaises ( smtp_proto.ErrorResponse ):
							try:
								await cli._send_recv ( BadAuthPlain1Request ( 'baad', 'f00d' ) )
							except smtp_proto.ErrorResponse as e:
								test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed auth input RFC4616#2')" )
								raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.auth_login ( 'Arthur', 'Dent' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(535, 'Authentication failed')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.auth_plain1 ( 'Ford', 'Prefect' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(535, 'Authentication failed')" )
							raise
					
					test.assertEqual (
						repr ( await cli.auth_plain2 ( 'Zaphod', 'Beeblebrox' ) ),
						"smtp_proto.SuccessResponse(235, 'Authentication successful')",
					)
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.auth_plain1 ( 'Ford', 'Prefect' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'already authenticated (RFC4954#4 Restrictions)')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.expn ( 'allusers' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'Access Denied!')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.vrfy ( 'admin@test.com' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'Access Denied!')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						class MailFrumRequest ( smtp_proto.MailFromRequest ):
							def _client_protocol ( self, client: smtp_proto.Client ) -> smtp_proto.RequestProtocolGenerator:
								yield from smtp_proto._client_proto_send_recv_done ( f'MAIL FRUM:<{self.mail_from}>\r\n' )
						try:
							await cli._send_recv ( MailFrumRequest ( 'foo@bar.com' ) )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed MAIL input')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'no from address received yet')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.mail_from ( 'ceo@test.com' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'address rejected')" )
							raise
					
					test.assertEqual ( repr ( await cli.mail_from ( 'from@test.com' ) ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						class RcptTooRequest ( smtp_proto.RcptToRequest ):
							def _client_protocol ( self, client: smtp_proto.Client ) -> smtp_proto.RequestProtocolGenerator:
								yield from smtp_proto._client_proto_send_recv_done ( f'RCPT TOO:<{self.rcpt_to}>\r\n' )
						try:
							await cli._send_recv ( RcptTooRequest ( 'foo@bar.com' ) )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed RCPT input')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'no rcpt address(es) received yet')" )
							raise
					
					with test.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.rcpt_to ( 'zaphod@beeblebrox.com' )
						except smtp_proto.ErrorResponse as e:
							test.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'address rejected')" )
							raise
					
					test.assertEqual ( repr ( await cli.rcpt_to ( 'to@test.com' ) ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					test.assertEqual ( repr ( await cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
						b'.<<< Evil line beginning with a dot\r\n'
						b'Last line of message\r\n'
					) ), "smtp_proto.SuccessResponse(250, 'Message accepted for delivery')" )
					
					test.assertEqual ( repr ( await cli.rset() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					test.assertEqual ( repr ( await cli.noop() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					test.assertEqual ( repr ( await cli.quit() ), "smtp_proto.SuccessResponse(221, 'Closing connection')" )
				
				except smtp_proto.ErrorResponse as e: # pragma: no cover
					log.exception ( f'server error: {e=}' )
				except smtp_proto.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					await cli.close()
			
			async def server_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.server_task' )
				class TestServer ( smtp_trio.Server ):
					async def on_EhloAcceptEvent ( self, event: smtp_proto.EhloAcceptEvent ) -> None:
						event.esmtp_features['FUBAR'] = ''
						event.accept()
					
					async def on_StartTlsAcceptEvent ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None:
						event.accept()
					
					async def on_AuthEvent ( self, event: smtp_proto.AuthEvent ) -> None:
						if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
							event.accept()
						else:
							event.reject()
					
					async def on_MailFromEvent ( self, event: smtp_proto.MailFromEvent ) -> None:
						if event.mail_from == 'from@test.com':
							event.accept()
						else:
							event.reject()
					
					async def on_RcptToEvent ( self, event: smtp_proto.RcptToEvent ) -> None:
						if event.rcpt_to.endswith ( '@test.com' ):
							event.accept()
						else:
							event.reject()
					
					async def on_CompleteEvent ( self, event: smtp_proto.CompleteEvent ) -> None:
						test.assertEqual ( event.mail_from, 'from@test.com' )
						test.assertEqual ( event.rcpt_to, [ 'to@test.com' ] )
						lines = b''.join ( event.data ).split ( b'\r\n' )
						test.assertEqual ( lines[0], b'From: from@test.com' )
						test.assertEqual ( lines[1], b'To: to@test.com' )
						test.assertEqual ( lines[2], b'Subject: Test email' )
						test.assertEqual ( lines[3], b'Date: 2000-01-01T00:00:00Z' )
						test.assertEqual ( lines[4], b'' )
						test.assertEqual ( lines[5], b'This is a test. This message does not end in a period, period.' )
						test.assertEqual ( lines[6], b'.<<< Evil line beginning with a dot' )
						test.assertEqual ( lines[7], b'Last line of message' )
						test.assertEqual ( lines[8], b'' )
						with test.assertRaises ( IndexError ):
							test.assertEqual ( lines[9], b'?????' )
						event.accept() # or .reject()
				
				srv = TestServer ( 'milliways.local' )
				
				try:
					srv.ssl_context = trust.server_context()
					await srv.run ( stream, False )
				except smtp_proto.Closed:
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
