from __future__ import annotations

# python imports:
from abc import ABCMeta, abstractmethod
import contextlib
import logging
import sys
from types import TracebackType
from typing import (
	Generic, Iterator, Optional as Opt, Sequence as Seq, Tuple, Type, TypeVar,
	Union,
)

# email_proto imports:
from base_proto import (
	BaseRequest, RequestType, ResponseType, Event, SendDataEvent,
	ClientProtocol, ServerProtocol, Closed,
)
from transport import SyncTransport, AsyncTransport
from util import BYTES, b2s

logger = logging.getLogger ( __name__ )

T = TypeVar ( 'T' )


@contextlib.contextmanager
def _event_exception_safety ( event: Event ) -> Iterator[None]:
	try:
		yield
	except Exception:
		event.exc_info = sys.exc_info()

class SyncEventHandler:
	transport: SyncTransport
	
	def on_SendDataEvent ( self, event: SendDataEvent ) -> None:
		log = logger.getChild ( 'Client.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			self.transport.write ( chunk )
	
	def _on_event ( self, event: Event ) -> None:
		log = logger.getChild ( 'SyncEventHandler._on_event' )
		with _event_exception_safety ( event ):
			func = getattr ( self, f'on_{type(event).__name__}' )
			func ( event )
	
	def close ( self ) -> None:
		self.transport.close()


class AsyncEventHandler:
	transport: AsyncTransport
	
	async def on_SendDataEvent ( self, event: SendDataEvent ) -> None:
		log = logger.getChild ( 'Client.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			await self.transport.write ( chunk )
	
	async def _on_event ( self, event: Event ) -> None:
		log = logger.getChild ( 'AsyncEventHandler._on_event' )
		with _event_exception_safety ( event ):
			func = getattr ( self, f'on_{type(event).__name__}' )
			await func ( event )
	
	async def close ( self ) -> None:
		await self.transport.close()


class Client ( metaclass = ABCMeta ):
	protocls: Type[ClientProtocol]
	proto: ClientProtocol


class SyncClient ( SyncEventHandler, Client ):
	def __init__ ( self,
		transport: SyncTransport,
		tls: bool,
		server_hostname: str,
	) -> None:
		self.transport = transport
		self.server_hostname = server_hostname
		self.proto = self.protocls ( tls )
	
	def _request ( self, request: RequestType[ResponseType] ) -> ResponseType:
		log = logger.getChild ( 'Client._request' )
		for event in self.proto.send ( request ):
			self._on_event ( event )
		while not request.base_response:
			data: bytes = self.transport.read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.proto.receive ( data ):
				self._on_event ( event )
		assert (
			request.base_response is not None
		and
			request.base_response.is_success()
		), f'invalid {request.base_response=}'
		return request.response


class AsyncClient ( AsyncEventHandler, Client ):
	def __init__ ( self,
		transport: AsyncTransport,
		tls: bool,
		server_hostname: str,
	) -> None:
		self.transport = transport
		self.server_hostname = server_hostname
		self.proto = self.protocls ( tls )
	
	async def _request ( self, request: RequestType[ResponseType] ) -> ResponseType:
		log = logger.getChild ( 'Client._request' )
		for event in self.proto.send ( request ):
			await self._on_event ( event )
		while not request.base_response:
			data: bytes = await self.transport.read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.proto.receive ( data ):
				await self._on_event ( event )
		assert (
			request.base_response is not None
		and
			request.base_response.is_success()
		), f'invalid {request.base_response=}'
		return request.response


class Server ( metaclass = ABCMeta ):
	protocls: Type[ServerProtocol]
	proto: ServerProtocol


@contextlib.contextmanager
def close_if_oserror() -> Iterator[None]:
	try:
		yield
	except OSError as e: # TODO FIXME: more specific exception?
		raise Closed ( repr ( e ) ) from e

class SyncServer ( SyncEventHandler, Server ):
	def __init__ ( self,
		transport: SyncTransport,
		tls: bool,
		server_hostname: str,
	) -> None:
		self.transport = transport
		self.server_hostname = server_hostname
		self.proto = self.protocls ( tls, server_hostname )
	
	def run ( self ) -> None:
		log = logger.getChild ( 'SyncServer.run' )
		try:
			for event in self.proto.startup():
				self._on_event ( event )
			
			while True:
				with close_if_oserror():
					data = self.transport.read()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in self.proto.receive ( data ):
					self._on_event ( event )
		except Closed as e:
			log.debug ( f'connection closed with reason: {e.args[0]!r}' )
		finally:
			self.transport.close()


class AsyncServer ( AsyncEventHandler, Server ):
	def __init__ ( self,
		transport: AsyncTransport,
		tls: bool,
		server_hostname: str,
	) -> None:
		self.transport = transport
		self.proto = self.protocls ( tls, server_hostname )
	
	async def run ( self ) -> None:
		log = logger.getChild ( 'AsyncServer.run' )
		try:
			for event in self.proto.startup():
				await self._on_event ( event )
			
			while True:
				with close_if_oserror():
					data = await self.transport.read()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in self.proto.receive ( data ):
					await self._on_event ( event )
		except Closed as e:
			log.debug ( f'connection closed with reason: {e.args[0]!r}' )
		finally:
			await self.transport.close()
