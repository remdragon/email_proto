# system imports:
from abc import ABCMeta, abstractmethod
import logging
import sys
from typing import Optional as Opt

# email_proto imports:
import pop3_proto as proto
from util import b2s

logger = logging.getLogger ( __name__ )


class Client ( metaclass = ABCMeta ):
	cli: proto.Client
	
	async def _connect ( self, tls: bool ) -> proto.SuccessResponse:
		self.cli = proto.Client ( tls )
		return await self.greeting()
	
	async def greeting ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.GreetingRequest() )
	
	async def capa ( self ) -> proto.MultiResponse:
		log = logger.getChild ( 'Client.capa' )
		r = await self._send_recv ( proto.CapaRequest() )
		assert isinstance ( r, proto.MultiResponse ) # TODO FIXME: figure out a better way...
		return r
	
	async def starttls ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.StartTlsRequest() )
	
	async def rset ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.RsetRequest() )
	
	async def noop ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.NoOpRequest() )
	
	async def quit ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.QuitRequest() )
	
	async def on_SendDataEvent ( self, event: proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Client.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			await self._write ( chunk )
	
	async def _on_event ( self, event: proto.Event ) -> None:
		log = logger.getChild ( 'Client._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			await func ( event )
		except Exception:
			event.exc_info = sys.exc_info()
	
	async def _recv ( self, request: proto.Request ) -> proto.SuccessResponse:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = await self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				await self._on_event ( event )
		assert isinstance ( request.response, proto.SuccessResponse ), f'invalid {request.response=}'
		return request.response
	
	async def _send_recv ( self, request: proto.Request ) -> proto.SuccessResponse:
		log = logger.getChild ( 'Client._send_recv' )
		log.debug ( f'{request=}' )
		for event in self.cli.send ( request ):
			log.debug ( f'{event=}' )
			await self._on_event ( event )
		log.debug ( 'yielding to _recv()' )
		return await self._recv ( request )
	
	@abstractmethod
	async def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._read()' )
	
	@abstractmethod
	async def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._write()' )
	
	@abstractmethod
	async def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )
	
	@abstractmethod
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )


class Server ( metaclass = ABCMeta ):
	
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	async def on_GreetingAcceptEvent ( self, event: proto.GreetingAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	@abstractmethod
	async def on_StartTlsAcceptEvent ( self, event: proto.StartTlsAcceptEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_starttls_accept()' )
	
	@abstractmethod
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )
	
	async def on_SendDataEvent ( self, event: proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Server.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			await self._write ( chunk )
	
	async def _on_event ( self, event: proto.Event ) -> None:
		log = logger.getChild ( 'Server._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			await func ( event )
		except Exception:
			event.exc_info = sys.exc_info()
	
	async def _run ( self, tls: bool, apop_challenge: Opt[str] = None ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = proto.Server ( self.hostname, tls, apop_challenge )
			
			for event in srv.startup():
				await self._on_event ( event )
			
			while True:
				try:
					data = await self._read()
				except OSError as e: # TODO FIXME: more specific exception?
					raise proto.Closed ( repr ( e ) ) from e
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					await self._on_event ( event )
		except proto.Closed as e:
			log.debug ( f'connection closed with reason: {e.args[0]!r}' )
		finally:
			await self.close()
	
	@abstractmethod
	async def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	async def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	async def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )
