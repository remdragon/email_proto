#region PROLOGUE --------------------------------------------------------------
from __future__ import annotations

# python imports:
from abc import ABCMeta, abstractmethod
import base64
import email.utils
import hashlib
import logging
import re
import traceback
from types import TracebackType
from typing import (
	Callable, Dict, Generator, Generic, Iterable, Iterator, List, NamedTuple,
	Optional as Opt, Sequence as Seq, Set, Tuple, Type, TypeVar, Union,
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
_r_crlf_dot = re.compile ( b'\\r\\n\\.', re.M )


#endregion
#region RESPONSES -------------------------------------------------------------

class Response ( BaseResponse ):
	def __init__ ( self, ok: bool, message: str ) -> None:
		self.ok = ok
		self.message = message
		super().__init__()
	
	@staticmethod
	def parse ( line: BYTES ) -> Union[SuccessResponse,ErrorResponse]:
		#log = logger.getChild ( 'Response.parse' )
		assert isinstance ( line, bytes_types ) and len ( line ) > 0, f'invalid {line=}'
		try:
			ok, *extra = b2s ( line ).split ( ' ', 1 )
			assert ok in ( '+OK', '-ERR' ), f'invalid {ok=}'
		except Exception as e:
			raise Closed ( f'malformed response from server {line=}: {e=}' ) from e
		text = extra[0].rstrip() if extra else ''
		if ok == '+OK':
			return SuccessResponse ( text )
		else:
			return ErrorResponse ( text )
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}({self.ok!r}, {self.message!r})'


class SuccessResponse ( Response ):
	def __init__ ( self, message: str ) -> None:
		return super().__init__ ( True, message )
	def is_success ( self ) -> bool:
		return True


class ErrorResponse ( Response ):
	def __init__ ( self, message: str ) -> None:
		return super().__init__ ( False, message )
	def is_success ( self ) -> bool:
		return False


class GreetingResponse ( SuccessResponse ):
	apop_challenge: Opt[str]
	
	def __init__ ( self, message: str ) -> None:
		m = re.search ( r'(<.*>)', message )
		self.apop_challenge = m.group ( 1 ) if m else None
		super().__init__ ( message )
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}({self.ok!r}, {self.message!r})'


MultiResponseType = TypeVar ( 'MultiResponseType', bound = 'MultiResponse' )
class MultiResponse ( SuccessResponse ):
	def __init__ ( self, message: str, *lines: str ) -> None:
		self.lines = lines
		super().__init__ ( message )
	
	@classmethod
	def parse_multi (
		cls: Type[MultiResponseType],
		*lines: BYTES,
	) -> MultiResponseType:
		assert (
			len ( lines ) >= 3
			and isinstance ( lines[0], bytes_types )
			and lines[0][0:1] in b'+-'
			and lines[-1][:] == b'.\r\n'
		), f'invalid {[bytes(line) for line in lines]=}'
		self: MultiResponseType = cls.__new__ ( cls )
		ok, *message = b2s ( lines[0] ).rstrip().split ( ' ', 1 )
		self.ok = ( ok == '+OK' )
		self.message = message[0] if message else ''
		self.lines = tuple ( map ( str.strip, map ( b2s, lines[1:-1] ) ) )
		return self
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}({self.ok!r}, {self.message!r}, {", ".join(map(repr,self.lines))})'


class CapaResponse ( MultiResponse ):
	capa: Dict[str,str]
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		capa_ = ', '.join ( [
			f'{k!r}: {v!r}' for k, v in sorted ( self.capa.items() )
		] )
		return f'{cls.__module__}.{cls.__name__}({self.ok!r}, {self.message!r}, capa={{{capa_}}})'


class StatResponse ( SuccessResponse ):
	count: int
	octets: int

class ListMessage ( NamedTuple ):
	id: int
	octets: int


class ListResponse ( SuccessResponse ):
	count: int # TODO FIXME: not sure this is part of the spec
	octets: int # TODO FIXME: not sure this is part of the spec
	messages: List[ListMessage]


client_util = ClientUtil ( Response.parse )

#endregion
#region EVENTS ----------------------------------------------------------------

def ResponseEvent ( ok: bool, text: str ) -> SendDataEvent:
	ok_ = '+OK' if ok else '-ERR'
	data = s2b (
		f'{ok_} {text}\r\n'
	)
	return SendDataEvent ( data )


def SuccessEvent ( text: str ) -> SendDataEvent:
	return ResponseEvent ( True, text )


def ErrorEvent ( text: str ) -> SendDataEvent:
	return ResponseEvent ( False, text )


def MultiResponseEvent ( text: str, *multilines: str ) -> SendDataEvent:
	multilines_ = '\r\n'.join ( multilines )
	return ResponseEvent ( True, f'{text}\r\n{multilines_}\r\n.' )


class AcceptRejectEvent ( Event ):
	success_message: str
	error_message: str
	_acceptance: Opt[bool] = None
	
	def __init__ ( self ) -> None:
		self._message: str = self.error_message
	
	def _accept ( self ) -> None:
		#log = logger.getChild ( 'AcceptRejectEvent.accept' )
		self._acceptance = True
		self._message = self.success_message
	
	def reject ( self, message: Opt[str] = None ) -> None:
		log = logger.getChild ( 'AcceptRejectEvent.reject' )
		self._acceptance = False
		self._message = self.error_message
		if message is not None:
			if not isinstance ( message, str ) or _r_eol.search ( message ):
				log.error ( f'invalid error-{message=}' )
			else:
				self._message = message
	
	def _accepted ( self ) -> Tuple[bool,str]:
		#log = logger.getChild ( 'AcceptRejectEvent._accepted' )
		assert self._acceptance is not None, f'you must call .accept() or .reject() on when passed a {type(self).__module__}.{type(self).__name__} object'
		assert isinstance ( self._message, str )
		return self._acceptance, self._message
	
	def go ( self ) -> Iterator[Event]:
		yield self
		if not self._acceptance:
			raise ResponseEvent ( False, self._message )
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		args = ', '.join ( f'{k}={getattr(self,k)!r}' for k in (
			'_acceptance',
			'_message',
		) )
		return f'{cls.__module__}.{cls.__name__}({args})'


class GreetingAcceptEvent ( AcceptRejectEvent ):
	error_message = 'Too busy to accept mail right now'
	
	def __init__ ( self, apop_challenge: Opt[str] ) -> None:
		super().__init__()
		self.success_message = 'POP3 server ready'
		if apop_challenge:
			assert apop_challenge[0] == '<' and apop_challenge[-1] == '>', f'invalid {apop_challenge=}'
			self.success_message += f' {apop_challenge}'
	
	def accept ( self ) -> None:
		self._accept()


class StartTlsAcceptEvent ( AcceptRejectEvent ):
	success_message = 'Begin TLS negotiation' # RFC2595#4 example
	error_message = 'TLS not available at the moment'
	
	def accept ( self ) -> None:
		self._accept()


class StartTlsBeginEvent ( Event ):
	pass


class UserPassEvent ( AcceptRejectEvent ):
	success_message = 'maildrop locked and ready' # TODO FIXME: "mrose's maildrop has 2 messages (320 octets)"
	error_message = 'Authentication failed'
	
	def __init__ ( self, uid: str, pwd: str ) -> None:
		super().__init__()
		self.uid = uid
		self.pwd = pwd
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(uid={self.uid!r})'


def apop_hash ( challenge: str, pwd: str ) -> str:
	# TODO FIXME: is this in the email library already maybe?
	return hashlib.md5 ( s2b ( f'{challenge}{pwd}' ) ).hexdigest()


class ApopChallengeEvent ( AcceptRejectEvent ):
	success_message = '' # not used
	error_message = '' # not used
	challenge: Opt[str] = None
	
	def accept ( self, challenge: str ) -> None:
		assert challenge[0] == '<' and challenge[-1] == '>'
		self.challenge = challenge
		super()._accept()


class ApopAuthEvent ( AcceptRejectEvent ):
	success_message = 'maildrop locked and ready' # TODO FIXME: "mrose's maildrop has 2 messages (320 octets)"
	error_message = 'authentication failed'
	
	def __init__ ( self, uid: str, challenge: str, digest: str ) -> None:
		self.uid = uid
		self.challenge = challenge
		self.digest = digest
	
	def accept ( self ) -> None:
		self._accept()
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(uid={self.uid!r}, challenge={self.challenge!r})'


class LockMaildropEvent ( AcceptRejectEvent ):
	success_message = 'maildrop locked and ready' # TODO FIXME: "mrose's maildrop has 2 messages (320 octets)"
	error_message = 'maildrop not available to be locked'
	"""
	This event indicates that a maildrop should be locked.
	implementations should cache or flag the messages that are locked.
	No other logins will have access to the locked messages simultaneously.
	"""
	
	count: int
	octets: int
	
	def __init__ ( self, maildrop: str ) -> None:
		self.maildrop = maildrop
		super().__init__()
	
	def accept ( self, count: int, octets: int ) -> None:
		self.count = count
		self.octets = octets
		self._accept()


class UnlockMaildropEvent ( AcceptRejectEvent ):
	'''
	Should this be an accept/reject???
	'''


class StatEvent ( AcceptRejectEvent ):
	error_message = 'error accessing maildrop' # TODO FIXME: look up expected error conditions/messages
	
	count: int
	octets: int
	
	def __init__ ( self, rcpt_to: str ) -> None:
		#assert isinstance ( rcpt_to, str ) and len ( rcpt_to.strip() ) > 0, f'invalid {rcpt_to=}'
		super().__init__()
		self.rcpt_to = rcpt_to
	
	def accept ( self, count: int, octets: int ) -> None:
		#log = logger.getChild ( 'StatEvent.accept' )
		self.count = count
		self.octets = octets
		self.success_message = f'{count} {octets}'
		self._accept()


#endregion
#region REQUESTS --------------------------------------------------------------

class Request ( RequestT[ResponseType] ):
	def _client_protocol ( self, client: ClientProtocol ) -> RequestProtocolGenerator:
		assert isinstance ( client, Client )
		yield from self.client_protocol ( client )
	
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
_pop3ext_capa: Dict[str,str] = {} # TODO FIXME: implement via an event

def request_verb (
	verb: str,
	*,
	capa: Opt[Tuple[str,str]] = None,
) -> Callable[[Type[BaseRequest]],Type[BaseRequest]]:
	def registrar ( cls: Type[BaseRequest] ) -> Type[BaseRequest]:
		global _request_verbs
		assert verb == verb.upper() and ' ' not in verb and len ( verb ) <= 71, f'invalid auth mechanism {verb=}'
		assert verb not in _request_verbs, f'duplicate request verb {verb!r}'
		_request_verbs[verb] = cls
		if capa is not None:
			capa_name, capa_params = capa
			assert capa_name not in _pop3ext_capa, f'duplicate pop3ext {capa_name=}'
			_pop3ext_capa[capa_name] = capa_params
		return cls
	return registrar

#_auth_plugins: Dict[str,Type[_Auth]] = {}
#
#def auth_plugin ( name: str ) -> Callable[[Type[_Auth]],Type[_Auth]]:
#	def registrar ( cls: Type[_Auth] ) -> Type[_Auth]:
#		global _auth_plugins
#		assert name == name.upper() and ' ' not in name and len ( name ) <= 71, f'invalid auth mechanism {name=}'
#		assert name not in _auth_plugins, f'duplicate auth mechanism {name!r}'
#		_auth_plugins[name] = cls
#		return cls
#	return registrar


class GreetingRequest ( Request[GreetingResponse] ):
	responsecls = GreetingResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'GreetingRequest.client_protocol' )
		event = NeedDataEvent()
		yield from client_util.recv_ok ( event )
		assert isinstance ( event.response, Response )
		raise GreetingResponse ( event.response.message )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		challenge = server.apop_challenge
		if challenge is None:
			event1 = ApopChallengeEvent()
			yield event1 # don't abort if rejected, we just won't have an apop challenge in the greeting
			challenge = event1.challenge
			if challenge:
				server.apop_challenge = challenge
		
		event2 = GreetingAcceptEvent ( challenge )
		yield from event2.go()
		ok, message = event2._accepted()
		yield ResponseEvent ( ok, message )


@request_verb ( 'CAPA' )
class CapaRequest ( Request[CapaResponse] ): # RFC2449
	responsecls = CapaResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		event = NeedDataEvent()
		yield from client_util.send_recv_ok ( 'CAPA\r\n', event ) # +OK Capability list follows
		lines: List[bytes] = [ event.data or b'' ]
		while event.data != b'.\r\n':
			yield from event.go()
			lines.append ( event.data or b'' )
		r = CapaResponse.parse_multi ( *lines )
		r.capa = {}
		for line in r.lines:
			capa_name, *capa_params = line.split ( ' ', 1 )
			r.capa[capa_name] = capa_params[0].rstrip() if capa_params else ''
		raise r
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'StartTlsRequest._server_protocol' )
		if argtext:
			raise ErrorEvent ( 'No parameters allowed' ) # TODO FIXME: need RFC citation
		lines = []
		for capa_name, capa_params in _pop3ext_capa.items():
			lines.append ( f'{capa_name} {capa_params}'.rstrip() )
		yield MultiResponseEvent ( 'Capability list follows', *lines )


@request_verb ( 'STLS', capa = ( 'STLS', '' ) )
class StartTlsRequest ( Request[SuccessResponse] ): # RFC2595 Using TLS with IMAP, POP3 and ACAP
	responsecls = SuccessResponse
	tls_excluded = True
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'StartTlsRequest._client_protocol' )
		assert not client.tls
		yield from client_util.send_recv_ok ( 'STLS\r\n' )
		yield from ( event := StartTlsBeginEvent() ).go()
		client.tls = True
		yield from client_util.recv_done()
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'StartTlsRequest._server_protocol' )
		if argtext:
			raise ErrorEvent ( 'No parameters allowed' ) # TODO FIXME: need RFC citation
		if server.tls:
			raise ErrorEvent ( 'Command not permitted when TLS active' ) # RFC2595#4 Examples
		yield from ( event1 := StartTlsAcceptEvent() ).go()
		yield SuccessEvent ( event1._message )
		yield from StartTlsBeginEvent().go()
		server.tls = True
		
		# TODO FIXME: it doesn't appear that the server greets the client again after TLS initiated



#class _Auth ( Request ):
#	
#	def _on_authenticate ( self, server: Server, uid: str, pwd: str ) -> RequestProtocolGenerator:
#		yield from ( event := AuthEvent ( uid, pwd ) ).go()
#		server.auth_mailbox = uid
#		yield SuccessEvent ( event._message )


@request_verb ( 'USER' )
class UserRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	tls_required: bool = True
	
	def __init__ ( self, uid: str, pwd: str ) -> None:
		self.uid = str ( uid )
		self.pwd = str ( pwd )
		assert len ( self.uid ) > 0
		assert len ( self.pwd ) > 0
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		assert False # not used
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( '_Auth._server_protocol' )
		assert False, 'TODO FIXME'
		#if not server.client_hostname and server.pedantic:
		#	raise ErrorEvent ( 'Say HELO first' )
		#if server.auth_mailbox:
		#	raise ErrorEvent ( 'already authenticated (RFC4954#4 Restrictions)' )
		#mechanism, *moreargtext = suffix.split ( ' ', 1 ) # ex: mechanism='PLAIN' moreargtext=['FUBAR']
		##log.debug ( f'{mechanism=} {moreargtext=}' )
		#plugincls = _auth_plugins.get ( mechanism )
		#if plugincls is None:
		#	raise ErrorEvent ( f'Unrecognized authentication mechanism: {mechanism}' )
		#if plugincls.tls_required and not server.tls:
		#	raise ErrorEvent ( 'SSL/TLS connection required' )
		#plugin: _Auth = plugincls.__new__ ( plugincls ) # bypass __init__()
		#yield from plugin._server_protocol ( server, moreargtext[0] if moreargtext else '' )


_r_apop_request = re.compile ( r'\s*([^\s]+)\s*([^\s]+)\s*' )
@request_verb ( 'APOP' )
class ApopRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def __init__ ( self, uid: str, pwd: str, challenge: str ) -> None:
		assert ' ' not in uid, f'invalid {uid=}'
		assert challenge[0:1] == '<' and challenge[-1:], f'invalid {challenge=}'
		self.uid = uid
		self.challenge = challenge
		self.digest = apop_hash ( challenge, pwd )
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from client_util.send_recv_done ( f'APOP {self.uid} {self.digest}\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if not ( m := _r_apop_request.match ( argtext ) ):
			raise ErrorEvent ( 'malformed request' )
		uid, digest = m.groups()
		
		challenge = server.apop_challenge
		if not challenge:
			raise ErrorEvent ( 'APOP not available' )
		
		event1 = ApopAuthEvent (
			uid = uid, challenge = challenge, digest = digest,
		)
		yield from event1.go()
		
		server.auth_uid = uid
		
		event2 = LockMaildropEvent ( server.auth_uid )
		yield from event2.go()
		
		yield SuccessEvent ( ' '.join ( [
			f'maildrop has {event2.count!r}',
			f'message{"s" if event2.count != 1 else ""}',
			f'({event2.octets!r} octets)'
		] ) )


@request_verb ( 'RSET' )
class RsetRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from client_util.send_recv_done ( 'RSET\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic: # TODO FIXME: is this correct?
			raise ErrorEvent ( 'No parameters allowed' )
		server.reset()
		yield SuccessEvent ( 'TODO FIXME' )


@request_verb ( 'NOOP' )
class NoOpRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from client_util.send_recv_done ( 'NOOP\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic: # TODO FIXME: is this correct?
			raise ErrorEvent ( 'No parameters allowed' )
		yield SuccessEvent ( 'TODO FIXME' )


@request_verb ( 'QUIT' )
class QuitRequest ( Request[SuccessResponse] ):
	responsecls = SuccessResponse
	
	def client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'QuitRequest._client_protocol' )
		yield from client_util.send_recv_done ( 'QUIT\r\n' )
	
	def server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic: # TODO FIXME: is this correct?
			raise ErrorEvent ( 'No parameters allowed' )
		yield SuccessEvent ( 'Closing connection' ) # TODO FIXME: is this correct?
		raise Closed ( 'QUIT' )

#endregion
#region SERVER ----------------------------------------------------------------

_r_pop3_request = re.compile ( r'\s*([a-z]+)(?:\s+(.*))?\s*', re.I )

class Server ( ServerProtocol ):
	_MAXLINE = 8192
	client_hostname: str = ''
	apop_challenge: Opt[str] = None
	
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
	
	def _parse_request_line ( self, line: BYTES ) -> Tuple[str,Opt[Type[BaseRequest]],str]:
		log = logger.getChild ( 'Server._parse_request_line' )
		m = _r_pop3_request.match ( b2s ( line ).rstrip() )
		if not m:
			return '', None, ''
		verb, suffix = m.groups()
		verb = verb.upper() # TODO FIXME: are POP3 verbs case-sensitive?
		requestcls = _request_verbs.get ( verb )
		if requestcls is None:
			log.debug ( f'{requestcls=} {verb=} {_request_verbs=}' )
		return '', requestcls, suffix or ''
	
	def _error_invalid_command ( self ) -> Event:
		#log = logger.getChild ( 'Server._error_invalid_command' )
		return ErrorEvent ( 'Command not recognized' )
	
	def _error_tls_required ( self ) -> Event:
		return ErrorEvent ( 'Command requires TLS to be active first' )
	
	def _error_tls_excluded ( self ) -> Event:
		return ErrorEvent ( 'Command not available when TLS is active' )


#endregion
#region CLIENT ----------------------------------------------------------------

class Client ( ClientProtocol ):
	_MAXLINE = Server._MAXLINE

#endregion
