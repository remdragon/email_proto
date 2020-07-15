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
	Callable, Dict, Generator, Iterable, Iterator, List, NamedTuple,
	Optional as Opt, Sequence as Seq, Set, Tuple, Type, TypeVar, Union,
)

logger = logging.getLogger ( __name__ )

# email_proto imports:
from util import bytes_types, BYTES, b2s, s2b, b64_encode_str, b64_decode_str

_MAXLINE = 8192

_r_eol = re.compile ( r'[\r\n]' )
_r_crlf_dot = re.compile ( b'\\r\\n\\.', re.M )

class Closed ( Exception ): # TODO FIXME: BaseException?
	def __init__ ( self, reason: str = '' ) -> None:
		super().__init__ ( reason or '(none given)' )

class ProtocolError ( Exception ):
	pass

#endregion
#region RESPONSES -------------------------------------------------------------

ResponseType = TypeVar ( 'ResponseType', bound = 'Response' )
class Response ( Exception ):
	def __init__ ( self, ok: bool, message: str ) -> None:
		self.ok = ok
		self.message = message
		super().__init__ ( ok, message )
	
	@staticmethod
	def parse ( *lines: BYTES ) -> Union[SuccessResponse,ErrorResponse,MultiResponse]:
		assert len ( lines ) == 1, f'invalid {lines=}' # call MultiResponse.parse() if you need > 1
		line = lines[0]
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


class ErrorResponse ( Response ):
	def __init__ ( self, message: str ) -> None:
		return super().__init__ ( False, message )


class GreetingResponse ( SuccessResponse ):
	apop_challenge: Opt[str]
	
	def __init__ ( self, message: str ) -> None:
		m = re.search ( r'(<.*>)', message )
		self.apop_challenge = m.group ( 1 ) if m else None
		super().__init__ ( message )
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}({self.ok!r}, {self.message!r})'


class MultiResponse ( SuccessResponse ):
	def __init__ ( self, message: str, *lines: str ) -> None:
		self.lines = lines
		super().__init__ ( True, message )
	
	@classmethod
	def parse ( cls, *lines: BYTES ) -> Union[SuccessResponse,ErrorResponse,MultiResponse]:
		assert (
			len ( lines ) > 0
			and isinstance ( lines[0], bytes_types )
			and lines[0][0:1] in b'+-'
			and bytes ( lines[-1] ) == b'.\r\n'
		), f'invalid {[bytes(line) for line in lines]=}'
		self: MultiResponse = cls.__new__ ( cls )
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

#endregion
#region EVENTS ----------------------------------------------------------------

class Event ( Exception ):
	exc_info: Opt[Union[Tuple[Type[BaseException],BaseException,TracebackType],Tuple[None,None,None]]] = None
	
	def go ( self ) -> Iterator[Event]:
		yield self
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}()'


class NeedDataEvent ( Event ):
	data: Opt[bytes] = None
	response: Opt[Response] = None
	
	def reset ( self ) -> NeedDataEvent:
		self.data = None
		self.response = None
		return self
	
	def go ( self ) -> Iterator[Event]:
		self.reset()
		yield from super().go()


class SendDataEvent ( Event ):
	
	def __init__ ( self, *chunks: bytes ) -> None:
		self.chunks: Seq[bytes] = chunks
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}(chunks={self.chunks!r})'


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
	
	def __init__ ( self ) -> None:
		self._acceptance: Opt[bool] = None
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

class ApopEvent ( AcceptRejectEvent ):
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

def _client_proto_send ( line: str ) -> Iterator[Event]:
	assert line.endswith ( '\r\n' ), f'invalid {line=}'
	yield from ( event := SendDataEvent ( s2b ( line ) ) ).go()

def _client_proto_recv_ok ( event: NeedDataEvent ) -> Iterator[Event]:
	yield from event.reset().go()
	event.response = Response.parse ( event.data or b'' )
	if isinstance ( event.response, ErrorResponse ):
		raise event.response

def _client_proto_recv_done() -> Iterator[Event]:
	log = logger.getChild ( '_client_proto_recv_done' )
	yield from ( event := NeedDataEvent() ).go()
	response = Response.parse ( event.data or b'' )
	raise response

def _client_proto_send_recv_ok ( line: str, event: Opt[NeedDataEvent] = None ) -> Iterator[Event]:
	log = logger.getChild ( '_client_proto_send_recv_ok' )
	yield from _client_proto_send ( line )
	if event is None:
		event = NeedDataEvent()
	yield from event.go()
	response = Response.parse ( event.data or b'' )
	if not isinstance ( response, SuccessResponse ):
		raise response

def _client_proto_send_recv_done ( line: str ) -> Iterator[Event]:
	yield from _client_proto_send ( line )
	yield from _client_proto_recv_done()


_request_verbs: Dict[str,Type[Request]] = {}
_pop3ext_capa: Dict[str,str] = {} # TODO FIXME: implement via an event

def request_verb (
	verb: str,
	*,
	capa: Opt[Tuple[str,str]] = None,
) -> Callable[[Type[Request]],Type[Request]]:
	def registrar ( cls: Type[Request] ) -> Type[Request]:
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

_auth_plugins: Dict[str,Type[_Auth]] = {}

def auth_plugin ( name: str ) -> Callable[[Type[_Auth]],Type[_Auth]]:
	def registrar ( cls: Type[_Auth] ) -> Type[_Auth]:
		global _auth_plugins
		assert name == name.upper() and ' ' not in name and len ( name ) <= 71, f'invalid auth mechanism {name=}'
		assert name not in _auth_plugins, f'duplicate auth mechanism {name!r}'
		_auth_plugins[name] = cls
		return cls
	return registrar


RequestProtocolGenerator = Generator[Event,None,None]

class Request ( metaclass = ABCMeta ):
	# this class is the basis of all client/server command handling
	# 1) client uses __init__() to construct request
	# 2) server bypasses __init__() for technical reasons
	# 3) _client_protocol() implements client-side state machine
	# 4) _server_protocol() implements server-side state machine
	tls_required: bool = False
	tls_excluded: bool = False # only used by STLS?
	response: Opt[Response] = None
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}()'
	
	@abstractmethod
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._client_protocol()' )
	
	@abstractmethod
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._server_protocol()' )


class GreetingRequest ( Request ):
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'GreetingRequest._client_protocol' )
		event = NeedDataEvent()
		yield from _client_proto_recv_ok ( event )
		raise GreetingResponse ( event.response.message )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		event = GreetingAcceptEvent ( server.apop_challenge )
		yield from event.go()
		ok, message = event._accepted()
		yield ResponseEvent ( ok, message )


@request_verb ( 'CAPA' )
class CapaRequest ( Request ): # RFC2449
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		event = NeedDataEvent()
		yield from _client_proto_send_recv_ok ( 'CAPA\r\n', event ) # +OK Capability list follows
		lines: List[bytes] = [ event.data or b'' ]
		while event.data != b'.\r\n':
			yield from event.go()
			lines.append ( event.data or b'' )
		r = CapaResponse.parse ( *lines )
		r.capa = {}
		for line in r.lines:
			capa_name, *capa_params = line.split ( ' ', 1 )
			r.capa[capa_name] = capa_params[0].rstrip() if capa_params else ''
		raise r
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( 'StartTlsRequest._server_protocol' )
		if argtext:
			raise ErrorEvent ( 'No parameters allowed' ) # TODO FIXME: need RFC citation
		lines = []
		for capa_name, capa_params in _pop3ext_capa.items():
			lines.append ( f'{capa_name} {capa_params}'.rstrip() )
		yield MultiResponseEvent ( 'Capability list follows', *lines )


@request_verb ( 'STLS', capa = ( 'STLS', '' ) )
class StartTlsRequest ( Request ): # RFC2595 Using TLS with IMAP, POP3 and ACAP
	tls_excluded = True
	
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'StartTlsRequest._client_protocol' )
		yield from _client_proto_send_recv_ok ( 'STLS\r\n' )
		yield from ( event := StartTlsBeginEvent() ).go()
		client.tls = True
		yield from _client_proto_recv_done()
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
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



class _Auth ( Request ):
	
	def _on_authenticate ( self, server: Server, uid: str, pwd: str ) -> RequestProtocolGenerator:
		yield from ( event := AuthEvent ( uid, pwd ) ).go()
		server.auth_mailbox = uid
		yield SuccessEvent ( event._message )


@request_verb ( 'USER' )
class UserRequest ( Request ):
	tls_required: bool = True
	
	def __init__ ( self, uid: str, pwd: str ) -> None:
		self.uid = str ( uid )
		self.pwd = str ( pwd )
		assert len ( self.uid ) > 0
		assert len ( self.pwd ) > 0
	
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		assert False # not used
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		log = logger.getChild ( '_Auth._server_protocol' )
		if not server.client_hostname and server.pedantic:
			raise ErrorEvent ( 'Say HELO first' )
		if server.auth_mailbox:
			raise ErrorEvent ( 'already authenticated (RFC4954#4 Restrictions)' )
		mechanism, *moreargtext = argtext.split ( ' ', 1 ) # ex: mechanism='PLAIN' moreargtext=['FUBAR']
		#log.debug ( f'{mechanism=} {moreargtext=}' )
		plugincls = _auth_plugins.get ( mechanism )
		if plugincls is None:
			raise ErrorEvent ( f'Unrecognized authentication mechanism: {mechanism}' )
		if plugincls.tls_required and not server.tls:
			raise ErrorEvent ( 'SSL/TLS connection required' )
		plugin: _Auth = plugincls.__new__ ( plugincls ) # bypass __init__()
		yield from plugin._server_protocol ( server, moreargtext[0] if moreargtext else '' )


_r_apop_request = re.compile ( r'\s*([^\s]+)\s*([^\s]+)\s*' )
@request_verb ( 'APOP' )
class ApopRequest ( _Auth ):
	def __init__ ( self, uid: str, pwd: str, challenge: str ) -> None:
		assert ' ' not in uid, f'invalid {uid=}'
		assert challenge[0:1] == '<' and challenge[-1:], f'invalid {challenge=}'
		self.uid = uid
		self.challenge = challenge
		self.digest = apop_hash ( challenge, pwd )
	
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from _client_proto_send_recv_done ( f'APOP {self.uid} {self.digest}\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if not ( m := _r_apop_request.match ( argtext ) ):
			raise ErrorEvent ( 'malformed request' )
		uid, digest = m.groups()
		event1 = ApopEvent ( uid = uid, challenge = server.apop_challenge, digest = digest )
		yield from event1.go()
		
		server.auth_mailbox = uid
		
		event2 = LockMaildropEvent ( server.auth_mailbox )
		yield from event2.go()
		
		yield SuccessEvent ( ' '.join ( [
			f'maildrop has {event2.count!r}',
			f'message{"s" if event2.count != 1 else ""}',
			f'({event2.octets!r} octets)'
		] ) )


@request_verb ( 'RSET' )
class RsetRequest ( Request ):
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from _client_proto_send_recv_done ( 'RSET\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic: # TODO FIXME: is this correct?
			raise ErrorEvent ( 'No parameters allowed' )
		server.reset()
		yield SuccessEvent ( 'TODO FIXME' )


@request_verb ( 'NOOP' )
class NoOpRequest ( Request ):
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		yield from _client_proto_send_recv_done ( 'NOOP\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic: # TODO FIXME: is this correct?
			raise ErrorEvent ( 'No parameters allowed' )
		yield SuccessEvent ( 'TODO FIXME' )


@request_verb ( 'QUIT' )
class QuitRequest ( Request ):
	def _client_protocol ( self, client: Client ) -> RequestProtocolGenerator:
		#log = logger.getChild ( 'QuitRequest._client_protocol' )
		yield from _client_proto_send_recv_done ( 'QUIT\r\n' )
	
	def _server_protocol ( self, server: Server, argtext: str ) -> RequestProtocolGenerator:
		if argtext and server.pedantic: # TODO FIXME: is this correct?
			raise ErrorEvent ( 'No parameters allowed' )
		yield SuccessEvent ( 'Closing connection' ) # TODO FIXME: is this correct?
		raise Closed ( 'QUIT' )

#endregion
#region COMMON ----------------------------------------------------------------

class Connection ( metaclass = ABCMeta ):
	_buf: bytes = b''
	request: Opt[Request] = None
	request_protocol: Opt[Generator[Event,None,None]] = None
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
			raise Closed ( 'EOF' )
		self._buf += data
		start = 0
		end = 0
		try:
			while ( end := ( self._buf.find ( b'\n', start ) + 1 ) ):
				line = memoryview ( self._buf )[start:end]
				start = end
				yield from self._receive_line ( line )
		finally:
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
		assert self.request is not None, f'invalid {self.request=}'
		assert self.request_protocol is not None, f'invalid {self.request_protocol=}'
		try:
			while True:
				#log.debug ( 'yielding to request protocol' )
				event = next ( self.request_protocol )
				#log.debug ( f'{event=}' )
				if isinstance ( event, NeedDataEvent ):
					if self.request.response is not None:
						log.warning ( f'INTERNAL ERROR - {self.request!r} pushed NeedDataEvent but has a response set - this can cause upstack deadlock ({self.request.response!r})' )
						self.request.response = None
					self.need_data = event.reset()
					return
				else:
					yield event
					if event.exc_info:
						self.request_protocol.throw ( *event.exc_info )
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
			if not self.request.response and isinstance ( self, Client ):
				log.warning (
					f'INTERNAL ERROR:'
					f' {type(self.request).__module__}.{type(self.request).__name__}'
					f'._client_protocol() exit w/o response - this can cause upstack deadlock'
				)
				self.request.response = ErrorResponse ( 'INTERNAL PROTOCOL IMPLEMENTATION ERROR' )
			#log.debug ( f'protocol finished with {self.request.response=}' )
			self.request = None
			self.request_protocol = None
		except Exception as e:
			self.request = None
			self.request_protocol = None
			log.exception ( 'internal protocol error:' )
			raise Closed ( repr ( e ) ) from e

#endregion
#region SERVER ----------------------------------------------------------------

class Server ( Connection ):
	client_hostname: str = ''
	auth_mailbox: Opt[str] = None
	mail_from: str
	rcpt_to: List[str]
	data: List[bytes]
	pedantic: bool = True # set this to False to relax behaviors that cause no harm for the protocol
	
	def __init__ ( self,
		hostname: str,
		tls: bool,
		apop_challenge: Opt[str] = None, # NOTE: None will auto-generate, empty string ('') will suppress
	) -> None:
		assert isinstance ( hostname, str ) and not _r_eol.search ( hostname ), f'invalid {hostname=}'
		self.hostname = hostname
		if apop_challenge is None:
			apop_challenge = email.utils.make_msgid ( hostname ) # this is slooooowwwww, probably should generate my own
		self.apop_challenge = apop_challenge
		super().__init__ ( tls )
		self.reset()
	
	def startup ( self ) -> Iterator[Event]:
		self.request = GreetingRequest()
		self.request_protocol = self.request._server_protocol ( self, '' )
		yield from self._run_protocol()
	
	def _receive_line ( self, line: BYTES ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server._receive_line' )
		if self.need_data:
			self.need_data.data = line
			self.need_data = None
			yield from self._run_protocol()
		else:
			assert self.request is None, 'server internal state error - not waiting for data but a request is active'
			verb, *argtext = map ( str.rstrip, b2s ( line ).split ( ' ', 1 ) ) # ex: verb='STLS', argtext=[] or verb='RETR', argtext=['1']
			verb = verb.upper() # TODO FIXME: are POP3 verbs case-sensitive?
			requestcls = _request_verbs.get ( verb )
			if requestcls is None:
				yield ErrorEvent ( 'Command not recognized' )
				return
			if requestcls.tls_required and not self.tls:
				yield ErrorEvent ( 'Command requires TLS to be active first' )
				return
			elif requestcls.tls_excluded and self.tls:
				yield ErrorEvent ( 'Command not available when TLS is active' )
				return
			request: Request = requestcls.__new__ ( requestcls )
			request_protocol = request._server_protocol ( self, argtext[0] if argtext else '' )
			self.request = request
			self.request_protocol = request_protocol
			yield from self._run_protocol()
	
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
		self.request_protocol = request._client_protocol ( self )
		#log.debug ( f'set {self.request=}' )
		yield from self._run_protocol()
	
	def _receive_line ( self, line: BYTES ) -> Iterator[Event]:
		log = logger.getChild ( 'Client._receive_line' )
		
		assert self.need_data, f'not expecting data at this time ({bytes(line)!r})'
		self.need_data.data = line
		self.need_data = None
		yield from self._run_protocol()

#endregion
