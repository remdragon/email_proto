#region PROLOGUE --------------------------------------------------------------
from __future__ import annotations

# python imports:
from abc import ABCMeta, abstractmethod
import base64
import logging
import re
import traceback
from types import TracebackType
from typing import (
	Callable, Dict, Generator, Iterable, Iterator, List, Optional as Opt,
	Sequence as Seq, Set, Tuple, Type, TypeVar, Union,
)

# email_proto imports:
from base_proto import (
	BaseResponse, ResponseType, BaseRequest, RequestT, Event, NeedDataEvent,
	SendDataEvent, Closed, RequestProtocolGenerator, ClientProtocol,
	ServerProtocol,
	ClientUtil,
)
from util import bytes_types, BYTES, b2s, s2b, b64_encode_str, b64_decode_str

logger = logging.getLogger ( __name__ )


_r_eol = re.compile ( r'[\r\n]' )
_r_mail_from = re.compile ( r'\s*FROM\s*:\s*<?([^>]*)>?\s*$', re.I ) # RFC5321#2.4 command verbs are not case sensitive
_r_rcpt_to = re.compile ( r'\s*TO\s*:\s*<?([^>]*)>?\s*$', re.I ) # RFC5321#2.4 command verbs are not case sensitive
_r_crlf_dot = re.compile ( b'\\r\\n\\.', re.M )

#endregion
#region RESPONSES -------------------------------------------------------------

class Response ( BaseResponse ):
	def __init__ ( self, code: int, *lines: str ) -> None:
		self.code = code
		assert lines and all ( isinstance ( line, str ) for line in lines ), f'invalid {lines=}'
		self.lines = lines
		super().__init__()
	
	@staticmethod
	def parse ( line: BYTES ) -> Union[SuccessResponse,ErrorResponse,IntermediateResponse]:
		#log = logger.getChild ( 'Response.parse' )
		assert isinstance ( line, bytes_types )
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


class SuccessResponse ( Response ):
	def __init__ ( self, code: int, *lines: str ) -> None:
		assert 200 <= code < 400
		super().__init__ ( code, *lines )
	def is_success ( self ) -> bool:
		return True


class ErrorResponse ( Response ):
	def __init__ ( self, code: int, *lines: str ) -> None:
		assert 400 <= code <= 599
		super().__init__ ( code, *lines )
	def is_success ( self ) -> bool:
		return False

class IntermediateResponse ( Response ):
	def is_success ( self ) -> bool:
		return True


class EhloResponse ( SuccessResponse ):
	esmtp_auth: Set[str] # AUTH mechanisms get parsed and stored here
	esmtp_features: Dict[str,str] # all other features documented here


class ExpnVrfyResponse ( SuccessResponse ):
	pass

class ExpnResponse ( ExpnVrfyResponse ):
	pass

class VrfyResponse ( ExpnVrfyResponse ):
	pass


client_util = ClientUtil ( Response.parse )

#endregion
#region EVENTS ----------------------------------------------------------------

def ResponseEvent ( code: int, *lines: str ) -> SendDataEvent:
	seps = [ '-' ] * len ( lines )
	seps[-1] = ' '
	chunks = ( s2b ( ''.join (
		f'{code}{sep}{line}\r\n'
		for sep, line in zip ( seps, lines )
	) ), )
	return SendDataEvent ( *chunks )


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


class GreetingAcceptEvent ( AcceptRejectEvent ):
	success_code = 220
	error_code = 421
	error_message = 'Too busy to accept mail right now'
	
	def __init__ ( self, server_hostname: str ) -> None:
		self.success_message = f'{server_hostname} ESMTP'
		super().__init__()


class HeloAcceptEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = '' # customized by HeloRequest._server_protocol
	error_code = 454
	error_message = 'SMTP service not available at the moment'


class EhloAcceptEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = '' # customized by EhloRequest._server_protocol
	error_code = 454
	error_message = 'SMTP service not available at the moment'
	
	esmtp_auth: Set[str]
	esmtp_features: Dict[str,str]


class StartTlsAcceptEvent ( AcceptRejectEvent ):
	success_code = 220
	success_message = 'Go ahead, make my day'
	error_code = 454
	error_message = 'TLS not available at the moment'


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


class ExpnVrfyEvent ( AcceptRejectEvent ):
	success_code = 250
	success_message = '' # not used
	error_code = 550
	error_message = 'Access Denied!'
	mailboxes: Seq[str]
	
	def __init__ ( self, mailbox: str ) -> None:
		self.mailbox = mailbox
		super().__init__()
	
	def accept ( self, *mailboxes: str ) -> None:
		self._code = self.success_code
		self._acceptance = True
		#assert mailboxes and all ( isinstance ( mailbox, str ) for mailbox in mailboxes ), f'invalid {mailboxes=}'
		self.mailboxes: Seq[str] = mailboxes

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
		#assert isinstance ( mail_from, str ) and len ( mail_from.strip() ) > 0, f'invalid {mail_from=}'
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
		#assert isinstance ( rcpt_to, str ) and len ( rcpt_to.strip() ) > 0, f'invalid {rcpt_to=}'
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
#region REQUESTS --------------------------------------------------------------

class Request ( RequestT[ResponseType] ):
	def _client_protocol ( self, client: ClientProtocol ) -> RequestProtocolGenerator:
		assert isinstance ( client, Client )
		yield from self.client_protocol ( client )
	
	@classmethod
	def subparse ( cls: Type[Request[ResponseType]],
		server: Server,
		argtext: str,
	) -> Tuple[Type[Request[ResponseType]],str]:
		return cls, argtext
	
	@abstractmethod
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		cls = self.__class__
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.client_protocol()' )
	
	def _server_protocol ( self, server: ServerProtocol, prefix: str, suffix: str ) -> RequestProtocolGenerator:
		assert isinstance ( server, Server )
		assert not prefix
		yield from self.server_protocol ( server, suffix )
	
	@abstractmethod
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		cls = self.__class__
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.server_protocol()' )


_request_verbs: Dict[str,Type[BaseRequest]] = {}

def request_verb ( verb: str ) -> Callable[[Type[BaseRequest]],Type[BaseRequest]]:
	def registrar ( cls: Type[BaseRequest] ) -> Type[BaseRequest]:
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


class GreetingRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'GreetingRequest.client_protocol' )
		yield from client_util.recv_done()
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		# if too busy, can also return:
		#	421-{self.hostname} is too busy to accept mail right now.
		#	421 Please come back in {delay} seconds.
		#	(and server disconnects)
		# or:
		#	554 No SMTP service here
		# 	(server stays connected but 503's everything except QUIT)
		#	(this is a useful state if remote ip is untrusted via blacklisting/whitelisting )
		event = GreetingAcceptEvent ( server.hostname )
		yield from event.go()
		accepted, code, message = event._accepted()
		yield ResponseEvent ( code, message )


@request_verb ( 'HELO' )
class HeloRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def __init__ ( self, domain: str ) -> None:
		self.domain = str ( domain ).strip()
		assert len ( self.domain ) > 0
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'HeloRequest.client_protocol' )
		yield from client_util.send_recv_done ( f'HELO {self.domain}\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'HeloRequest.server_protocol' )
		if not argtext:
			raise ResponseEvent ( 501, 'missing required hostname parameter' )
		if server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'you already said HELO RFC1869#4.2' )
		
		client_hostname = argtext
		
		event = HeloAcceptEvent()
		event.success_message = f'{server.hostname} greets {client_hostname}'
		
		yield from event.go()
		
		server.client_hostname = client_hostname
		
		raise ResponseEvent ( event._code, event._message )


@request_verb ( 'EHLO' )
class EhloRequest ( Request[EhloResponse] ):
	responsecls = EhloResponse
	
	def __init__ ( self, domain: str ) -> None:
		self.domain = str ( domain ).strip()
		assert len ( self.domain ) > 0
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'EhloRequest.client_protocol' )
		yield from client_util.send ( f'EHLO {self.domain}\r\n' )
		event = NeedDataEvent()
		lines: List[str] = []
		
		esmtp_features: Dict[str,str] = {}
		esmtp_auth: Set[str] = set()
		
		while True:
			yield from client_util.recv_ok ( event )
			assert isinstance ( event.response, Response )
			tmp: Opt[Response] = event.response
			assert tmp is not None
			lines.append ( tmp.lines[0] )
			if isinstance ( tmp, SuccessResponse ):
				for line in lines[1:]:
					
					if line.startswith ( 'AUTH ' ):
						for auth in line.split ( ' ' )[1:]:
							esmtp_auth.add ( auth )
					else:
						name, *args = line.split ( ' ', 1 )
						esmtp_features[name] = args[0] if args else ''
				r = EhloResponse ( tmp.code, *lines )
				r.esmtp_features = esmtp_features
				r.esmtp_auth = esmtp_auth
				raise r
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if not argtext:
			raise ResponseEvent ( 501, 'missing required hostname parameter' )
		if server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'you already said HELO RFC1869#4.2' )
		
		client_hostname = argtext
		
		event = EhloAcceptEvent()
		event.esmtp_features = dict ( server.esmtp_features )
		if not server.tls:
			event.esmtp_features['STARTTLS'] = ''
		event.esmtp_auth = set ( [
			name for name, plugin in _auth_plugins.items()
			if server.tls or not plugin.tls_required
		] )
		event.success_message = f'{server.hostname} greets {client_hostname}'
		
		yield from event.go()
		
		server.client_hostname = client_hostname
		
		lines: List[str] = [ event.success_message ]
		for name, value in event.esmtp_features.items():
			if value:
				lines.append ( f'{name} {value}' )
			else:
				lines.append ( name )
		for line in _auth_lines ( event.esmtp_auth ):
			lines.append ( line )
		
		yield ResponseEvent ( 250, *lines )


@request_verb ( 'STARTTLS' )
class StartTlsRequest ( Request[SuccessResponse] ): # RFC3207 SMTP Service Extension for Secure SMTP over Transport Layer Security
	responsecls = SuccessResponse
	tls_excluded = True
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'StartTlsRequest.client_protocol' )
		yield from client_util.send_recv_ok ( 'STARTTLS\r\n' )
		yield from ( event := StartTlsBeginEvent() ).go()
		client.tls = True
		yield from client_util.recv_done()
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'StartTlsRequest._server_protocol' )
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if argtext:
			raise ResponseEvent ( 501, 'Syntax error (no extra parameters allowed)' )
		yield from ( event1 := StartTlsAcceptEvent() ).go()
		yield ResponseEvent ( event1._code, event1._message )
		yield from StartTlsBeginEvent().go()
		
		server.tls = True
		server.client_hostname = '' # client must say HELO again
		# TODO FIXME: server.reset()?
		
		event = GreetingAcceptEvent ( server.hostname )
		yield from event.go()
		accepted, code, message = event._accepted()
		yield ResponseEvent ( code, message )



@request_verb ( 'AUTH' )
class _Auth ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	tls_required: bool = True
	
	def __init__ ( self, uid: str, pwd: str ) -> None:
		self.uid = str ( uid )
		self.pwd = str ( pwd )
		assert len ( self.uid ) > 0
		assert len ( self.pwd ) > 0
	
	@classmethod
	def subparse ( cls: Type[Request[SuccessResponse]],
		server: Server,
		argtext: str,
	) -> Tuple[Type[Request[SuccessResponse]],str]:
		log = logger.getChild ( '_Auth.subparse' )
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if server.auth_uid:
			raise ResponseEvent ( 503, 'already authenticated (RFC4954#4 Restrictions)' )
		mechanism, *moreargtext = argtext.split ( ' ', 1 ) # ex: mechanism='PLAIN' moreargtext=['FUBAR']
		plugincls = _auth_plugins.get ( mechanism )
		if plugincls is None:
			raise ResponseEvent ( 504, f'Unrecognized authentication mechanism: {mechanism}' )
		return plugincls, moreargtext[0] if moreargtext else ''
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		return super().client_protocol ( client )
	
	def server_protocol ( self, server: Server, moreargtext: str ) -> RequestProtocolGenerator:
		return super().server_protocol ( server, moreargtext )
	
	def _on_authenticate ( self, server: Server, uid: str, pwd: str ) -> RequestProtocolGenerator:
		yield from ( event := AuthEvent ( uid, pwd ) ).go()
		server.auth_uid = uid
		yield ResponseEvent ( event._code, event._message )


@auth_plugin ( 'PLAIN' )
class AuthPlainRequest ( _Auth ):
	# no _client_protocol - clients should use AuthPlain1Request or AuthPlain2Request
	
	def server_protocol ( self, server: Server, moreargtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'AuthPlainRequest._server_protocol' )
		try:
			if not ( authtext := moreargtext ):
				yield ResponseEvent ( 334, '' )
				yield from ( event := NeedDataEvent() ).go()
				authtext = b2s ( event.data or b'' ).rstrip()
			_, uid, pwd = b64_decode_str ( authtext ).split ( '\0' )
		except Exception as e:
			log.debug ( f'malformed auth input {moreargtext=}: {e=}' )
			yield ResponseEvent ( 501, 'malformed auth input RFC4616#2' )
		else:
			yield from self._on_authenticate ( server, uid, pwd )


class AuthPlain1Request ( AuthPlainRequest ):
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'AuthPlain1Request.client_protocol' )
		authtext = b64_encode_str ( f'{self.uid}\0{self.uid}\0{self.pwd}' )
		yield from client_util.send_recv_done ( f'AUTH PLAIN {authtext}\r\n' )

class AuthPlain2Request ( AuthPlainRequest ):
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'AuthPlain2Request.client_protocol' )
		yield from client_util.send_recv_ok ( 'AUTH PLAIN\r\n' )
		authtext = b64_encode_str ( f'{self.uid}\0{self.uid}\0{self.pwd}' )
		yield from client_util.send_recv_done ( f'{authtext}\r\n' )


@auth_plugin ( 'LOGIN' )
class AuthLoginRequest ( _Auth ):
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'AuthLoginRequest.client_protocol' )
		yield from client_util.send_recv_ok ( 'AUTH LOGIN\r\n' )
		yield from client_util.send_recv_ok ( f'{b64_encode_str(self.uid)}\r\n' )
		yield from client_util.send_recv_done ( f'{b64_encode_str(self.pwd)}\r\n' )
	
	def server_protocol ( self, server: Server, moreargtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'AuthLoginRequest._server_protocol' )
		if moreargtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no extra parameters allowed)' )
		event = NeedDataEvent()
		try:
			yield ResponseEvent ( 334, b64_encode_str ( 'Username:' ) )
			yield event
			uid = b2s ( base64.b64decode ( event.data or b'' ) ).rstrip()
			yield ResponseEvent ( 334, b64_encode_str ( 'Password:' ) )
			yield event
			pwd = b2s ( base64.b64decode ( event.data or b'' ) ).rstrip()
		except Exception as e:
			log.debug ( f'{e=}' )
			yield ResponseEvent ( 501, 'malformed auth input RFC4616#2' )
		else:
			yield from self._on_authenticate ( server, uid, pwd )


class ExpnVrfyRequest ( Request[ResponseType] ):
	_verb: str
	_event_cls: Type[ExpnVrfyEvent]
	
	def __init__ ( self, mailbox: str ) -> None:
		self.mailbox = str ( mailbox ).strip()
		assert len ( self.mailbox ) > 0
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'ExpnRequest.client_protocol' )
		yield from client_util.send ( f'{self._verb} {self.mailbox}\r\n' )
		event = NeedDataEvent()
		lines: List[str] = []
		
		while True:
			yield from client_util.recv_ok ( event )
			assert isinstance ( event.response, Response )
			tmp: Opt[Response] = event.response
			assert tmp is not None
			lines.append ( tmp.lines[0] )
			if isinstance ( tmp, SuccessResponse ):
				raise self.responsecls ( tmp.code, *lines )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator: # raises: ResponseEvent
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if not server.auth_uid:
			raise ResponseEvent ( 513, 'Must authenticate' )
		if not argtext:
			raise ResponseEvent ( 501, 'missing required mailbox parameter' )
		event = self._event_cls ( argtext )
		yield event
		assert isinstance ( event._code, int )
		if event._acceptance:
			assert event.mailboxes is not None
			yield ResponseEvent ( event._code, *event.mailboxes )
		else:
			assert event._message is not None
			yield ResponseEvent ( event._code, event._message )


@request_verb ( 'EXPN' )
class ExpnRequest ( ExpnVrfyRequest[ExpnResponse] ):
	responsecls = ExpnResponse
	_verb = 'EXPN'
	_event_cls = ExpnEvent


@request_verb ( 'VRFY' )
class VrfyRequest ( ExpnVrfyRequest[VrfyResponse] ):
	responsecls = VrfyResponse
	_verb = 'VRFY'
	_event_cls = VrfyEvent


@request_verb ( 'MAIL' )
class MailFromRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def __init__ ( self, mail_from: str ) -> None:
		self.mail_from = str ( mail_from ).strip()
		assert len ( self.mail_from ) > 0
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'MailFromRequest.client_protocol' )
		yield from client_util.send_recv_done ( f'MAIL FROM:<{self.mail_from}>\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if not server.auth_uid:
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
class RcptToRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def __init__ ( self, rcpt_to: str ) -> None:
		self.rcpt_to = str ( rcpt_to ).strip()
		assert len ( self.rcpt_to ) > 0
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'RcptToRequest.client_protocol' )
		yield from client_util.send_recv_done ( f'RCPT TO:<{self.rcpt_to}>\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if not server.auth_uid:
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
class DataRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	# see RFC 5321 4.5.2 for byte stuffing algorithm description
	
	def __init__ ( self, payload: bytes ) -> None:
		assert isinstance ( payload, bytes_types ) and len ( payload ) > 0
		self.payload: bytes = payload # only used on client side because on server side it is accumulated in Server.data
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'DataRequest.client_protocol' )
		yield from client_util.send_recv_ok ( 'DATA\r\n' )
		payload = memoryview ( self.payload ) # avoid data copying when we start slicing it later
		last = 0
		stitch = b'\r\n..'
		parts: List[bytes] = []
		for m in _r_crlf_dot.finditer ( payload ):
			start = m.start()
			chunk = payload[last:start]
			parts.append ( chunk )
			parts.append ( stitch )
			last = start + 3
		if last < len ( payload ):
			parts.append ( payload[last:] )
		if not self.payload.endswith ( b'\r\n' ):
			parts.append ( b'\r\n' )
		yield from SendDataEvent ( *parts ).go()
		yield from client_util.send_recv_done ( '.\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'DataRequest._server_protocol' )
		if not server.client_hostname and server.pedantic:
			raise ResponseEvent ( 503, 'Say HELO first' )
		if argtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
		if not server.auth_uid:
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
			elif line[0:1] == b'.':
				server.data.append ( line[1:] )
			else:
				server.data.append ( line )
		event2 = CompleteEvent ( server.mail_from, server.rcpt_to, server.data )
		server.reset() # is this correct? reset even if we're going to return an error?
		yield event2
		_, code, message = event2._accepted()
		yield ResponseEvent ( code, message )


@request_verb ( 'RSET' )
class RsetRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from client_util.send_recv_done ( 'RSET\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
		server.reset()
		yield ResponseEvent ( 250, 'OK' )


@request_verb ( 'NOOP' )
class NoOpRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from client_util.send_recv_done ( 'NOOP\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		# FYI `argtext` is ignored per RFC 5321 4.1.1.9
		yield ResponseEvent ( 250, 'OK' )


@request_verb ( 'QUIT' )
class QuitRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'QuitRequest.client_protocol' )
		yield from client_util.send_recv_done ( 'QUIT\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic:
			raise ResponseEvent ( 501, 'Syntax error (no parameters allowed) RFC5321#4.3.2' )
		yield ResponseEvent ( 221, 'Closing connection' )
		raise Closed ( 'QUIT' )

#endregion
#region SERVER ----------------------------------------------------------------

def _auth_lines ( auth_mechanisms: Iterable[str] ) -> Seq[str]:
	lines: List[str] = []
	if auth_mechanisms:
		line = ' '.join ( auth_mechanisms )
		while len ( line ) >= 71: # 80 - len ( '250-' ) - len ( 'AUTH ' )
			n = line.rindex ( ' ', 0, 71 ) # raises: ValueError # no auth name can be 71 characters! ( not true, one of the RFCs greatly extended command length limits )
			lines.append ( f'AUTH {line[:n]}' )
			line = line[n:].lstrip()
		lines.append ( f'AUTH {line}' )
	return lines

_r_smtp_request = re.compile ( r'^\s*([a-z]+)(?:\s+(.*))?\s*$', re.I )


class Server ( ServerProtocol ):
	_MAXLINE = 8192
	client_hostname: str = ''
	mail_from: str
	rcpt_to: List[str]
	data: List[bytes]
	pedantic: bool = True # set this to False to relax behaviors that cause no harm for the protocol ( like double-HELO )
	esmtp_features: Dict[str,str] = {
		'8BITMIME': '', # should work out of the box?
		'PIPELINING': '', # should work out of the box
	}
	
	def __init__ ( self,
		tls: bool,
		hostname: str,
	) -> None:
		super().__init__ ( tls, hostname )
		self.reset()
	
	def startup ( self ) -> Iterator[Event]:
		self.request = GreetingRequest()
		self.request_protocol = self.request.server_protocol ( self, '' )
		yield from self._run_protocol()
	
	def reset ( self ) -> None:
		self.mail_from = ''
		self.rcpt_to = []
		self.data = []
	
	def _parse_request_line ( self, line: BYTES ) -> Tuple[str,Opt[Type[BaseRequest]],str]:
		log = logger.getChild ( 'Server._parse_request_line' )
		m = _r_smtp_request.match ( b2s ( line ).rstrip() )
		if not m:
			#log.critical ( f'{m=} {bytes(line)=}' )
			return '', None, ''
		verb, suffix = m.groups()
		verb = verb.upper() # RFC5321#2.4 command verbs are not case-sensitive
		
		requestcls = _request_verbs.get ( verb )
		if requestcls is None:
			log.debug ( f'{requestcls=} {verb=} {_request_verbs=}' )
		else:
			assert issubclass ( requestcls, Request )
			requestcls, suffix = requestcls.subparse ( self, suffix )
		
		return '', requestcls, suffix or ''
	
	def _error_invalid_command ( self ) -> Event:
		#log = logger.getChild ( 'Server._error_invalid_command' )
		return ResponseEvent ( 500, 'Command not recognized' )
	
	def _error_tls_required ( self ) -> Event:
		return ResponseEvent ( 535, 'SSL/TLS connection required' )
	
	def _error_tls_excluded ( self ) -> Event:
		return ResponseEvent ( 535, 'Command not available in SSL/TLS' )

#endregion
#region CLIENT ----------------------------------------------------------------

class Client ( ClientProtocol ):
	_MAXLINE = Server._MAXLINE

#endregion
