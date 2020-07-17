from __future__ import annotations

# python imports:
from abc import ABCMeta, abstractmethod
import logging
import re
from types import TracebackType
from typing import (
	Callable, Generator, Generic, Iterator, Optional as Opt, Sequence as Seq,
	Tuple, Type, TypeVar, Union,
)

# email_proto imports:
from util import bytes_types, BYTES, b2s, s2b

logger = logging.getLogger ( __name__ )

EXC_INFO = Opt[Union[
	Tuple[Type[BaseException],BaseException,TracebackType],
	Tuple[None,None,None],
]]

_r_eol = re.compile ( r'[\r\n]' )


class Event ( Exception ):
	exc_info: EXC_INFO = None
	
	def go ( self ) -> Iterator[Event]:
		yield self
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}()'


class Closed ( Exception ): # TODO FIXME: BaseException?
	def __init__ ( self, reason: str = '' ) -> None:
		super().__init__ ( reason or '(none given)' )


class ProtocolError ( Exception ):
	pass


ResponseType = TypeVar ( 'ResponseType', bound = 'BaseResponse' )
class BaseResponse ( Exception, metaclass = ABCMeta ):
	@abstractmethod
	def is_success ( self ) -> bool:
		cls = self.__class__
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.is_success()' )


RequestProtocolGenerator = Generator[Event,None,None]


class BaseRequest ( metaclass = ABCMeta ):
	# this class is the basis of all client/server command handling
	# 1) client uses __init__() to construct request
	# 2) server bypasses __init__() for technical reasons
	# 3) _client_protocol() implements client-side state machine
	# 4) _server_protocol() implements server-side state machine
	tls_required: bool = False
	tls_excluded: bool = False
	base_response: Opt[BaseResponse] = None
	
	def __repr__ ( self ) -> str:
		cls = type ( self )
		return f'{cls.__module__}.{cls.__name__}()'
	
	@abstractmethod
	def _client_protocol ( self, client: ClientProtocol ) -> RequestProtocolGenerator:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._client_protocol()' )
	
	@abstractmethod
	def _server_protocol ( self, server: ServerProtocol, prefix: str, suffix: str ) -> RequestProtocolGenerator:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._server_protocol()' )


class RequestT ( BaseRequest, Generic[ResponseType] ):
	responsecls: Type[ResponseType]
	
	@property
	def response ( self ) -> ResponseType:
		assert isinstance ( self.base_response, self.responsecls )
		return self.base_response
RequestType = RequestT[ResponseType]


class NeedDataEvent ( Event ):
	data: Opt[bytes] = None
	response: Opt[BaseResponse] = None
	
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


class Protocol ( metaclass = ABCMeta ):
	_buf: bytes = b''
	request: Opt[BaseRequest] = None
	request_protocol: Opt[Generator[Event,None,None]] = None
	need_data: Opt[NeedDataEvent] = None
	tls: bool # whether or not the connection is currently encrypted
	_MAXLINE: int
	
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
		if len ( self._buf ) >= self._MAXLINE:
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
				log.debug ( 'yielding to request protocol' )
				event = next ( self.request_protocol )
				log.debug ( f'{event=}' )
				if isinstance ( event, NeedDataEvent ):
					if self.request.base_response is not None:
						log.warning ( f'INTERNAL ERROR - {self.request!r} pushed NeedDataEvent but has a response set - this can cause upstack deadlock ({self.request.base_response!r})' )
						self.request.base_response = None
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
		except BaseResponse as response: # client protocol
			request, self.request = self.request, None
			#log.debug ( f'{request=} finished with {response=}' )
			self.request = None
			self.request_protocol = None
			if not response.is_success():
				raise
			assert isinstance ( request, BaseRequest )
			request.base_response = response
		except SendDataEvent as event: # server protocol
			#log.debug ( f'protocol finished with {event=}' )
			self.request = None
			self.request_protocol = None
			yield event
		except StopIteration:
			# client protocol *must* raise a ResponseEvent
			# *or* set it's base_response attribute before exiting
			# if not, the smtp_[a]sync.Client._recv() will get stuck waiting for data that never arrives
			request, self.request = self.request, None
			self.request_protocol = None
			if not request.base_response and isinstance ( self, ClientProtocol ):
				log.warning (
					f'INTERNAL ERROR:'
					f' {type(self.request).__module__}.{type(self.request).__name__}'
					f'._client_protocol() exit w/o response - this can cause upstack deadlock'
				)
				raise Closed ( 'INTERNAL ERROR - CLIENT PROTOCOLS MUST THROW THEIR RESPONSE' )
			#log.debug ( f'protocol finished with {self.request.response=}' )
		except Exception as e:
			self.request = None
			self.request_protocol = None
			log.exception ( 'internal protocol error:' )
			raise Closed ( repr ( e ) ) from e


class ClientProtocol ( Protocol ):
	def send ( self, request: BaseRequest ) -> Iterator[Event]:
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


class ServerProtocol ( Protocol ):
	pedantic: bool = True # set this to False to relax behaviors that cause no harm for the protocol
	auth_uid: Opt[str] = None
	
	def __init__ ( self, tls: bool, hostname: str ) -> None:
		assert isinstance ( hostname, str ) and not _r_eol.search ( hostname ), f'invalid {hostname=}'
		self.hostname = hostname
		super().__init__ ( tls )
		self.reset()
	
	def reset ( self ) -> None:
		pass
	
	def startup ( self ) -> Iterator[Event]:
		# override this if server protocol needs to say "hi" first
		yield from ()
	
	@abstractmethod
	def _parse_request_line ( self, line: BYTES ) -> Tuple[str,Opt[Type[BaseRequest]],str]:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._parse_request_line()' )
	
	@abstractmethod
	def _error_invalid_command ( self ) -> Event:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._error_invalid_command()' )
	
	@abstractmethod
	def _error_tls_required ( self ) -> Event:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._error_tls_required()' )
	
	@abstractmethod
	def _error_tls_excluded ( self ) -> Event:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._error_tls_excluded()' )
	
	def _receive_line ( self, line: BYTES ) -> Iterator[Event]:
		#log = logger.getChild ( 'Server._receive_line' )
		if self.need_data:
			self.need_data.data = line
			self.need_data = None
			yield from self._run_protocol()
		else:
			assert self.request is None, 'server internal state error - not waiting for data but a request is active'
			try:
				prefix, requestcls, suffix = self._parse_request_line ( line )
			except SendDataEvent as e:
				yield e
				return
			if requestcls is None:
				yield self._error_invalid_command()
				return
			if requestcls.tls_required and not self.tls:
				yield self._error_tls_required()
				return
			elif requestcls.tls_excluded and self.tls:
				yield self._error_tls_excluded()
				return
			request: BaseRequest = requestcls.__new__ ( requestcls )
			request_protocol = request._server_protocol ( self, prefix, suffix )
			self.request = request
			self.request_protocol = request_protocol
			yield from self._run_protocol()

#region client protocol helpers

class ClientUtil:
	def __init__ ( self,
		parser: Callable[[BYTES],ResponseType],
	) -> None:
		self.parser = parser
	
	def send ( self, line: str ) -> Iterator[Event]:
		assert line.endswith ( '\r\n' ), f'invalid {line=}'
		yield from ( event := SendDataEvent ( s2b ( line ) ) ).go()

	def recv_ok ( self, event: Opt[NeedDataEvent] = None ) -> Iterator[Event]:
		if event is None:
			event = NeedDataEvent()
		yield from event.reset().go()
		event.response = response = self.parser ( event.data or b'' )
		if not response.is_success():
			raise response

	def recv_done ( self ) -> Iterator[Event]:
		log = logger.getChild ( 'recv_done' )
		yield from ( event := NeedDataEvent() ).go()
		response = self.parser ( event.data or b'' )
		raise response

	def send_recv_ok ( self, line: str, event: Opt[NeedDataEvent] = None ) -> Iterator[Event]:
		log = logger.getChild ( 'send_recv_ok' )
		yield from self.send ( line )
		yield from self.recv_ok ( event )

	def send_recv_done ( self, line: str ) -> Iterator[Event]:
		yield from self.send ( line )
		yield from self.recv_done()

#endregion client protocol helpers
