from __future__ import annotations

# python imports:
import logging
import ssl
import trio # pip install trio trio-typing
from typing import Type

# email_proto imports:
from transport import AsyncTransport

logger = logging.getLogger ( __name__ )


class TrioTransport ( AsyncTransport ):
	happy_eyeballs_delay: float = 0.25 # this is the same as trio's default circa version 0.16.0
	stream: trio.abc.Stream
	
	def __init__ ( self, stream: trio.abc.Stream ) -> None:
		self.stream = stream
	
	@classmethod
	async def connect ( cls: Type[TrioTransport], hostname: str, port: int, tls: bool ) -> TrioTransport:
		log = logger.getChild ( 'TrioTransport.connect' )
		stream = await trio.open_tcp_stream ( hostname, port,
			happy_eyeballs_delay = cls.happy_eyeballs_delay,
		)
		self = cls ( stream )
		if tls:
			self.starttls_client ( hostname )
		return self
	
	async def read ( self ) -> bytes:
		#log = logger.getChild ( 'TrioTransport.read' )
		with trio.move_on_after ( 1.0 ): # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			return await self.stream.receive_some()
		raise TimeoutError ( f'{type(self).__module__}.{type(self).__name__} timeout waiting to read data' )
	
	async def write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'TrioTransport.write' )
		with trio.move_on_after ( 1.0 ): # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			await self.stream.send_all ( data )
			return
		raise TimeoutError ( f'{type(self).__module__}.{type(self).__name__} timeout waiting to write {bytes(data)=}' )
	
	async def starttls_client ( self, server_hostname: str ) -> None:
		context = self.ssl_context_or_default_client()
		
		self.stream = trio.SSLStream (
			self.stream,
			ssl_context = context,
			server_hostname = server_hostname,
		)
	
	async def starttls_server ( self ) -> None:
		#log = logger.getChild ( 'TrioTransport.starttls_server' )
		context = self.ssl_context_or_default_server()
		
		self.stream = trio.SSLStream (
			self.stream,
			ssl_context = context,
			server_side = True,
		)
	
	async def close ( self ) -> None:
		#log = logger.getChild ( 'TrioTransport.close' )
		with trio.move_on_after ( 0.05 ):
			await self.stream.aclose() # TODO FIXME: why sometimes getting hung up when in ssl?
