#region PROLOGUE --------------------------------------------------------------
from __future__ import annotations

from abc import ABCMeta, abstractmethod
import base64
import logging
import re
from typing import (
	Callable, Dict, Iterable, Iterator, List, Optional as Opt, Sequence as Seq,
	Tuple, Type, Union,
)

logger = logging.getLogger ( __name__ )

_MAXLINE = 8192 # more than 8 times larger than RFC 821, 4.5.3
BYTES = Union[bytes,bytearray]
bytes_types = ( bytes, bytearray )
ENCODING = 'us-ascii'
ERRORS = 'strict'

_r_eol = re.compile ( r'[\r\n]' )
_r_mail_from = re.compile ( r'\s*FROM\s*:\s*<?([^>]*)>?\s*$', re.I )
_r_rcpt_to = re.compile ( r'\s*TO\s*:\s*<?([^>]*)>?\s*$', re.I )

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
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(data={self.data!r})'


class Connection ( metaclass = ABCMeta ):
	_buf: bytes = b''
	
	def receive ( self, data: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'Connection.receive' )
		assert isinstance ( data, bytes_types ), f'invalid {data=}'
		if not data: # EOF indicator
			if self._buf:
				buf, self._buf = self._buf, b''
				yield from self._receive_line ( buf )
				return
			raise Closed()
		self._buf += data
		start = 0
		while ( end := ( self._buf.find ( b'\n', start ) + 1 ) ):
			line = self._buf[start:end]
			try:
				yield from self._receive_line ( line )
			except:
				# we normally wait until yielding all events, but exceptions abort our loop, so clean up now:
				self._buf = self._buf[end:]
				raise
			start = end
		if start:
			self._buf = self._buf[start:]
		if len ( self._buf ) >= _MAXLINE:
			raise ProtocolError ( 'maximum line length exceeded' )
	
	@abstractmethod
	def _receive_line ( self, line: bytes ) -> Iterator[Event]:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._receive_line()' )

#endregion
#region SERVER ----------------------------------------------------------------

#class ErrorEvent ( Event ):
#	def __init__ ( self, code: int, message: str ) -> None:
#		self.code = code
#		self.message = message
#	
#	def __repr__ ( self ) -> str:
#		cls = type ( self )
#		return f'{cls.__module__}.{cls.__name__}(code={self.code!r}, message={self.message!r})'

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
		#log = logger.getChild ( 'AcceptRejectEvent.accept' )
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
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		args = ', '.join ( f'{k}={getattr(self,k)!r}' for k in (
			'_acceptance',
			'_code',
			'_message',
		) )
		return f'{cls.__module__}.{cls.__name__}({args})'


class StartTlsRequestEvent ( AcceptRejectEvent ):
	success_code = 220
	success_message = 'Go ahead, make my day'
	error_code = 454
	error_message = 'TLS not available at the moment'
	# TODO FIXME: also 501 Syntax error (no parameters allowed)


class StartTlsBeginEvent ( Event ):
	pass

class AuthEvent ( AcceptRejectEvent ):
	success_code = 235
	success_message = 'Authentication successful'
	error_code = 535
	error_message = 'Authentication failed'
	
	def __init__ ( self, uid: str, pwd: str ) -> None:
		super().__init__()
		self.uid = uid
		self.pwd = pwd
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(uid={self.uid!r})'


class MailFromEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = 'OK'
	error_code = 550
	error_message = 'address rejected'
	
	def __init__ ( self, mail_from: str ) -> None:
		super().__init__()
		self.mail_from = mail_from
	
	# TODO FIXME: define custom reject_* methods for specific scenarios
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(mail_from={self.mail_from!r})'


class RcptToEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = 'OK'
	error_code = 550
	error_message = 'address rejected'
	
	def __init__ ( self, rcpt_to: str ) -> None:
		super().__init__()
		self.rcpt_to = rcpt_to
	
	# TODO FIXME: define custom reject_* methods for specific scenarios
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(rcpt_to={self.rcpt_to!r})'


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


def _auth_lines ( auth_mechanisms: Iterable[str] ) -> Seq[str]:
	lines: List[str] = []
	line = ' '.join ( auth_mechanisms )
	while len ( line ) >= 71: # 80 - len ( '250-' ) - len ( 'AUTH ' )
		n = line.rindex ( ' ', 0, 71 ) # raises: ValueError # no auth name can be 71 characters! ( what is the limit? )
		lines.append ( f'AUTH {line[:n]}' )
		line = line[n:].lstrip()
	lines.append ( f'AUTH {line}' )
	return lines


class ServerState:
	def receive_line ( self, server: Server, line: bytes ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server.ServerState.receive_line' )
		#log.debug ( f'{line=}' )
		text = b2s ( line )
		if ' ' in text:
			command, textstring = map ( str.rstrip, text.split ( ' ', 1 ) )
		else:
			command, textstring = text.rstrip(), ''
		fname = f'on_{command.upper()}'
		try:
			f = getattr ( self, fname )
		except AttributeError:
			#log.debug ( f'{type(self).__module__}.{type(self).__name__} has no {fname}' )
			yield from server._singleline_response ( 500, f'command not recognized or not available: {command}' )
		else:
			#log.debug ( f'calling {f=}' )
			yield from f ( server, command, textstring )
	
	def on_EHLO ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		global auth_plugins
		
		if server.client_hostname and server.pedantic:
			yield from server._singleline_response ( 503, 'you already said HELO' )
			return
		
		server.client_hostname = textstring
		
		lines: List[str] = [ f'{server.hostname} greets {server.client_hostname}' ]
		
		if server.esmtp_pipelining:
			lines.append ( 'PIPELINING' )
		if server.esmtp_8bitmime:
			lines.append ( '8BITMIME' )
		
		lines.extend ( _auth_lines ( auth_plugins.keys() ) )
		
		yield from server._multiline_response ( 250, *lines )
	
	def on_EXPN ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		log = logger.getChild ( 'ServerState.on_EXPN' )
		log.debug ( f'{command=} {textstring=}' )
		yield from server._singleline_response ( 550, 'Access Denied!' )
	
	def on_HELO ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		# TODO FIXME: this is not correct, supposed to give a 503 if HELO/EHLO already requested, see RFC1869#4.2
		if server.client_hostname and server.pedantic:
			yield from server._singleline_response ( 503, 'you already said HELO' )
			return
		
		server.client_hostname = textstring
		yield from server._singleline_response ( 250, f'{server.hostname} greets {server.client_hostname}' )
	
	def on_NOOP ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._singleline_response ( 250, 'OK' )
	
	def on_QUIT ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		#log = logger.getChild ( 'ServerState.on_QUIT' )
		yield from server._singleline_response ( 250, 'OK' )
		raise Closed()
	
	def on_RSET ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._singleline_response ( 250, 'OK' )
	
	def on_STARTTLS ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		if textstring:
			yield server._singleline_response ( 501, 'Syntax error (no parameters allowed)' )
		else:
			yield from server.on_starttls()
	
	def on_VRFY ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._singleline_response ( 550, 'Access Denied!' )


class AuthPluginStatus ( metaclass = ABCMeta ):
	@abstractmethod
	def _resolve ( self, server: Server ) -> Iterator[Event]:
		''' this method is used internally by the server, do not call it yourself '''
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._resolve()' )


class AuthPluginStatus_Reply ( AuthPluginStatus ):
	def __init__ ( self, code: int, message: str ) -> None:
		assert isinstance ( code, int ) and 200 <= code <= 599, f'invalid {code=}'
		assert (
			isinstance ( message, str ) # message must be a str ( not bytes )
			and not _r_eol.search ( message ) # must not have \r or \n in it
		), (
			f'invalid {message=}'
		)
		self.code = code
		self.message = message
	
	def _resolve ( self, server: Server ) -> Iterator[Event]:
		if self.code >= 400:
			server.state = ServerState_Untrusted()
		yield from server._singleline_response ( self.code, self.message )


class AuthPluginStatus_Credentials ( AuthPluginStatus ):
	def __init__ ( self, uid: str, pwd: str ) -> None:
		self.uid = uid
		self.pwd = pwd
	
	def _resolve ( self, server: Server ) -> Iterator[Event]:
		yield from server.on_authenticate ( self.uid, self.pwd )


class AuthPlugin ( metaclass = ABCMeta ):
	@abstractmethod
	def first_line ( self, extra: str ) -> AuthPluginStatus:
		'''
		this method is called with any extra data when the auth method is instanciated.
		
		For example, if the following command were issued to the server:
			AUTH PLAIN dGVzdAB0ZXN0ADEyMzQ=
		then this function would get called with:
			extra = 'dGVzdAB0ZXN0ADEyMzQ='
		
		If however, this command were issued:
			AUTH PLAIN
		then this function gets called with:
			extra = ''
		'''
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.first_line()' )
	
	@abstractmethod
	def receive_line ( self, line: bytes ) -> AuthPluginStatus:
		'''
		this function gets called each time a client submits data to the server
		while this authentication mechanism is pending
		'''
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.receive_line()' )


auth_plugins: Dict[str,Type[AuthPlugin]] = {}

def auth_plugin ( name: str ) -> Callable[[Type[AuthPlugin]],Type[AuthPlugin]]:
	def registrar ( cls: Type[AuthPlugin] ) -> Type[AuthPlugin]:
		global auth_plugins
		assert name == name.upper() and ' ' not in name and len ( name ) <= 71, f'invalid auth mechanism {name=}'
		assert name not in auth_plugins, f'duplicate auth mechanism {name!r}'
		auth_plugins[name] = cls
		return cls
	return registrar


@auth_plugin ( 'PLAIN' )
class AuthPlugin_Plain ( AuthPlugin ):
	def first_line ( self, extra: str ) -> AuthPluginStatus:
		#log = logger.getChild ( 'AuthPlugin_Plain.first_line' )
		if extra:
			return self.receive_line ( s2b ( extra ) )
		else:
			return AuthPluginStatus_Reply ( 334, '' )
	
	def receive_line ( self, line: bytes ) -> AuthPluginStatus:
		log = logger.getChild ( 'AuthPlugin_Plain.receive_line' )
		try:
			_, uid, pwd = b2s ( base64.b64decode ( line ) ).split ( '\0' )
		except Exception as e:
			#log.error ( f'{e=}' )
			return AuthPluginStatus_Reply ( 501, 'malformed auth input RFC4616#2' )
		return AuthPluginStatus_Credentials ( uid, pwd )


@auth_plugin ( 'LOGIN' )
class AuthPlugin_Login ( AuthPlugin ):
	uid: Opt[str] = None
	
	def first_line ( self, extra: str ) -> AuthPluginStatus:
		#log = logger.getChild ( 'AuthPlugin_Login.first_line' )
		return AuthPluginStatus_Reply ( 334, b64_encode ( 'Username:' ) )
	
	def receive_line ( self, line: bytes ) -> AuthPluginStatus:
		#log = logger.getChild ( 'AuthPlugin_Login.receive_line' )
		if self.uid is None:
			self.uid = b2s ( base64.b64decode ( line ) )
			return AuthPluginStatus_Reply ( 334, b64_encode ( 'Password:' ) )
		else:
			assert isinstance ( self.uid, str )
			uid: str = self.uid
			pwd = b2s ( base64.b64decode ( line ) )
			return AuthPluginStatus_Credentials ( uid, pwd )


class ServerState_Untrusted ( ServerState ):
	def on_AUTH ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.ServerState_Untrusted.on_AUTH' )
		global auth_plugins
		mechanism, *extra = textstring.split ( ' ', 1 )
		mechanism = mechanism.upper()
		plugincls = auth_plugins.get ( mechanism )
		if plugincls is None:
			yield from server._singleline_response ( 504, f'Unrecognized authentication mechanism: {mechanism}' )
			return
		plugin = plugincls()
		log.warning ( 'TODO FIXME: are we in ssl and if not, is this auth plugin allowed to be used in an unencrypted state?' )
		server.state = ServerState_Auth ( plugin )
		status = plugin.first_line ( extra[0] if extra else '' )
		yield from status._resolve ( server )


class ServerState_Auth ( ServerState ):
	def __init__ ( self, plugin: AuthPlugin ) -> None:
		self.plugin = plugin
	
	def receive_line ( self, server: Server, line: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'ServerState_Auth.receive_line' )
		try:
			status: AuthPluginStatus = self.plugin.receive_line ( line )
		except Exception as e: # pragma: no cover # this is going to take some thinking on a clean way to test it
			log.error ( f'{e=}' )
			server.state = ServerState_Untrusted()
			yield from server._singleline_response ( 501, 'malformed auth input' )
		else:
			yield from status._resolve ( server )


class ServerState_Trusted ( ServerState ):
	def on_AUTH ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		yield from server._singleline_response ( 503, 'already authenticated (RFC4954#4 Restrictions)' )
	
	def on_RSET ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		server.reset()
		yield from super().on_RSET ( server, command, textstring )
	
	def on_MAIL ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server.ServerState_Trusted.on_MAIL' )
		#log.debug ( f'{command=} {textstring=}' )
		m = _r_mail_from.match ( textstring )
		if not m:
			yield from server._singleline_response ( 501, 'malformed MAIL input' )
		else:
			mail_from = m.group ( 1 ).strip()
			yield from server.on_mail_from ( mail_from )
	
	def on_RCPT ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server.ServerState_Trusted.on_RCPT' )
		#log.debug ( f'{command=} {textstring=}' )
		m = _r_rcpt_to.match ( textstring )
		if not m:
			yield from server._singleline_response ( 501, 'malformed RCPT input' )
		else:
			rcpt_to = m.group ( 1 ).strip()
			yield from server.on_rcpt_to ( rcpt_to )
	
	def on_DATA ( self, server: Server, command: str, textstring: str ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server.ServerState_Trusted.on_DATA' )
		#log.debug ( f'{command=} {textstring=}' )
		if not server.mail_from:
			yield from server._singleline_response ( 503, 'no from address received yet' )
		elif not server.rcpt_to:
			yield from server._singleline_response ( 503, 'no rcpt address(es) received yet' )
		else:
			server.state = ServerState_Data()
			yield from server._singleline_response ( 354, 'Start mail input; end with <CRLF>.<CRLF>' )


class ServerState_Data ( ServerState ):
	def receive_line ( self, server: Server, line: bytes ) -> Iterator[Event]:
		#log = logger.getChild ( 'ServerState_Data.receive_line' )
		#log.debug ( f'{line=}' )
		if line == b'.\r\n':
			yield from server.on_complete()
		elif line.startswith ( b'.' ):
			server.data.append ( line[1:] )
		else:
			server.data.append ( line )


class Server ( Connection ):
	client_hostname: str = ''
	mail_from: str
	rcpt_to: List[str]
	data: List[bytes]
	pedantic: bool = True # set this to False to relax behaviors that cause no harm for the protocol ( like double-HELO )
	esmtp_pipelining: bool = True # advertise that we support PIPELINING
	esmtp_8bitmime: bool = True # this currently doesn't do anything except advertise on EHLO ( not sure anything else is necessary )
	
	def __init__ ( self, hostname: str ) -> None:
		assert isinstance ( hostname, str ) and not _r_eol.search ( hostname ), f'invalid {hostname=}'
		self.hostname = hostname
		self.reset()
		self.state: ServerState = ServerState_Untrusted() # TODO FIXME: refactor away ServerState and collapse Request into Event objects that handle client/server logic, use a Server._auth_id: Opt[str] to identify trusted state...
	
	def greeting ( self ) -> bytes:
		# if too busy, can also return:
		#	421-{self.hostname} is too busy to accept mail right now.
		#	421 Please come back in {delay} seconds.
		#	(and server disconnects)
		# or:
		#	554 No SMTP service here
		# 	(server stays connected but 503's everything except QUIT)
		#	(this is a useful state if remote ip is untrusted via blacklisting/whitelisting )
		return s2b ( f'220 {self.hostname} ESMTP\r\n' )
	
	def _receive_line ( self, line: bytes ) -> Iterator[Event]:
		yield from self.state.receive_line ( self, line )
	
	def reset ( self ) -> None:
		self.mail_from = ''
		self.rcpt_to = []
		self.data = []
	
	def _singleline_response ( self, reply_code: int, text: str ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server._singleline_response' )
		assert isinstance ( reply_code, int ) and 100 <= reply_code <= 599, f'invalid {reply_code=}'
		assert isinstance ( text, str ) and not _r_eol.search ( text ), f'invalid {text=}'
		yield SendDataEvent ( s2b ( f'{reply_code} {text}\r\n' ) )
	
	def _multiline_response ( self, reply_code: int, *lines: str ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server._multiline_response' )
		assert isinstance ( reply_code, int ) and 100 <= reply_code <= 599, f'invalid {reply_code=}'
		seps = ( [ '-' ] * ( len ( lines ) - 1 ) ) + [ ' ' ]
		for line, sep in zip ( lines, seps ):
			assert isinstance ( line, str ) and not _r_eol.search ( line ), f'invalid {line=}'
			yield SendDataEvent ( s2b ( f'{reply_code}{sep}{line}\r\n' ) )
	
	def on_starttls ( self ) -> Iterator[Event]:
		event1 = StartTlsRequestEvent()
		yield event1
		accepted, code, message = event1._accepted()
		if not accepted:
			yield from self._singleline_response ( code, message )
			return
		event2 = StartTlsBeginEvent()
		yield event2
	
	def on_authenticate ( self, uid: str, pwd: str ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.on_authenticate' )
		event = AuthEvent ( uid, pwd )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			self.state = ServerState_Trusted()
		else:
			self.state = ServerState_Untrusted()
		yield from self._singleline_response ( code, message )
	
	def on_mail_from ( self, mail_from: str ) -> Iterator[Event]:
		event = MailFromEvent ( mail_from )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			self.mail_from = mail_from
		yield from self._singleline_response ( code, message )
	
	def on_rcpt_to ( self, rcpt_to: str ) -> Iterator[Event]:
		event = RcptToEvent ( rcpt_to )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			self.rcpt_to.append ( rcpt_to )
		yield from self._singleline_response ( code, message )
	
	def on_complete ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'Server.complete' )
		event = CompleteEvent ( self.mail_from, self.rcpt_to, self.data )
		self.reset()
		self.state = ServerState_Trusted()
		yield event
		accepted, code, message = event._accepted()
		yield from self._singleline_response ( code, message )

#endregion
#region CLIENT ----------------------------------------------------------------

class Response ( Exception ):
	def __init__ ( self, code: int, *lines: str ) -> None:
		self.code = code
		assert lines and isinstance ( lines[0], str ) # they should all be str but I'm being lazy here
		self.lines = lines
		super().__init__ ( code, *lines )
	
	@staticmethod
	def parse ( line: Opt[bytes] ) -> ResponseType:
		assert isinstance ( line, bytes )
		try:
			code = int ( line[:3] )
			assert 200 <= code <= 599, f'invalid {code=}'
			intermediate = line[3:4]
			text = b2s ( line[4:] ).rstrip()
			assert intermediate in ( b' ', b'-' )
		except Exception as e:
			raise Closed ( f'malformed response from server {line=}: {e=}' ) from e
		if intermediate == b'-':
			return IntermediateResponse ( code, text )
		if code < 400:
			return SuccessResponse ( code, text )
		else:
			return ErrorResponse ( code, text )
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}({self.code!r}, {", ".join(map(repr,self.lines))})'

class NeedDataEvent ( Event ):
	data: Opt[bytes] = None
	response: Opt[Response] = None

class SuccessResponse ( Response ):
	pass

class ErrorResponse ( Response ):
	pass

class IntermediateResponse ( Response ):
	pass

class Request ( metaclass = ABCMeta ):
	# TODO FIXME: this will become the basis of all client/server command handling
	# maybe rename to Command?
	# 1) client will use __init__() to construct request
	# 2) server will use @classmethod parse ( line: bytes ) to construct request ( experiment with calling __new__() directly to bypass client's __init__ )
	# 3) client-specific API that Client class will use to control status of multi-line interaction
	# 4) server-specific API that Server class will use for the same
	# AuthPlugin() should be able to inherit from this
	# users will be able to create their own custom Request/Command objects
	response: Opt[Response] = None
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}()'

def _client_proto_send ( line: str ) -> Iterator[Event]:
	assert line.endswith ( '\r\n' )
	yield SendDataEvent ( s2b ( line ) )

def _client_proto_recv ( event: NeedDataEvent() ) -> Iterator[Event]:
	event.data = None
	event.response = None
	yield event
	event.response = Response.parse ( event.data )

def _client_proto_recv_done() -> Iterator[Event]:
	log = logger.getChild ( '_client_proto_recv_done' )
	event = NeedDataEvent()
	log.debug ( 'waiting for data' )
	yield event
	log.debug ( f'{event.data=}' )
	response = Response.parse ( event.data )
	log.debug ( f'{response=}' )
	raise response

def _client_proto_send_recv_ok ( line: str ) -> Iterator[Event]:
	yield from _client_proto_send ( line )
	event = NeedDataEvent()
	yield event
	response = Response.parse ( event.data )
	if not isinstance ( response, SuccessResponse ):
		raise response

def _client_proto_send_recv_done ( line: str ) -> Iterator[Event]:
	yield from _client_proto_send ( line )
	yield from _client_proto_recv_done()

class GreetingRequest ( Request ):
	def __init__ ( self ) -> None:
		pass
	
	def send_data ( self ) -> Iterator[SendDataEvent]:
		yield from ()
	
	def on_success ( self, client: Client, response: Response ) -> Iterator[Event]:
		yield from ()
	
	def _client_protocol ( self ) -> Iterator[Event]:
		#log = logger.getChild ( 'GreetingRequest._client_protocol' )
		yield from _client_proto_recv_done()

class HeloRequest ( Request ):
	def __init__ ( self, domain: str ) -> None:
		self.domain = domain
	
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'HeloRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( f'HELO {self.domain}\r\n' )

class EhloResponse ( SuccessResponse ):
	esmtp_8bitmime: bool
	esmtp_auth: Set[str]
	esmtp_pipelining: bool
	esmtp_starttls: bool

class EhloRequest ( Request ):
	
	def __init__ ( self, domain: str ) -> None:
		self.domain = domain
		self.esmtp_auth = set()
	
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'EhloRequest._client_protocol' )
		yield from _client_proto_send ( f'EHLO {self.domain}\r\n' )
		event = NeedDataEvent()
		lines: List[str] = []
		
		esmtp_8bitmime: bool = False
		esmtp_auth: Set[str] = set()
		esmtp_pipelining: bool = False
		esmtp_starttls: bool = False
		
		while True:
			yield from _client_proto_recv ( event )
			tmp: Opt[Response] = event.response
			assert tmp is not None
			if isinstance ( tmp, ErrorResponse ):
				raise tmp
			line = tmp.lines[0]
			lines.append ( line )
			
			# TODO FIXME: some kind of plugin system so this is not hard-coded maybe?
			log.debug ( f'{line=}' )
			if line.startswith ( '8BITMIME' ):
				esmtp_8bitmime = True
			elif line.startswith ( 'AUTH ' ):
				for auth in line.split ( ' ' )[1:]:
					esmtp_auth.add ( auth )
			elif line.startswith ( 'PIPELINING' ):
				esmtp_pipelining = True
			elif line.startswith ( 'STARTTLS' ):
				esmtp_starttls = True
			if isinstance ( tmp, SuccessResponse ):
				r = EhloResponse ( tmp.code, *lines )
				r.esmtp_8bitmime = esmtp_8bitmime
				r.esmtp_auth = esmtp_auth
				r.esmtp_pipelining = esmtp_pipelining
				r.esmtp_starttls = esmtp_starttls
				raise r

class StartTlsRequest ( Request ):
	def __init__ ( self ) -> None:
		super().__init__ ( 'STARTTLS' )
	
	def send_data ( self ) -> Iterator[SendDataEvent]:
		#log = logger.getChild ( 'Request.send_data' )
		yield SendDataEvent ( s2b ( f'{self.line}\r\n' ) )
	
	def on_success ( self, client: Client, response: Response ) -> Iterator[Event]:
		yield StartTlsBeginEvent()

class _AuthRequest ( Request ):
	def __init__ ( self, uid: str, pwd: str ) -> None:
		self.uid = uid
		self.pwd = pwd

class AuthPlain1Request ( _AuthRequest ):
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'AuthPlain1Request._client_protocol' )
		authtext = b64_encode ( f'{self.uid}\0{self.uid}\0{self.pwd}' )
		yield from _client_proto_send_recv_done ( f'AUTH PLAIN {authtext}\r\n' )

class AuthPlain2Request ( _AuthRequest ):
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'AuthPlain1Request._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'AUTH PLAIN\r\n' )
		authtext = b64_encode ( f'{self.uid}\0{self.uid}\0{self.pwd}' )
		yield from _client_proto_send_recv_done ( f'{authtext}\r\n' )

class AuthLoginRequest ( _AuthRequest ):
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'AuthLoginRequest._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'AUTH LOGIN\r\n' )
		yield from _client_proto_send_recv_ok ( f'{b64_encode(self.uid)}\r\n' )
		yield from _client_proto_send_recv_done ( f'{b64_encode(self.pwd)}\r\n' )

class ExpnRequest ( Request ): # pragma: no cover # TODO FIXME this needs to be implemented
	def __init__ ( self, maillist: str ) -> None:
		self.maillist = maillist
	
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'ExpnRequest._client_protocol' )
		# TODO FIXME: this needs to be implemented
		yield from _client_proto_send_recv_done ( f'EXPN {self.maillist}\r\n' )

class VrfyRequest ( Request ): # pragma: no cover # TODO FIXME this needs to be implemented
	def __init__ ( self, mailbox: str ) -> None:
		self.mailbox = mailbox
	
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'ExpnRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( f'VRFY {self.mailbox}\r\n' )

class MailFromRequest ( Request ):
	def __init__ ( self, mail_from: str ) -> None:
		self.mail_from = mail_from
	
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'MailFromRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( f'MAIL FROM:<{self.mail_from}>\r\n' )

class RcptToRequest ( Request ):
	def __init__ ( self, rcpt_to: str ) -> None:
		self.rcpt_to = rcpt_to
	
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'RcptToRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( f'RCPT TO:<{self.rcpt_to}>\r\n' )

_r_crlf_dot = re.compile ( b'\\r\\n\\.', re.M )

class DataRequest ( Request ):
	initial_response: Opt[Response] = None
	
	def __init__ ( self, payload: bytes ) -> None:
		assert isinstance ( payload, bytes_types ) and len ( payload ) > 0
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
	
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'DataRequest._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'DATA\r\n' )
		payload = self.payload
		last = 0
		stitch = b'\r\n..'
		for m in _r_crlf_dot.finditer ( payload ):
			start = m.start()
			chunk = payload[last:start] # TODO FIXME: performance concern: does this copy or is it a view?
			log.debug ( f'{last=} {start=} {chunk=} {stitch=}' )
			yield SendDataEvent ( chunk )
			yield SendDataEvent ( stitch )
			last = start + 3
		tail = payload[last:]
		if tail:
			log.debug ( f'{last=} {tail=}' )
			yield SendDataEvent ( tail )
		yield from _client_proto_send_recv_done ( '\r\n.\r\n' )

class RsetRequest ( Request ):
	def _client_protocol ( self ) -> Iterator[Event]:
		yield from _client_proto_send_recv_done ( 'RSET\r\n' )

class NoOpRequest ( Request ):
	def _client_protocol ( self ) -> Iterator[Event]:
		yield from _client_proto_send_recv_done ( 'NOOP\r\n' )

class QuitRequest ( Request ):
	def _client_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'QuitRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( 'QUIT\r\n' )

class Client ( Connection ):
	request: Opt[Request] = None
	request_protocol: Opt[Iterator[Event]] = None
	need_data: Opt[NeedDataEvent] = None
	
	_multiline: List[str]
	
	def __init__ ( self ) -> None:
		self._multiline = []
	
	def send ( self, request: Request ) -> Iterator[Event]:
		#log = logger.getChild ( 'Client.send' )
		assert self.request is None, f'trying to send {request=} but not finished processing {self.request=}'
		self.request = request
		self.request_protocol = request._client_protocol()
		#log.debug ( f'set {self.request=}' )
		yield from self._run_protocol()
	
	def _run_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'Client._run_protocol' )
		while True:
			try:
				#log.debug ( 'yielding to request protocol' )
				event = next ( self.request_protocol )
				#log.debug ( f'{event=}' )
				if isinstance ( event, NeedDataEvent ):
					self.need_data = event
					return
				else:
					yield event
			except Closed as e:
				log.debug ( f'request protocol indication connection closure: {e=}' )
				self.request = None
				self.request_protocol = None
				raise
			except Response as response:
				log.debug ( f'request protocol finished with {response=}' )
				self.request.response = response
				self.request = None
				self.request_protocol = None
				if isinstance ( response, ErrorResponse ):
					raise
				return
			except StopIteration:
				log.exception ( 'request protocol exited without response' )
				self.request = None
				self.request_protocol = None
				return
	
	def _receive_line ( self, line: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'Client._receive_line' )
		
		if True:
			if self.need_data:
				#log.debug ( f'got data for protocol: {line=}' )
				self.need_data.data = line
				self.need_data = None
				yield from self._run_protocol()
			else:
				assert False, f'unexpected {line=}'
				try:
					reply_code = int ( line[:3] )
					intermed = line[3:4]
					textstring = b2s ( line[4:] ).rstrip()
					assert intermed in ( b' ', b'-' )
				except Exception as e:
					raise Closed ( f'malformed response from server {line=}: {e=}' ) from e
		else:
			
			try:
				reply_code = int ( line[:3] )
				intermed = line[3:4]
				textstring = b2s ( line[4:] ).rstrip()
				assert intermed in ( b' ', b'-' )
			except Exception as e:
				raise Closed ( f'malformed response from server {line=}: {e=}' ) from e
			intermediate = ( intermed == b'-' )
			
			if intermediate:
				#log.debug ( f'multiline not finished: {self._multiline=} + {textstring=}' )
				self._multiline.append ( textstring )
				return
			
			#log.debug ( f'clearing {self.request=}' )
			request, self.request = self.request, None
			assert isinstance ( request, Request )
			lines = self._multiline + [ textstring ]
			self._multiline = []
			#log.debug ( f'response finished: {lines=}' )
			if reply_code < 400:
				request.response = Response ( reply_code, *lines )
				#log.debug ( f'calling {request=}.on_success()' )
				yield from request.on_success ( self, request.response )
			else:
				raise ErrorResponse ( reply_code, *lines )

#endregion
