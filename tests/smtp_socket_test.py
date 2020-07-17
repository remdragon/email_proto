# system imports;
from functools import partial
import logging
import socket
import ssl
import sys
import threading
from typing import Callable, Type
import unittest

# mail_proto imports:
import itrustme
import smtp_proto
import smtp_socket
from util import b2s

logger = logging.getLogger ( __name__ )

if False:
	trust = itrustme.ClientServer (
		client_hostname = 'zaphod@milliways.local',
		server_hostname = 'milliways.local',
	)
else:
	trust = itrustme.ServerOnly (
		server_hostname = 'milliways.local',
	)

class Tests ( unittest.TestCase ):
	def test_ping_pong ( self ) -> None:
		test = self
		
		thing1, thing2 = socket.socketpair()
		
		def client_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_auth_plain1.client_task' )
			xport = smtp_socket.Transport ( sock )
			xport.ssl_context = trust.client_context()
			tls = False
			cli = smtp_socket.Client ( xport, tls, 'milliways.local' )
			
			def test_pass (
				func: Callable[[],smtp_proto.Response],
				responserepr: str,
				responsecls: Type[smtp_proto.Response] = smtp_proto.SuccessResponse,
			) -> None:
				try:
					r = func()
				except Exception as e:
					r = e
				test.assertEqual ( repr ( r ), responserepr )
				test.assertEqual ( type ( r ), responsecls )
			
			def test_fail (
				func: Callable[[],smtp_proto.Response],
				responserepr: str,
				responsecls: Type[smtp_proto.Response] = smtp_proto.ErrorResponse,
			) -> None:
				try:
					r = func()
				except Exception as e:
					test.assertEqual ( repr ( e ), responserepr )
					test.assertEqual ( type ( e ), responsecls )
				else:
					test.fail ( f'function did not throw an error but returned {r=}' )
			
			try:
				test_pass ( cli.greeting,
					"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
				)
				
				r1 = smtp_proto.HeloRequest ( 'localhost' )
				r1.domain = ''
				test_fail ( lambda: cli._request ( r1 ),
					"smtp_proto.ErrorResponse(501, 'missing required hostname parameter')",
				)
				
				r1 = smtp_proto.EhloRequest ( 'localhost' )
				r1.domain = ''
				test_fail ( lambda: cli._request ( r1 ),
					"smtp_proto.ErrorResponse(501, 'missing required hostname parameter')",
				)
				
				test_pass ( lambda: cli.helo ( 'localhost' ),
					"smtp_proto.SuccessResponse(250, 'milliways.local greets localhost')",
				)
				
				test_pass ( lambda: cli.starttls(),
					"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
				)
				
				test_pass ( lambda: cli.helo ( 'localhost' ),
					"smtp_proto.SuccessResponse(250, 'milliways.local greets localhost')",
				)
				
				test_pass (
					lambda: cli.auth_plain1 ( 'Zaphod', 'Beeblebrox' ),
					"smtp_proto.SuccessResponse(235, 'Authentication successful')",
				)
				
				test_pass ( lambda: cli.expn ( 'mike' ),
					"smtp_proto.ExpnResponse(250, 'mike@abc.com')",
					smtp_proto.ExpnResponse,
				)
				
				test_pass ( lambda: cli.vrfy ( 'users-hackers' ),
					"smtp_proto.VrfyResponse(250, 'carol@abc.com', 'greg@abc.com', 'marcha@abc.com', 'peter@abc.com')",
					smtp_proto.VrfyResponse,
				)
				
				test_pass ( lambda: cli.mail_from ( 'from@test.com' ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
				
				test_pass ( lambda: cli.rcpt_to ( 'to@test.com' ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
				
				test_pass ( lambda: cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
						b'.<<< Evil line beginning with a dot\r\n'
						b'Last line of message\r\n'
					),
					"smtp_proto.SuccessResponse(250, 'Message accepted for delivery')",
				)
				
				test_pass (
					lambda: cli.quit(),
					"smtp_proto.SuccessResponse(221, 'Closing connection')",
				)
			
			except smtp_proto.Closed as e: # pragma: no cover
				log.debug ( f'server closed connection: {e=}' )
			except Exception:
				log.exception ( 'Unexpected client_task exception:' )
			finally:
				cli.close()
		
		def server_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_auth_plain1.server_task' )
			
			class TestServer ( smtp_socket.Server ):
				def on_StartTlsAcceptEvent ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None:
					event.accept()
				
				def on_expnvrfy ( self, event: smtp_proto.ExpnVrfyEvent ) -> None:
					if event.mailbox == 'mike':
						event.accept ( 'mike@abc.com' )
					elif event.mailbox == 'users-hackers':
						event.accept ( 'carol@abc.com', 'greg@abc.com', 'marcha@abc.com', 'peter@abc.com' ) # sheesh, someone was a Brady's Bunch fan
					else:
						event.reject()
				
				def on_ExpnEvent ( self, event: smtp_proto.ExpnEvent ) -> None:
					self.on_expnvrfy ( event )
				
				def on_VrfyEvent ( self, event: smtp_proto.VrfyEvent ) -> None:
					self.on_expnvrfy ( event )
				
				def on_AuthEvent ( self, event: smtp_proto.AuthEvent ) -> None:
					if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
						event.accept()
					else:
						event.reject()
				
				def on_MailFromEvent ( self, event: smtp_proto.MailFromEvent ) -> None:
					event.accept() # or .reject()
				
				def on_RcptToEvent ( self, event: smtp_proto.RcptToEvent ) -> None:
					event.accept() # or .reject()
				
				def on_CompleteEvent ( self, event: smtp_proto.CompleteEvent ) -> None:
					test.assertEqual ( event.mail_from, 'from@test.com' )
					test.assertEqual ( event.rcpt_to, [ 'to@test.com' ] )
					test.assertEqual ( b2s ( b''.join ( event.data ) ),
						'From: from@test.com\r\n'
						'To: to@test.com\r\n'
						'Subject: Test email\r\n'
						'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						'\r\n' # a sane person would use the email module to create their email content...
						'This is a test. This message does not end in a period, period.\r\n'
						'.<<< Evil line beginning with a dot\r\n'
						'Last line of message\r\n'
					)
					event.accept() # or .reject()
			
			xport = smtp_socket.Transport ( sock )
			xport.ssl_context = trust.server_context()
			tls = False
			srv = TestServer ( xport, tls, 'milliways.local' )
			
			try:
				srv.run()
			except smtp_proto.Closed:
				pass
			except Exception:
				log.exception ( 'Unexpected server_task exception:' )
			finally:
				srv.close()
		
		thread1 = threading.Thread ( target = partial ( client_task, thing1 ), name = 'SocketClientThread' )
		thread2 = threading.Thread ( target = partial ( server_task, thing2 ), name = 'SocketServerThread' )
		
		thread1.start()
		thread2.start()
		
		thread1.join()
		thread2.join()
	
	def test_RFC5321_D1_replay ( self ) -> None:
		# can our protocol recreate RFC 5321 D1?
		
		thing1, thing2 = socket.socketpair()
		
		def client_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_RFC5321_D1_replay.client_task' )
			try:
				xport = smtp_socket.Transport ( sock )
				xport.ssl_context = trust.client_context()
				tls = False
				cli = smtp_socket.Client ( xport, tls, 'milliways.local' )
				
				self.assertEqual (
					repr ( cli.greeting() ),
					"smtp_proto.SuccessResponse(220, 'foo.com Simple Mail Transfer Service Ready')",
				)
				
				self.assertEqual (
					repr ( cli.ehlo ( 'bar.com' ) ),
					"smtp_proto.EhloResponse(250, 'foo.com greets bar.com', '8BITMIME', 'SIZE', 'DSN', 'HELP')",
				)
				
				self.assertEqual (
					repr ( cli.mail_from ( 'Smith@bar.com' ) ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
				
				self.assertEqual (
					repr ( cli.rcpt_to ( 'Jones@foo.com' ) ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
				
				with self.assertRaises ( smtp_proto.ErrorResponse ):
					try:
						cli.rcpt_to ( 'Green@foo.com' )
					except smtp_proto.ErrorResponse as e:
						self.assertEqual ( repr ( e ), "smtp_proto.ErrorResponse(550, 'No such user here')" )
						raise
				
				self.assertEqual (
					repr ( cli.rcpt_to ( 'Brown@foo.com' ) ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
				
				self.assertEqual ( repr ( cli.data (
					b'Blah blah blah...\r\n'
					b'..etc. etc. etc.'
				) ), "smtp_proto.SuccessResponse(250, 'OK')" )
				
				self.assertEqual (
					repr ( cli.quit() ),
					"smtp_proto.SuccessResponse(221, 'foo.com Service closing transmission channel')",
				)
			
			except smtp_proto.Closed as e: # pragma: no cover
				log.debug ( f'server closed connection: {e=}' )
			except Exception:
				log.exception ( 'Unexpected client_task exception:' )
			finally:
				cli.close()
		
		def server_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_RFC5321_D1_replay.server_task' )
			def expect ( request: bytes, response: bytes ) -> None:
				received = b''
				while len ( received ) < len ( request ):
					received += sock.recv ( len ( request ) - len ( received ) )
				self.assertEqual ( received, request )
				sock.sendall ( response )
			try:
				expect ( b'', b'220 foo.com Simple Mail Transfer Service Ready\r\n' )
				expect ( b'EHLO bar.com\r\n',
					b'250-foo.com greets bar.com\r\n'
					b'250-8BITMIME\r\n'
					b'250-SIZE\r\n'
					b'250-DSN\r\n'
					b'250 HELP\r\n'
				)
				expect ( b'MAIL FROM:<Smith@bar.com>\r\n', b'250 OK\r\n' )
				expect ( b'RCPT TO:<Jones@foo.com>\r\n', b'250 OK\r\n' )
				expect ( b'RCPT TO:<Green@foo.com>\r\n', b'550 No such user here\r\n' )
				expect ( b'RCPT TO:<Brown@foo.com>\r\n', b'250 OK\r\n' )
				expect ( b'DATA\r\n', b'354 Start mail input; end with <CRLF>.<CRLF>\r\n' )
				expect (
					b'Blah blah blah...\r\n'
					b'...etc. etc. etc.\r\n'
					b'.\r\n',
					b'250 OK\r\n'
				)
				expect ( b'QUIT\r\n', b'221 foo.com Service closing transmission channel\r\n' )
			finally:
				sock.close()
		
		thread1 = threading.Thread ( target = partial ( client_task, thing1 ), name = 'SocketClientThread' )
		thread2 = threading.Thread ( target = partial ( server_task, thing2 ), name = 'SocketServerThread' )
		
		thread1.start()
		thread2.start()
		
		thread1.join()
		thread2.join()
	
	if False:
		def test_hmailserver ( self ) -> None:
			log = logger.getChild ( 'Tests.test_hmailserver' )
			mail_from = 'ford.prefect@milliways.local'
			rcpt_to = 'zaphod@milliways.local'
			from email.message import EmailMessage
			msg = EmailMessage()
			msg['From'] = mail_from
			msg['To'] = rcpt_to
			msg['Subject'] = 'Re: Lunch?'
			msg.set_content ( 'Ask Marvin' )
			
			client = smtp_socket.Client()
			client.connect ( '127.0.0.1', 587, False )
			r1 = client.ehlo ( 'localhost' )
			if 'STARTTLS' in r1.esmtp_features:
				client.starttls()
			else:
				log.warning ( 'STARTTLS not advertised!' )
			client.auth_login ( rcpt_to, 'Beeblebrox' )
			client.mail_from ( mail_from )
			client.rcpt_to ( rcpt_to )
			r = client.data ( bytes ( msg ).replace ( b'\n', b'\r\n' ) )
			print ( f'{r=}' )
			client.quit()
			client.close()

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
