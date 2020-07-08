#region PROLOGUE --------------------------------------------------------------
from __future__ import annotations

from abc import ABCMeta, abstractmethod
import base64
import logging
import re
from typing import (
	Callable, Iterator, List, Optional as Opt, Sequence as Seq, Tuple, Union,
)

logger = logging.getLogger ( __name__ )

_MAXLINE = 8192 # more than 8 times larger than RFC 821, 4.5.3
BYTES = Union[bytes,bytearray]
bytes_types = ( bytes, bytearray )
ENCODING = 'us-ascii'
ERRORS = 'strict'

#endregion
#region COMMON ----------------------------------------------------------------

def b2s ( b: bytes ) -> str:
	return b.decode ( ENCODING, ERRORS )

def s2b ( s: str ) -> bytes:
	return s.encode ( ENCODING, ERRORS )

def b64_encode ( s: str ) -> str:
	return b2s ( base64.b64encode ( s2b ( s ) ) )

def b64_decode ( s: str ) -> str:
	return b2s ( base64.b64decode ( s2b ( s ) ) )

class Closed ( Exception ): # TODO FIXME: BaseException?
	pass


class ProtocolError ( Exception ):
	pass


class Event:
	#def send_data ( self ) -> Iterator[SendDataEvent]:
	#	cls = type ( self )
	#	raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.to_bytes()' )
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}()'

class SendDataEvent ( Event ):
	def __init__ ( self, data: bytes ) -> None:
		assert isinstance ( data, bytes_types ) and len ( data ) > 0
		self.data = data

class Connection ( metaclass = ABCMeta ):
	_buf: bytes = b''
	
	def receive ( self, data: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'Connection.receive' )
		assert isinstance ( data, bytes_types ), f'invalid {data=}'
		if not data: # EOF indicator
			if self._buf:
				buf, self._buf = self._buf, b''
				yield from self._receive_line ( self._buf )
			raise Closed()
		self._buf += data
		start = 0
		while ( end := ( self._buf.find ( b'\n', start ) + 1 ) ):
			line = self._buf[start:end]
			yield from self._receive_line ( line )
			start = end
		if start:
			self._buf = self._buf[start:]
		if len ( self._buf ) >= _MAXLINE:
			raise ProtocolError ( 'maximum line length exceeded' )
	
	def _receive_line ( self, line: bytes ) -> Iterator[Event]:
		assert False, f'{line=}'
		yield from () # nothing to yield

#endregion
#region SERVER ----------------------------------------------------------------

class AcceptRejectEvent ( Event ):
	success_code: int
	success_message: str
	error_code: int
	error_message: str
	
	def __init__ ( self ) -> None:
		self._acceptance: Opt[bool] = None
		self._code: Opt[int] = None
		self._message: Opt[str] = None
	
	def accept ( self ) -> None:
		self._acceptance = True
		self._code = self.success_code
		self._message = self.success_message
	
	def reject ( self, code: Opt[int] = None, message: Opt[str] = None ) -> None:
		log = logger.getChild ( 'AcceptRejectEvent.reject' )
		self._acceptance = False
		self._code = self.error_code
		self._message = self.error_message
		if code is not None:
			if not isinstance ( code, int ) or code < 400 or code > 599:
				log.error ( f'invalid error-{code=}' )
			else:
				self._code = code
		if message is not None:
			if not isinstance ( message, str ) or _r_eol.search ( message ):
				log.error ( f'invalid error-{message=}' )
			else:
				self._message = message
	
	def _accepted ( self ) -> Tuple[bool,int,str]:
		log = logger.getChild ( 'AcceptRejectEvent._accepted' )
		assert self._acceptance is not None, f'you must call .accept() or .reject() on when passed a {type(self).__module__}.{type(self).__name__} object'
		assert isinstance ( self._code, int )
		assert isinstance ( self._message, str )
		return self._acceptance, self._code, self._message

class AuthEvent ( AcceptRejectEvent ):
	success_code = 235
	success_message = 'Authentication successful'
	error_code = 535
	error_message = 'Authentication failed'
	
	def __init__ ( self, uid: str, pwd: str ) -> None:
		super().__init__()
		self.uid = uid
		self.pwd = pwd

class MailFromEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = 'OK'
	error_code = 550
	error_message = 'address rejected'
	
	def __init__ ( self, mail_from: str ) -> None:
		super().__init__()
		self.mail_from = mail_from
	
	# TODO FIXME: define custom reject_* methods for specific scenarios

class RcptToEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = 'OK'
	error_code = 550
	error_message = 'address rejected'
	
	def __init__ ( self, rcpt_to: str ) -> None:
		super().__init__()
		self.rcpt_to = rcpt_to
	
	# TODO FIXME: define custom reject_* methods for specific scenarios

class CompleteEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = 'Message accepted for delivery'
	error_code = 450
	error_message = 'Unable to accept message for delivery'
	
	def __init__ ( self,
		mail_from: str,
		rcpt_to: Seq[str],
		data: Seq[bytes],
	) -> None:
		super().__init__()
		self.mail_from = mail_from
		self.rcpt_to = rcpt_to
		self.data = data
	
	# TODO FIXME: define custom reject_* methods for specific scenarios

class ServerState:
	def receive_line ( self, server: Server, line: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.ServerState.receive_line' )
		log.debug ( f'{line=}' )
		text = b2s ( line )
		if ' ' in text:
			command, textstring = map ( str.rstrip, text.split ( ' ', 1 ) )
		else:
			command, textstring = text.rstrip(), ''
		fname = f'on_{command.upper()}'
		try:
			f = getattr ( self, fname )
		except AttributeError:
			log.debug ( f'{type(self).__module__}.{type(self).__name__} has no {fname}' )
			yield from server._respond ( 500, f'command not recognized or not available: {command}' )
		else:
			log.debug ( f'calling {f=}' )
			yield from f ( server, command, textstring )
	
	def on_EXPN ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._respond ( 502, 'Command not implemented' )
	
	def on_HELO ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._respond ( 250, server.hostname )
		#yield ErrorResponse ( 400, 'you already said that' )
	
	def on_NOOP ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._respond ( 250, 'OK' )
	
	def on_QUIT ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._respond ( 250, 'OK' )
		raise Closed()
	
	def on_RSET ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._respond ( 250, 'OK' )
	
	def on_VRFY ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._respond ( 502, 'Command not implemented' )


class ServerStateUntrusted ( ServerState ):
	def on_HELO ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		server.state = ServerStateUntrusted()
		yield from server._respond ( 250, server.hostname )
	
	def on_EHLO ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._respond ( 502, 'TODO FIXME: Command not implemented' )
	
	def on_AUTH ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.ServerStateUntrusted.on_AUTH' )
		log.debug ( f'{command=} {textstring=}' )
		mechanism, *extra = textstring.split ( ' ', 1 )
		mechanism = mechanism.upper()
		if mechanism == 'LOGIN':
			server.state = ServerStateAuthLogin()
			yield from server._respond ( 334, b64_encode ( 'Username:' ) )
		if mechanism == 'PLAIN':
			server.state = ServerStateAuthPlain()
			if extra:
				yield from server.state.receive_line ( server, s2b ( extra[0] ) )
			else:
				yield from server._respond ( 334, '' )
		else:
			yield from server._respond ( 504, f'Unrecognized authentication type: {mechanism}' )

class ServerStateAuthPlain ( ServerState ):
	
	def receive_line ( self, server: Server, line: bytes ) -> Iterator[Event]:
		# see RFC 4616 section 2
		log = logger.getChild ( 'Server.ServerStateAuthPlain.receive_line' )
		#log.debug ( f'{line=}' )
		try:
			_, uid, pwd = b2s ( base64.b64decode ( line ) ).split ( '\0' )
		except Exception as e:
			#log.error ( f'{e=}' )
			yield from server._respond ( 501, 'malformed auth input RFC4616#2' )
			return
		yield from server.on_authenticate ( uid, pwd )

class ServerStateAuthLogin ( ServerState ):
	uid: Opt[str] = None
	
	def receive_line ( self, server: Server, line: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.ServerStateAuthLogin.receive_line' )
		try:
			if self.uid is None:
				self.uid = b2s ( base64.b64decode ( line ) )
				yield from server._respond ( 334, b64_encode ( 'Password:' ) )
				return
			else:
				assert isinstance ( self.uid, str )
				uid: str = self.uid
				pwd = b2s ( base64.b64decode ( line ) )
		except Exception:
			server.state = ServerStateUntrusted()
			yield from server._respond ( 501, 'malformed auth input' )
		
		yield from server.on_authenticate ( uid, pwd )

r_mail_from = re.compile ( r'\s*FROM\s*:\s*<?(.*)>?\s*$', re.I )
r_rcpt_to = re.compile ( r'\s*TO\s*:\s*<?(.*)>?\s*$', re.I )

class ServerStateTrusted ( ServerState ):
	def on_RSET ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		server.reset()
		yield from server._respond ( 250, server.hostname )
	
	def on_MAIL ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.ServerStateTrusted.on_MAIL' )
		log.debug ( f'{command=} {textstring=}' )
		m = r_mail_from.match ( textstring )
		if not m:
			yield from server._respond ( 501, 'malformed MAIL input' )
		else:
			mail_from = m.group ( 1 ).strip()
			yield from server.on_mail_from ( mail_from )
	
	def on_RCPT ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.ServerStateTrusted.on_RCPT' )
		log.debug ( f'{command=} {textstring=}' )
		m = r_rcpt_to.match ( textstring )
		if not m:
			yield from server._respond ( 501, 'malformed RCPT input' )
		else:
			rcpt_to = m.group ( 1 ).strip()
			yield from server.on_rcpt_to ( rcpt_to )
	
	def on_DATA ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.ServerStateTrusted.on_DATA' )
		log.debug ( f'{command=} {textstring=}' )
		if not server.mail_from:
			yield from server._respond ( 503, 'no from address received yet' )
		elif not server.rcpt_to:
			yield from server._respond ( 503, 'no rcpt address(es) received yet' )
		else:
			server.state = ServerStateData()
			yield from server._respond ( 354, 'Start mail input; end with <CRLF>.<CRLF>' )

class ServerStateData ( ServerState ):
	def receive_line ( self, server: Server, line: bytes ) -> Iterator[Event]:
		#log = logger.getChild ( 'ServerStateData.receive_line' )
		#log.debug ( f'{line=}' )
		if line == b'.\r\n':
			yield from server.on_complete()
		elif line.startswith ( b'.' ):
			server.data.append ( line[1:] )
		else:
			server.data.append ( line )

_r_eol = re.compile ( r'[\r\n]' )

class Server ( Connection ):
	client_hostname: str = ''
	mail_from: str
	rcpt_to: List[str]
	data: List[bytes]
	
	def __init__ ( self, hostname: str ) -> None:
		assert isinstance ( hostname, str ) and not _r_eol.search ( hostname ), f'invalid {hostname=}'
		self.hostname = hostname
		self.reset()
		self.state: ServerState = ServerStateUntrusted()
	
	def greeting ( self ) -> bytes:
		return s2b ( f'220 {self.hostname}\r\n' )
	
	def _receive_line ( self, line: bytes ) -> Iterator[Event]:
		yield from self.state.receive_line ( self, line )
	
	def reset ( self ) -> None:
		self.mail_from = ''
		self.rcpt_to = []
		self.data = []
	
	def _respond ( self, reply_code: int, errortext: str ) -> Iterator[Event]:
		assert isinstance ( reply_code, int ) and 100 <= reply_code <= 599, f'invalid {reply_code=}'
		assert isinstance ( errortext, str ) and not _r_eol.search ( errortext ), f'invalid {errortext=}'
		yield SendDataEvent ( s2b ( f'{reply_code} {errortext}\r\n' ) )
	
	def on_authenticate ( self, uid: str, pwd: str ) -> Iterator[Event]:
		event = AuthEvent ( uid, pwd )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			self.state = ServerStateTrusted()
		else:
			self.state = ServerStateUntrusted()
		yield from self._respond ( code, message )
	
	def on_mail_from ( self, mail_from: str ) -> Iterator[Event]:
		event = MailFromEvent ( mail_from )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			self.mail_from = mail_from
		yield from self._respond ( code, message )
	
	def on_rcpt_to ( self, rcpt_to: str ) -> Iterator[Event]:
		event = RcptToEvent ( rcpt_to )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			self.rcpt_to.append ( rcpt_to )
		yield from self._respond ( code, message )
	
	def on_complete ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.complete' )
		event = CompleteEvent ( self.mail_from, self.rcpt_to, self.data )
		self.reset()
		self.state = ServerStateTrusted()
		yield event
		accepted, code, message = event._accepted()
		yield from self._respond ( code, message )

#endregion
#region CLIENT ----------------------------------------------------------------

class Response:
	def __init__ ( self, code: int, message: str ) -> None:
		self.code = code
		self.message = message

class ErrorResponse ( Response, Exception ):
	def __init__ ( self, code: int, message: str ) -> None:
		Response.__init__ ( self, code, message )
		Exception.__init__ ( self, code, message )

class Request ( metaclass = ABCMeta ):
	response: Opt[Response] = None
	
	def __init__ ( self, line: str ) -> None:
		self.line = line
	
	def send_data ( self ) -> Iterator[SendDataEvent]:
		yield SendDataEvent ( s2b ( f'{self.line}\r\n' ) )
	
	def on_success ( self, client: Client, response: Response ) -> Iterator[Event]:
		yield from () # no follow-up

class MultiRequest ( Request ):
	def __init__ ( self, *lines: str ) -> None:
		self.lines = lines
	
	def on_success ( self, client: Client, response: Response ) -> Iterator[Event]:
		self.lines = self.lines[1:]
		if self.lines:
			yield SendDataEvent ( s2b ( f'{self.lines[0]}\r\n' ) )

class GreetingRequest ( Request ):
	def __init__ ( self ) -> None:
		pass
	
	def on_success ( self, client: Client, response: Response ) -> Iterator[Event]:
		yield from ()

class HeloRequest ( Request ):
	def __init__ ( self, domain: str ) -> None:
		self.domain = domain
		super().__init__ ( f'HELO {self.domain}' )

#class Ehlo ( Request ):
#	pass

class AuthPlain1Request ( Request ):
	def __init__ ( self, uid: str, pwd: str ) -> None:
		authtext = b64_encode ( f'{uid}\0{uid}\0{pwd}' )
		super().__init__ ( f'AUTH PLAIN {authtext}' )

class AuthPlain2Request ( MultiRequest ):
	def __init__ ( self, uid: str, pwd: str ) -> None:
		authtext = b64_encode ( f'{uid}\0{uid}\0{pwd}' )
		super().__init__ (
			'AUTH PLAIN',
			authtext,
		)

class AuthLoginRequest ( MultiRequest ):
	def __init__ ( self, uid: str, pwd: str ) -> None:
		super().__init__ (
			'AUTH LOGIN',
			b64_encode ( uid ),
			b64_encode ( pwd ),
		)

class MailFromRequest ( Request ):
	def __init__ ( self, mail_from: str ) -> None:
		self.mail_from = mail_from
		super().__init__ ( f'MAIL FROM:<{mail_from}>' )

class RcptToRequest ( Request ):
	def __init__ ( self, mail_from: str ) -> None:
		self.mail_from = mail_from
		super().__init__ ( f'RCPT TO:<{mail_from}>' )

class DataRequest ( Request ):
	initial_response: Opt[Response] = None
	
	def __init__ ( self, payload: bytes ) -> None:
		assert isinstance ( payload, bytes_types ) and len ( payload ) > 0
		self.stage: int = 1
		self.payload: bytes = payload
	
	def send_data ( self ) -> Iterator[SendDataEvent]:
		if self.stage == 1:
			yield SendDataEvent ( b'DATA\r\n' )
		else:
			yield SendDataEvent ( self.payload.replace ( b'\r\n.', b'\r\n..' ) ) # TODO FIXME: performance -> get rid of .replace()
			yield SendDataEvent ( b'\r\n.\r\n' )
	
	def on_success ( self, client: Client, response: Response ) -> Iterator[Event]:
		if self.stage == 1:
			self.initial_response = response
			self.response = None # wait for next response...
			self.stage = 2
			yield from client.send ( self )



class QuitRequest ( Request ):
	def __init__ ( self ) -> None:
		super().__init__ ( 'QUIT' )

class Client ( Connection ):
	request: Opt[Request] = None
	
	def __init__ ( self, greeting: GreetingRequest ) -> None:
		self.request = greeting
		#self.state: ClientState = ServerSpeaksFirstState()
	
	def send ( self, request: Request ) -> Iterator[Event]:
		log = logger.getChild ( 'Client.send' )
		assert self.request is None, f'trying to send {request=} but not finished processing {self.request=}'
		self.request = request
		log.debug ( f'setting {self.request=}' )
		yield from request.send_data()
	
	def _receive_line ( self, line: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'Client._receive_line' )
		log.debug ( f'{line=}' )
		try:
			reply_code = int ( line[:3] )
			intermed = line[3:4]
			textstring = b2s ( line[4:] ).rstrip()
			if intermed not in ( b' ', b'-' ):
				raise ValueError ( f'invalid {intermed=}' )
		except ValueError as e:
			raise Closed ( f'invalid response: {e=}' ) from e
		intermediate = ( intermed == b'-' )
		
		log.debug ( f'clearing {self.request=}' )
		request, self.request = self.request, None
		assert isinstance ( request, Request )
		if reply_code < 400:
			request.response = Response ( reply_code, textstring )
			log.debug ( f'calling {request=}.on_success()' )
			yield from request.on_success ( self, request.response )
		else:
			request.response = ErrorResponse ( reply_code, textstring )
			raise request.response

#endregion
#region EPILOGUE ---- ---------------------------------------------------------

if __name__ == '__main__':
	import trio # pip install trio trio-typing
	
	logging.basicConfig ( level = logging.DEBUG )
	logging.getLogger ( '__main__.Client' ).setLevel ( logging.INFO )
	logging.getLogger ( '__main__.Server' ).setLevel ( logging.INFO )
	
	async def main() -> None:
		greeting = GreetingRequest()
		cli = Client ( greeting )
		srv = Server ( 'milliways.local' )
		
		xmit1, recv1 = trio.open_memory_channel[bytes] ( 0 )
		xmit2, recv2 = trio.open_memory_channel[bytes] ( 0 )
		
		async def client_task ( recv: trio.MemoryReceiveChannel[bytes], xmit: trio.MemorySendChannel[bytes] ) -> None:
			try:
				log = logger.getChild ( 'main.client_task' )
				
				async def _event ( event: Event ) -> None:
					if isinstance ( event, SendDataEvent ):
						log.debug ( f'C>{b2s(event.data).rstrip()}' )
						await xmit.send ( event.data )
					else:
						assert False, f'unrecognized {event=}'
				
				async def _recv ( request: Request ) -> Response:
					#log = logger.getChild ( 'main.client_task._recv' )
					while not request.response:
						data: bytes = await recv.receive()
						log.debug ( f'S>{b2s(data).rstrip()}' )
						for event in cli.receive ( data ):
							await _event ( event )
					return request.response
				
				async def _send_recv ( request: Request ) -> Response:
					#log = logger.getChlid ( 'main.client_task._send_recv' )
					for event in cli.send ( request ):
						await _event ( event )
					return await _recv ( request )
				
				try:
					await _recv ( greeting )
					await _send_recv ( HeloRequest ( 'localhost' ) )
					await _send_recv ( AuthPlain1Request ( 'Zaphod', 'Beeblebrox' ) )
					await _send_recv ( MailFromRequest ( 'from@test.com' ) )
					await _send_recv ( RcptToRequest ( 'to@test.com' ) )
					await _send_recv ( DataRequest (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't right...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
					) )
					await _send_recv ( QuitRequest() )
					
				except ErrorResponse as e:
					log.error ( f'server error: {e=}' )
				except Closed as e:
					log.debug ( f'server closed connection: {e=}' )
			finally:
				await recv.aclose()
				await xmit.aclose()
		
		async def server_task ( xmit: trio.MemorySendChannel[bytes], recv: trio.MemoryReceiveChannel[bytes] ) -> None:
			try:
				log = logger.getChild ( 'main.server_task' )
				data = srv.greeting()
				log.debug ( f'S>{b2s(data).rstrip()}' )
				await xmit.send ( data )
				while True:
					try:
						data = await recv.receive()
					except trio.EndOfChannel:
						raise Closed()
					log.debug ( f'C>{b2s(data).rstrip()}' )
					for event in srv.receive ( data ):
						if isinstance ( event, SendDataEvent ): # this will be the most common event...
							log.debug ( f'S>{b2s(data).rstrip()}' )
							await xmit.send ( event.data )
						elif isinstance ( event, RcptToEvent ): # 2nd most common event
							log.debug ( f'{event.rcpt_to=}' )
							event.accept() # or .reject()
						elif isinstance ( event, MailFromEvent ):
							log.debug ( f'{event.mail_from=}' )
							event.accept() # or .reject()
						elif isinstance ( event, AuthEvent ):
							if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
								event.accept()
							else:
								event.reject()
						elif isinstance ( event, CompleteEvent ):
							print ( f'MAIL FROM: {event.mail_from}' )
							for rcpt_to in event.rcpt_to:
								print ( f'RCPT TO: {rcpt_to}' )
							print ( '-' * 20 )
							for line in event.data:
								print ( b2s ( line ) )
							event.accept() # or .reject()
						else:
							assert False, f'unrecognized {event=}'
			except Closed:
				pass
			finally:
				await xmit.aclose()
				await recv.aclose()
		
		async with trio.open_nursery() as nursery:
			nursery.start_soon ( client_task, recv1, xmit2 )
			nursery.start_soon ( server_task, xmit1, recv2 )
	
	trio.run ( main )
#endregion
