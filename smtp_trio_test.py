# system imports:
from abc import ABCMeta, abstractmethod
import logging
import trio # pip install trio trio-typing
import trio.testing
from typing import Iterator
import unittest

# mail_proto imports:
import smtp_proto
import smtp_trio

logger = logging.getLogger ( __name__ )

b2s = smtp_proto.b2s

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ) -> None:
		self.maxDiff = None
		
		async def _test() -> None:
			thing1, thing2 = trio.testing.lockstep_stream_pair()
			
			async def client_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.client_task' )
				try:
					cli = smtp_trio.Client()
					cli.stream = stream
					
					self.assertEqual ( repr ( await cli._connect() ), "smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')" )
					
					# NOTE we can't (currently) test a successful HELO and EHLO in a single session, so I'll test HELO in a different unittest
					r = await cli.ehlo ( 'localhost' )
					self.assertEqual ( type ( r ), smtp_proto.EhloResponse )
					self.assertEqual ( r.code, 250 )
					self.assertEqual ( sorted ( r.lines ), [
						'8BITMIME',
						'AUTH PLAIN LOGIN',
						'PIPELINING',
						'STARTTLS',
						'milliways.local greets localhost',
					] )
					self.assertTrue ( r.esmtp_8bitmime )
					self.assertEqual ( sorted ( r.esmtp_auth ), [ 'LOGIN', 'PLAIN' ] )
					self.assertTrue ( r.esmtp_pipelining )
					self.assertTrue ( r.esmtp_starttls )
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.helo ( 'localhost' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'you already said HELO RFC1869#4.2')" )
							raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.ehlo ( 'localhost' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'you already said HELO RFC1869#4.2')" )
							raise
					self.assertEqual ( repr ( await cli.rset() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					if False: # not ready yet
						self.assertEqual ( repr ( await cli.starttls() ) )
					
					if True: # request an non-existent AUTH mechanism
						class AuthFubarRequest ( smtp_proto.Request ):
							def _client_protocol ( self ) -> Iterator[smtp_proto.Event]:
								log = logger.getChild ( 'AuthFubarRequest._client_protocol' )
								yield from smtp_proto._client_proto_send_recv_done ( f'AUTH FUBAR\r\n' )
							def _server_protocol ( self, server: smtp_proto.Server ) -> Iterator[smtp_proto.Event]:
								assert False
						with self.assertRaises ( smtp_proto.ErrorResponse ):
							try:
								await cli._send_recv ( AuthFubarRequest() )
							except smtp_proto.ErrorResponse as e:
								self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(504, 'Unrecognized authentication mechanism: FUBAR')" )
								raise
					
					if True: # construct an invalid AUTH PLAIN request to trigger specific error handling in the server-side protocol
						class BadAuthPlain1Request ( smtp_proto.AuthPlain1Request ):
							def _client_protocol ( self ) -> Iterator[smtp_proto.Event]:
								log = logger.getChild ( 'HeloRequest._client_protocol' )
								yield from smtp_proto._client_proto_send_recv_done ( f'AUTH PLAIN BAADF00D\r\n' )
						with self.assertRaises ( smtp_proto.ErrorResponse ):
							try:
								await cli._send_recv ( BadAuthPlain1Request ( 'baad', 'f00d' ) )
							except smtp_proto.ErrorResponse as e:
								self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed auth input RFC4616#2')" )
								raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.auth_login ( 'Arthur', 'Dent' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(535, 'Authentication failed')" )
							raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.auth_plain1 ( 'Ford', 'Prefect' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(535, 'Authentication failed')" )
							raise
					
					self.assertEqual (
						repr ( await cli.auth_plain2 ( 'Zaphod', 'Beeblebrox' ) ),
						"smtp_proto.SuccessResponse(235, 'Authentication successful')",
					)
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.auth_plain1 ( 'Ford', 'Prefect' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'already authenticated (RFC4954#4 Restrictions)')" )
							raise
					
					if False: # TODO FIXME
						with self.assertRaises ( smtp_proto.ErrorResponse ):
							try:
								await cli.expn ( 'allusers' )
							except smtp_proto.ErrorResponse as e:
								self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'Access Denied!')" )
								raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.vrfy ( 'admin@test.com' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'Access Denied!')" )
							raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						class MailFrumRequest ( smtp_proto.MailFromRequest ):
							def _client_protocol ( self ) -> Iterator[smtp_proto.Event]:
								yield from smtp_proto._client_proto_send_recv_done ( f'MAIL FRUM:<{self.mail_from}>\r\n' )
						try:
							await cli._send_recv ( MailFrumRequest ( 'foo@bar.com' ) )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed MAIL input')" )
							raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'no from address received yet')" )
							raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.mail_from ( 'ceo@test.com' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'address rejected')" )
							raise
					
					self.assertEqual ( repr ( await cli.mail_from ( 'from@test.com' ) ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						class RcptTooRequest ( smtp_proto.RcptToRequest ):
							def _client_protocol ( self ) -> Iterator[smtp_proto.Event]:
								yield from smtp_proto._client_proto_send_recv_done ( f'RCPT TOO:<{self.rcpt_to}>\r\n' )
						try:
							await cli._send_recv ( RcptTooRequest ( 'foo@bar.com' ) )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(501, 'malformed RCPT input')" )
							raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(503, 'no rcpt address(es) received yet')" )
							raise
					
					with self.assertRaises ( smtp_proto.ErrorResponse ):
						try:
							await cli.rcpt_to ( 'zaphod@beeblebrox.com' )
						except smtp_proto.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'address rejected')" )
							raise
					
					self.assertEqual ( repr ( await cli.rcpt_to ( 'to@test.com' ) ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					self.assertEqual ( repr ( await cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
						b'.<<< Evil line beginning with a dot\r\n'
						b'Last line of message\r\n'
					) ), "smtp_proto.SuccessResponse(250, 'Message accepted for delivery')" )
					
					self.assertEqual ( repr ( await cli.rset() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					self.assertEqual ( repr ( await cli.noop() ), "smtp_proto.SuccessResponse(250, 'OK')" )
					
					self.assertEqual ( repr ( await cli.quit() ), "smtp_proto.SuccessResponse(250, 'OK')" )
				
				except smtp_proto.ErrorResponse as e: # pragma: no cover
					log.exception ( f'server error: {e=}' )
				except smtp_proto.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					await stream.aclose()
			
			async def server_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.server_task' )
				try:
					class TestServer ( smtp_trio.Server ):
						async def on_starttls_request ( self, event: smtp_proto.StartTlsRequestEvent ) -> None:
							event.reject()
						
						async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
							raise NotImplementedError
						
						async def on_authenticate ( self, event: smtp_proto.AuthEvent ) -> None:
							if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
								event.accept()
							else:
								event.reject()
						
						async def on_mail_from ( self, event: smtp_proto.MailFromEvent ) -> None:
							if event.mail_from == 'from@test.com':
								event.accept()
							else:
								event.reject()
						
						async def on_rcpt_to ( self, event: smtp_proto.RcptToEvent ) -> None:
							if event.rcpt_to.endswith ( '@test.com' ):
								event.accept()
							else:
								event.reject()
						
						async def on_complete ( self, event: smtp_proto.CompleteEvent ) -> None:
							log.debug ( f'MAIL FROM: {event.mail_from}' )
							for rcpt_to in event.rcpt_to:
								log.debug ( f'RCPT TO: {rcpt_to}' )
							log.debug ( '-' * 20 )
							log.debug ( b2s ( b''.join ( event.data ) ) )
							event.accept() # or .reject()
					
					srv = TestServer ( 'milliways.local' )
					
					await srv.run ( stream )
				except smtp_proto.Closed:
					pass
				finally:
					await stream.aclose()
			
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
