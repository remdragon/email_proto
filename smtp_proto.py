#region PROLOGUE --------------------------------------------------------------
from __future__ import annotations

from abc import ABCMeta, abstractmethod
import base64
import logging
import re
from typing import (
	Callable, Dict, Iterable, Iterator, List, Optional as Opt, Sequence as Seq,
	Set, Tuple, Type, TypeVar, Union,
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
_r_crlf_dot = re.compile ( b'\\r\\n\\.', re.M )

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

#endregion
#region EVENTS ----------------------------------------------------------------

class Event ( Exception ):
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}()'

class ThrowableEvent ( Event ):
	exception: Opt[Exception] = None # TODO FIXME: BaseException?
	
	def go ( self ) -> Iterator[Event]:
		yield self
		if self.exception:
			raise self.exception

class SendDataEvent ( ThrowableEvent ):
	
	def __init__ ( self, data: bytes ) -> None:
		assert isinstance ( data, bytes_types ) and len ( data ) > 0
		self.data = data
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(data={self.data!r})'

class ResponseEvent ( SendDataEvent ):
	def __init__ ( self, code: int, *lines: str ) -> None:
		assert isinstance ( code, int ), f'invalid {code=}'
		assert lines and all ( isinstance ( line, str ) for line in lines ), f'invalid {lines=}'
		seps = [ '-' ] * len ( lines )
		seps[-1] = ' '
		self.data = s2b ( ''.join (
			f'{code}{sep}{line}\r\n'
			for sep, line in zip ( seps, lines )
		) )

class AcceptRejectEvent ( Event ):
	success_code: int
	success_message: str
	error_code: int
	error_message: str
	
	def __init__ ( self ) -> None:
		self._acceptance: Opt[bool] = None
		self._code: int = self.error_code
		self._message: str = self.error_message
	
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
		#log = logger.getChild ( 'AcceptRejectEvent._accepted' )
		assert self._acceptance is not None, f'you must call .accept() or .reject() on when passed a {type(self).__module__}.{type(self).__name__} object'
		assert isinstance ( self._code, int )
		assert isinstance ( self._message, str )
		return self._acceptance, self._code, self._message
	
	def go ( self ) -> Iterator[Event]:
		yield self
		if not self._acceptance:
			raise ResponseEvent ( self._code, self._message )
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		args = ', '.join ( f'{k}={getattr(self,k)!r}' for k in (
			'_acceptance',
			'_code',
			'_message',
		) )
		return f'{cls.__module__}.{cls.__name__}({args})'


class StartTlsAcceptEvent ( AcceptRejectEvent ):
	success_code = 220
	success_message = 'Go ahead, make my day'
	error_code = 454
	error_message = 'TLS not available at the moment'


class StartTlsBeginEvent ( ThrowableEvent ):
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


class ExpnVrfyEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = '' # not used
	error_code = 550
	error_message = 'Access Denied!'
	
	def __init__ ( self, mailbox: str ) -> None:
		self.mailbox = mailbox
	
	def accept ( self, *mailboxes: str ) -> None:
		self._code = self.success_code
		self._acceptance = True
		assert mailboxes and all ( isinstance ( mailbox, str ) for mailbox in mailboxes ), f'invalid {mailboxes=}'
		self.mailboxes = mailboxes

class ExpnEvent ( ExpnVrfyEvent ):
	pass

class VrfyEvent ( ExpnVrfyEvent ):
	pass


class MailFromEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = 'OK'
	error_code = 550
	error_message = 'address rejected'
	
	def __init__ ( self, mail_from: str ) -> None:
		assert isinstance ( mail_from, str ) and len ( mail_from.strip() ) > 0, f'invalid {mail_from=}'
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

#endregion
#region RESPONSES -------------------------------------------------------------

ResponseType = TypeVar ( 'ResponseType', bound = 'Response' )
class Response ( Exception ):
	def __init__ ( self, code: int, *lines: str ) -> None:
		self.code = code
		assert lines and isinstance ( lines[0], str ) # they should all be str but I'm being lazy here
		self.lines = lines
		super().__init__ ( code, *lines )
	
	@staticmethod
	def parse ( line: Opt[bytes] ) -> Union[SuccessResponse,ErrorResponse,IntermediateResponse]:
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


class NeedDataEvent ( ThrowableEvent ):
	data: Opt[bytes] = None
	response: Opt[Response] = None
	
	def reset ( self ) -> NeedDataEvent:
		self.data = None
		self.response = None
		return self


class SuccessResponse ( Response ):
	pass

class ErrorResponse ( Response ):
	pass

class IntermediateResponse ( Response ):
	pass


class EhloResponse ( SuccessResponse ):
	esmtp_8bitmime: bool
	esmtp_auth: Set[str]
	esmtp_pipelining: bool
	esmtp_starttls: bool

class ExpnVrfyResponse ( SuccessResponse ):
	pass

class ExpnResponse ( ExpnVrfyResponse ):
	pass

class VrfyResponse ( ExpnVrfyResponse ):
	pass

#endregion
#region REQUESTS --------------------------------------------------------------

def _client_proto_send ( line: str ) -> Iterator[Event]:
	assert line.endswith ( '\r\n' )
	yield from ( event := SendDataEvent ( s2b ( line ) ) ).go()

def _client_proto_recv_ok ( event: NeedDataEvent ) -> Iterator[Event]:
	yield from event.reset().go()
	event.response = Response.parse ( event.data )
	if isinstance ( event.response, ErrorResponse ):
		raise event.response

def _client_proto_recv_done() -> Iterator[Event]:
	log = logger.getChild ( '_client_proto_recv_done' )
	yield from ( event := NeedDataEvent() ).go()
	response = Response.parse ( event.data )
	raise response

def _client_proto_send_recv_ok ( line: str ) -> Iterator[Event]:
	log = logger.getChild ( '_client_proto_send_recv_ok' )
	yield from _client_proto_send ( line )
	yield from ( event := NeedDataEvent() ).go()
	response = Response.parse ( event.data )
	if not isinstance ( response, SuccessResponse ):
		raise response

def _client_proto_send_recv_done ( line: str ) -> Iterator[Event]:
	yield from _client_proto_send ( line )
	yield from _client_proto_recv_done()


_request_verbs: Dict[str,Type[Request]] = {}

def request_verb ( verb: str ) -> Callable[[Type[Request]],Type[Request]]:
	def registrar ( cls: Type[Request] ) -> Type[Request]:
		global _request_verbs
		assert verb == verb.upper() and ' ' not in verb and len ( verb ) <= 71, f'invalid auth mechanism {verb=}'
		assert verb not in _request_verbs, f'duplicate request verb {verb!r}'
		_request_verbs[verb] = cls
		return cls
	return registrar

_auth_plugins: Dict[str,Type[_Auth]] = {}

def auth_plugin ( name: str ) -> Callable[[Type[_Auth]],Type[_Auth]]:
	def registrar ( cls: Type[_Auth] ) -> Type[_Auth]:
		global _auth_plugins
		assert name == name.upper() and ' ' not in name and len ( name ) <= 71, f'invalid auth mechanism {name=}'
		assert name not in _auth_plugins, f'duplicate auth mechanism {name!r}'
		_auth_plugins[name] = cls
		return cls
	return registrar


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
	
	@abstractmethod
	def _client_protocol ( self, client: Client ) -> Iterator[Event]: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._client_protocol()' )
	
	@abstractmethod
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._server_protocol()' )


class GreetingRequest ( Request ):
	def __init__ ( self ) -> None:
		pass
	
	def send_data ( self ) -> Iterator[SendDataEvent]:
		yield from ()
	
	def on_success ( self, client: Client, response: Response ) -> Iterator[Event]:
		yield from ()
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'GreetingRequest._client_protocol' )
		yield from _client_proto_recv_done()
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]: # pragma: no cover
		assert False # this should never get called


@request_verb ( 'HELO' )
class HeloRequest ( Request ):
	def __init__ ( self, domain: str ) -> None:
		self.domain = domain
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'HeloRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( f'HELO {self.domain}\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		if not argtext:
			raise ResponseEvent ( 501, 'missing required hostname parameter' )
		if server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'you already said HELO RFC1869#4.2' )
		else:
			server.client_hostname = argtext
			raise ResponseEvent ( 250, f'{server.hostname} greets {server.client_hostname}' )


@request_verb ( 'EHLO' )
class EhloRequest ( Request ):
	
	def __init__ ( self, domain: str ) -> None:
		self.domain = domain
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		log = logger.getChild ( 'EhloRequest._client_protocol' )
		yield from _client_proto_send ( f'EHLO {self.domain}\r\n' )
		event = NeedDataEvent()
		lines: List[str] = []
		
		esmtp_8bitmime: bool = False
		esmtp_auth: Set[str] = set()
		esmtp_pipelining: bool = False
		esmtp_starttls: bool = False
		
		while True:
			yield from _client_proto_recv_ok ( event )
			tmp: Opt[Response] = event.response
			assert tmp is not None
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
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		if not argtext:
			raise ResponseEvent ( 501, 'missing required hostname parameter' )
		if server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'you already said HELO RFC1869#4.2' )
		server.client_hostname = argtext
		lines: List[str] = [ f'{server.hostname} greets {server.client_hostname}' ]
		if server.esmtp_8bitmime:
			lines.append ( '8BITMIME' )
		available_auth_plugins = [
			name for name, plugin in _auth_plugins.items()
			if server.tls or not plugin.tls_required
		]
		for line in _auth_lines ( available_auth_plugins ):
			lines.append ( line )
		if server.esmtp_pipelining:
			lines.append ( 'PIPELINING' )
		if not server.tls:
			lines.append ( 'STARTTLS' )
		yield ResponseEvent ( 250, *lines )


@request_verb ( 'STARTTLS' )
class StartTlsRequest ( Request ): # RFC3207 SMTP Service Extension for Secure SMTP over Transport Layer Security
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'StartTlsRequest._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'STARTTLS\r\n' )
		yield from ( event := StartTlsBeginEvent() ).go()
		client.tls = True
		yield from _client_proto_recv_done()
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		log = logger.getChild ( 'StartTlsRequest._server_protocol' )
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if argtext:
			raise ResponseEvent ( 501, 'Syntax error (no extra parameters allowed)' )
		yield from ( event1 := StartTlsAcceptEvent() ).go()
		yield ResponseEvent ( event1._code, event1._message )
		yield from StartTlsBeginEvent().go()
		server.tls = True
		yield ResponseEvent ( 220, f'{server.hostname} ESMTP' )



@request_verb ( 'AUTH' )
class _Auth ( Request ):
	tls_required: bool = True
	
	def __init__ ( self, uid: str, pwd: str ) -> None:
		self.uid = uid
		self.pwd = pwd
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]: # pragma: no cover
		assert False # not used
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		log = logger.getChild ( '_Auth._server_protocol' )
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if server.auth_mailbox:
			raise ResponseEvent ( 503, 'already authenticated (RFC4954#4 Restrictions)' )
		mechanism, *moreargtext = argtext.split ( ' ', 1 ) # ex: mechanism='PLAIN' moreargtext=['FUBAR']
		log.debug ( f'{mechanism=} {moreargtext=}' )
		plugincls = _auth_plugins.get ( mechanism )
		if plugincls is None:
			raise ResponseEvent ( 504, f'Unrecognized authentication mechanism: {mechanism}' )
		if plugincls.tls_required and not server.tls:
			raise ResponseEvent ( 535, 'SSL/TLS connection required' )
		plugin: _Auth = plugincls.__new__ ( plugincls ) # bypass __init__()
		yield from plugin._server_protocol ( server, moreargtext[0] if moreargtext else '' )
	
	def _on_authenticate ( self, server: Server, uid: str, pwd: str ) -> Iterator[Event]:
		yield from ( event := AuthEvent ( uid, pwd ) ).go()
		server.auth_mailbox = uid
		yield ResponseEvent ( event._code, event._message )


@auth_plugin ( 'PLAIN' )
class AuthPlainRequest ( _Auth ):
	def _client_protocol ( self, client: Client ) -> Iterator[Event]: # pragma: no cover
		assert False # use AuthPlain1Request or AuthPlain2Request below
	
	def _server_protocol ( self, server: Server, moreargtext: str ) -> Iterator[Event]:
		log = logger.getChild ( 'AuthPlainRequest._server_protocol' )
		try:
			if not ( authtext := moreargtext ):
				yield ResponseEvent ( 334, '' )
				yield from ( event := NeedDataEvent() ).go()
				authtext = b2s ( event.data or b'' ).rstrip()
			_, uid, pwd = b64_decode ( authtext ).split ( '\0' )
		except Exception as e:
			log.debug ( f'malformed auth input {moreargtext=}: {e=}' )
			yield ResponseEvent ( 501, 'malformed auth input RFC4616#2' )
		else:
			yield from self._on_authenticate ( server, uid, pwd )


class AuthPlain1Request ( AuthPlainRequest ):
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'AuthPlain1Request._client_protocol' )
		authtext = b64_encode ( f'{self.uid}\0{self.uid}\0{self.pwd}' )
		yield from _client_proto_send_recv_done ( f'AUTH PLAIN {authtext}\r\n' )

class AuthPlain2Request ( AuthPlainRequest ):
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'AuthPlain2Request._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'AUTH PLAIN\r\n' )
		authtext = b64_encode ( f'{self.uid}\0{self.uid}\0{self.pwd}' )
		yield from _client_proto_send_recv_done ( f'{authtext}\r\n' )


@auth_plugin ( 'LOGIN' )
class AuthLoginRequest ( _Auth ):
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'AuthLoginRequest._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'AUTH LOGIN\r\n' )
		yield from _client_proto_send_recv_ok ( f'{b64_encode(self.uid)}\r\n' )
		yield from _client_proto_send_recv_done ( f'{b64_encode(self.pwd)}\r\n' )
	
	def _server_protocol ( self, server: Server, moreargtext: str ) -> Iterator[Event]:
		log = logger.getChild ( 'AuthLoginRequest._server_protocol' )
		if moreargtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no extra parameters allowed)' )
		event = NeedDataEvent()
		try:
			yield ResponseEvent ( 334, b64_encode ( 'Username:' ) )
			yield event
			uid = b2s ( base64.b64decode ( event.data or b'' ) ).rstrip()
			yield ResponseEvent ( 334, b64_encode ( 'Password:' ) )
			yield event
			pwd = b2s ( base64.b64decode ( event.data or b'' ) ).rstrip()
		except Exception as e:
			log.error ( f'{e=}' )
			yield ResponseEvent ( 501, 'malformed auth input RFC4616#2' )
		else:
			yield from self._on_authenticate ( server, uid, pwd )


class ExpnVrfyRequest ( Request ):
	_verb: str
	_response: Type[ExpnVrfyResponse]
	_event: Type[ExpnVrfyEvent]
	
	def __init__ ( self, mailbox: str ) -> None:
		self.mailbox = mailbox
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'ExpnRequest._client_protocol' )
		yield from _client_proto_send ( f'{self._verb} {self.mailbox}\r\n' )
		event = NeedDataEvent()
		lines: List[str] = []
		
		while True:
			yield from _client_proto_recv_ok ( event )
			tmp: Opt[Response] = event.response
			assert tmp is not None
			lines.append ( tmp.lines[0] )
			if isinstance ( tmp, SuccessResponse ):
				raise self._response ( tmp.code, *lines )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]: # raises: ResponseEvent
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if not server.auth_mailbox:
			raise ResponseEvent ( 513, 'Must authenticate' )
		if not argtext:
			raise ResponseEvent ( 501, 'missing required mailbox parameter' )
		event = self._event ( argtext )
		yield event
		assert isinstance ( event._code, int )
		if event._acceptance:
			assert event.mailboxes is not None
			yield ResponseEvent ( event._code, *event.mailboxes )
		else:
			assert event._message is not None
			yield ResponseEvent ( event._code, event._message )


@request_verb ( 'EXPN' )
class ExpnRequest ( ExpnVrfyRequest ):
	_verb = 'EXPN'
	_response = ExpnResponse
	_event = ExpnEvent


@request_verb ( 'VRFY' )
class VrfyRequest ( ExpnVrfyRequest ):
	_verb = 'VRFY'
	_response = VrfyResponse
	_event = VrfyEvent


@request_verb ( 'MAIL' )
class MailFromRequest ( Request ):
	def __init__ ( self, mail_from: str ) -> None:
		self.mail_from = mail_from
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'MailFromRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( f'MAIL FROM:<{self.mail_from}>\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if not server.auth_mailbox:
			raise ResponseEvent ( 513, 'Must authenticate' )
		m = _r_mail_from.match ( argtext )
		if not m:
			raise ResponseEvent ( 501, 'malformed MAIL input' )
		mail_from = m.group ( 1 )
		event = MailFromEvent ( mail_from )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			server.mail_from = mail_from
		yield ResponseEvent ( code, message )


@request_verb ( 'RCPT' )
class RcptToRequest ( Request ):
	def __init__ ( self, rcpt_to: str ) -> None:
		self.rcpt_to = rcpt_to
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'RcptToRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( f'RCPT TO:<{self.rcpt_to}>\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if not server.auth_mailbox:
			raise ResponseEvent ( 513, 'Must authenticate' )
		m = _r_rcpt_to.match ( argtext )
		if not m:
			raise ResponseEvent ( 501, 'malformed RCPT input' )
		rcpt_to = m.group ( 1 )
		event = RcptToEvent ( rcpt_to )
		yield event
		accepted, code, message = event._accepted()
		if accepted:
			server.rcpt_to.append ( rcpt_to )
		yield ResponseEvent ( code, message )


@request_verb ( 'DATA' )
class DataRequest ( Request ):
	initial_response: Opt[Response] = None
	
	def __init__ ( self, payload: bytes ) -> None:
		assert isinstance ( payload, bytes_types ) and len ( payload ) > 0
		self.payload: bytes = payload # only used on client side because on server side it is accumulated in Server.data
	
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		log = logger.getChild ( 'DataRequest._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'DATA\r\n' )
		payload = self.payload
		last = 0
		stitch = b'\r\n..'
		for m in _r_crlf_dot.finditer ( payload ):
			start = m.start()
			chunk = payload[last:start] # TODO FIXME: performance concern: does this copy or is it a view?
			#log.debug ( f'{last=} {start=} {chunk=} {stitch=}' )
			yield SendDataEvent ( chunk )
			yield SendDataEvent ( stitch )
			last = start + 3
		tail = payload[last:]
		if tail:
			#log.debug ( f'{last=} {tail=}' )
			yield SendDataEvent ( tail )
		yield from _client_proto_send_recv_done ( '\r\n.\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if argtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
		if not server.auth_mailbox:
			raise ResponseEvent ( 513, 'Must authenticate' )
		if not server.mail_from:
			raise ResponseEvent ( 503, 'no from address received yet' )
		if not server.rcpt_to:
			raise ResponseEvent ( 503, 'no rcpt address(es) received yet' )
		yield ResponseEvent ( 354, 'Start mail input; end with <CRLF>.<CRLF>' )
		event1 = NeedDataEvent()
		while True:
			yield from event1.go()
			line = event1.data or b''
			if line == b'.\r\n':
				break
			elif line.startswith ( b'.' ):
				server.data.append ( line[1:] )
			else:
				server.data.append ( line )
		event2 = CompleteEvent ( server.mail_from, server.rcpt_to, server.data )
		server.reset() # is this correct? reset even if we're going to return an error?
		yield event2
		_, code, message = event2._accepted()
		yield ResponseEvent ( code, message )


@request_verb ( 'RSET' )
class RsetRequest ( Request ):
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		yield from _client_proto_send_recv_done ( 'RSET\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		if argtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
		server.reset()
		yield ResponseEvent ( 250, 'OK' )


@request_verb ( 'NOOP' )
class NoOpRequest ( Request ):
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		yield from _client_proto_send_recv_done ( 'NOOP\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		# FYI `argtext` is ignored per RFC 5321 4.1.1.9
		yield ResponseEvent ( 250, 'OK' )


@request_verb ( 'QUIT' )
class QuitRequest ( Request ):
	def _client_protocol ( self, client: Client ) -> Iterator[Event]:
		#log = logger.getChild ( 'QuitRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( 'QUIT\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> Iterator[Event]:
		if argtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
		yield ResponseEvent ( 221, 'Closing connection' )
		raise Closed ( 'QUIT' )

#endregion
#region COMMON ----------------------------------------------------------------

class Connection ( metaclass = ABCMeta ):
	_buf: bytes = b''
	request: Opt[Request] = None
	request_protocol: Opt[Iterator[Event]] = None
	need_data: Opt[NeedDataEvent] = None
	tls: bool # whether or not the connection is currently encrypted
	
	def __init__ ( self, tls: bool ) -> None:
		self.tls = tls
	
	def receive ( self, data: bytes ) -> Iterator[Event]:
		#log = logger.getChild ( 'Connection.receive' )
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
				# we normally wait until done yielding all events, but exceptions abort our loop, so clean up now:
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
	
	def _run_protocol ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'Client._run_protocol' )
		assert self.request is not None
		assert self.request_protocol is not None
		try:
			while True:
				#log.debug ( 'yielding to request protocol' )
				event = next ( self.request_protocol )
				#log.debug ( f'{event=}' )
				if isinstance ( event, NeedDataEvent ):
					if self.request.response is not None: # pragma: no cover
						log.warning ( f'INTERNAL ERROR - {self.request!r} pushed NeedDataEvent but has a response set - this can cause upstack deadlock ({self.request.response!r})' )
						self.request.response = None
					self.need_data = event.reset()
					return
				else:
					yield event
		except Closed as e:
			#log.debug ( f'protocol indicated connection closure: {e=}' )
			self.request = None
			self.request_protocol = None
			raise
		except Response as response: # client protocol
			#log.debug ( f'protocol finished with {response=}' )
			self.request.response = response
			self.request = None
			self.request_protocol = None
			if isinstance ( response, ErrorResponse ):
				raise
		except SendDataEvent as event: # server protocol
			#log.debug ( f'protocol finished with {event=}' )
			self.request = None
			self.request_protocol = None
			yield event
		except StopIteration:
			# client protocol *must* raise a ResponseEvent *or* set it's response attribute before exiting
			# if not, the smtp_[a]sync.Client._recv() will get stuck waiting for data that never arrives
			if not self.request.response and isinstance ( self, Client ): # pragma: no cover
				log.warning (
					f'INTERNAL ERROR:'
					f' {type(self.request).__module__}.{type(self.request).__name__}'
					f'._client_protocol() exit w/o response - this can cause upstack deadlock'
				)
				self.request.response = ErrorResponse ( 500, 'INTERNAL PROTOCOL IMPLEMENTATION ERROR' )
			#log.debug ( f'protocol finished with {self.request.response=}' )
			self.request = None
			self.request_protocol = None

#endregion
#region SERVER ----------------------------------------------------------------

def _auth_lines ( auth_mechanisms: Iterable[str] ) -> Seq[str]:
	lines: List[str] = []
	if auth_mechanisms:
		line = ' '.join ( auth_mechanisms )
		while len ( line ) >= 71: # 80 - len ( '250-' ) - len ( 'AUTH ' )
			n = line.rindex ( ' ', 0, 71 ) # raises: ValueError # no auth name can be 71 characters! ( what is the limit? )
			lines.append ( f'AUTH {line[:n]}' )
			line = line[n:].lstrip()
		lines.append ( f'AUTH {line}' )
	return lines


class Server ( Connection ):
	client_hostname: str = ''
	auth_mailbox: Opt[str] = None
	mail_from: str
	rcpt_to: List[str]
	data: List[bytes]
	pedantic: bool = True # set this to False to relax behaviors that cause no harm for the protocol ( like double-HELO )
	esmtp_pipelining: bool = True # advertise that we support PIPELINING
	esmtp_8bitmime: bool = True # this currently doesn't do anything except advertise on EHLO ( not sure anything else is necessary )
	
	def __init__ ( self, hostname: str, tls: bool ) -> None:
		assert isinstance ( hostname, str ) and not _r_eol.search ( hostname ), f'invalid {hostname=}'
		self.hostname = hostname
		super().__init__ ( tls )
		self.reset()
	
	def greeting ( self ) -> bytes:
		# TODO FIXME: figure out how to move this to GreetingRequest._server_protocol()
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
		#log = logger.getChild ( 'Server._receive_line' )
		if self.need_data:
			self.need_data.data = line
			self.need_data = None
			yield from self._run_protocol()
		elif self.request is None:
			verb, *argtext = map ( str.rstrip, b2s ( line ).split ( ' ', 1 ) ) # ex: verb='DATA', argtext=[] or verb='AUTH', argtext=['PLAIN XXXXXXXXXXXXX']
			requestcls = _request_verbs.get ( verb )
			if requestcls is None:
				yield ResponseEvent ( 500, 'Command not recognized' )
				return
			try:
				request: Request = requestcls.__new__ ( requestcls )
				request_protocol = request._server_protocol ( self, argtext[0] if argtext else '' )
			except SendDataEvent as event: # this can happen if there's a problem parsing the command
				yield event
			else:
				self.request = request
				self.request_protocol = request_protocol
				yield from self._run_protocol()
		else:
			assert False, 'server internal state error - not waiting for data but a request is active'
	
	def reset ( self ) -> None:
		self.mail_from = ''
		self.rcpt_to = []
		self.data = []

#endregion
#region CLIENT ----------------------------------------------------------------

class Client ( Connection ):
	
	def send ( self, request: Request ) -> Iterator[Event]:
		log = logger.getChild ( 'Client.send' )
		assert self.request is None, f'trying to send {request=} but not finished processing {self.request=}'
		self.request = request
		try:
			self.request_protocol = request._client_protocol ( self )
		except TypeError:
			log.error ( f'problem calling {request=}._client_protocl()' )
			raise
		#log.debug ( f'set {self.request=}' )
		yield from self._run_protocol()
	
	def _receive_line ( self, line: bytes ) -> Iterator[Event]:
		log = logger.getChild ( 'Client._receive_line' )
		
		if self.need_data:
			self.need_data.data = line
			self.need_data = None
			yield from self._run_protocol()
		else:
			raise ProtocolError ( f'not expecting data at this time ({line!r})' )

#endregion
