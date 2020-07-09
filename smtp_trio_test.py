# system imports:
from abc import ABCMeta, abstractmethod
import logging
import trio # pip install trio trio-typing
import trio.testing
import unittest

# mail_proto imports:
import smtp
import smtp_trio

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ) -> None:
		async def _test() -> None:
			thing1, thing2 = trio.testing.lockstep_stream_pair()
			
			async def client_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.client_task' )
				try:
					cli = smtp_trio.Client()
					cli.stream = stream
					self.assertEqual ( repr ( await cli._connect() ), "smtp.Response(code=220, message='milliways.local')" )
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.ehlo ( 'localhost' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=502, message='TODO FIXME: Command not implemented')" )
							raise
					self.assertEqual ( repr ( await cli.helo ( 'localhost' ) ), "smtp.Response(code=250, message='milliways.local')" )
					self.assertEqual ( repr ( await cli.rset() ), "smtp.Response(code=250, message='OK')" )
					
					if True: # request an non-existent AUTH mechanism
						class AuthFubarRequest ( smtp.Request ):
							def __init__ ( self ) -> None:
								super().__init__ ( f'AUTH FUBAR' )
						with self.assertRaises ( smtp.ErrorResponse ):
							try:
								await cli._send_recv ( AuthFubarRequest() )
							except smtp.ErrorResponse as e:
								self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=504, message='Unrecognized authentication mechanism: FUBAR')" )
								raise
					
					if True: # construct an invalid AUTH PLAIN request to trigger specific error handling in the server-side protocol
						class BadAuthPlain1Request ( smtp.AuthPlain1Request ):
							def __init__ ( self ) -> None:
								smtp.Request.__init__ ( self, 'AUTH PLAIN BAADF00D' )
						with self.assertRaises ( smtp.ErrorResponse ):
							try:
								await cli._send_recv ( BadAuthPlain1Request() )
							except smtp.ErrorResponse as e:
								self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=501, message='malformed auth input RFC4616#2')" )
								raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.auth_login ( 'Arthur', 'Dent' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=535, message='Authentication failed')" )
							raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.auth_plain1 ( 'Ford', 'Prefect' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=535, message='Authentication failed')" )
							raise
					
					self.assertEqual ( repr ( await cli.auth_plain2 ( 'Zaphod', 'Beeblebrox' ) ), "smtp.Response(code=235, message='Authentication successful')" )
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.expn ( 'allusers' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=550, message='Access Denied!')" )
							raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.vrfy ( 'admin@test.com' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=550, message='Access Denied!')" )
							raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						class MailFrumRequest ( smtp.Request ):
							def __init__ ( self ) -> None:
								self.mail_from = 'foo@bar.com'
								smtp.Request.__init__ ( self, f'MAIL FRUM:<{self.mail_from}>' )
						try:
							await cli._send_recv ( MailFrumRequest() )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=501, message='malformed MAIL input')" )
							raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=503, message='no from address received yet')" )
							raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.mail_from ( 'ceo@test.com' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=550, message='address rejected')" )
							raise
					
					self.assertEqual ( repr ( await cli.mail_from ( 'from@test.com' ) ), "smtp.Response(code=250, message='OK')" )
					
					with self.assertRaises ( smtp.ErrorResponse ):
						class RcptTooRequest ( smtp.Request ):
							def __init__ ( self ) -> None:
								self.mail_from = 'foo@bar.com'
								smtp.Request.__init__ ( self, f'RCPT TOO:<{self.mail_from}>' )
						try:
							await cli._send_recv ( RcptTooRequest() )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=501, message='malformed RCPT input')" )
							raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.data ( b'x' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=503, message='no rcpt address(es) received yet')" )
							raise
					
					with self.assertRaises ( smtp.ErrorResponse ):
						try:
							await cli.rcpt_to ( b'zaphod@beeblebrox.com' )
						except smtp.ErrorResponse as e:
							self.assertEqual ( repr ( e ), "smtp.ErrorResponse(code=550, message='address rejected')" )
							raise
					
					self.assertEqual ( repr ( await cli.rcpt_to ( 'to@test.com' ) ), "smtp.Response(code=250, message='OK')" )
					
					self.assertEqual ( repr ( await cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
						b'.<<< Evil line beginning with a dot\r\n'
						b'Last line of message\r\n'
					) ), "smtp.Response(code=250, message='Message accepted for delivery')" )
					
					self.assertEqual ( repr ( await cli.rset() ), "smtp.Response(code=250, message='OK')" )
					
					self.assertEqual ( repr ( await cli.noop() ), "smtp.Response(code=250, message='OK')" )
					
					self.assertEqual ( repr ( await cli.quit() ), "smtp.Response(code=250, message='OK')" )
				
				except smtp.ErrorResponse as e: # pragma: no cover
					log.exception ( f'server error: {e=}' )
				except smtp.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					await stream.aclose()
			
			async def server_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.server_task' )
				try:
					class TestServer ( smtp_trio.Server ):
						async def on_authenticate ( self, event: smtp.AuthEvent ) -> None:
							if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
								event.accept()
							else:
								event.reject()
						
						async def on_mail_from ( self, event: smtp.MailFromEvent ) -> None:
							if event.mail_from == 'from@test.com':
								event.accept()
							else:
								event.reject()
						
						async def on_rcpt_to ( self, event: smtp.RcptToEvent ) -> None:
							if event.rcpt_to.endswith ( '@test.com' ):
								event.accept()
							else:
								event.reject()
						
						async def on_complete ( self, event: smtp.CompleteEvent ) -> None:
							log.debug ( f'MAIL FROM: {event.mail_from}' )
							for rcpt_to in event.rcpt_to:
								log.debug ( f'RCPT TO: {rcpt_to}' )
							log.debug ( '-' * 20 )
							log.debug ( b2s ( b''.join ( event.data ) ) )
							event.accept() # or .reject()
					
					srv = TestServer ( 'milliways.local' )
					
					await srv.run ( stream )
				except smtp.Closed:
					pass
				finally:
					await stream.aclose()
			
			async with trio.open_nursery() as nursery:
				nursery.start_soon ( client_task, thing1 )
				nursery.start_soon ( server_task, thing2 )
		
		trio.run ( _test )

if __name__ == '__main__':
	logging.basicConfig (
		level = logging.DEBUG,
	)
	unittest.main()
