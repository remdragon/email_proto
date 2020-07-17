from __future__ import annotations

# python imports:
import asyncio
import contextlib
import logging
import ssl
from typing import Iterator, Type

# email_proto imports:
from transport import AsyncTransport

logger = logging.getLogger ( __name__ )


@contextlib.contextmanager
def asyncio_timeout ( self: object, text: str ) -> Iterator[None]:
	try:
		yield
	except asyncio.TimeoutError:
		cls = self.__class__
		raise TimeoutError ( f'{cls.__module__}.{cls.__name__} timeout {text}' ) from None

class AsyncioTransport ( AsyncTransport ):
	rx: asyncio.StreamReader
	tx: asyncio.StreamWriter
	
	def __init__ ( self, rx: asyncio.StreamReader, tx: asyncio.StreamWriter ) -> None:
		self.rx, self.tx = rx, tx
	
	@classmethod
	async def connect ( cls: Type[AsyncioTransport],
		hostname: str,
		port: int,
		tls: bool,
	) -> AsyncioTransport:
		log = logger.getChild ( 'AsyncioTransport.connect' )
		rx, tx = await asyncio.open_connection (
			hostname, port, ssl = tls,
		)
		return cls ( rx, tx )
	
	async def read ( self ) -> bytes:
		#log = logger.getChild ( 'AsyncioTransport.read' )
		with asyncio_timeout ( self, 'waiting to read data' ):
			return await asyncio.wait_for (
				self.rx.readline(), # NOTE: there doesn't seem to be a way to tell asyncio to give us everything it has...
				timeout = 1.0, # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			)
	
	async def write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'AsyncioTransport.write' )
		self.tx.write ( data )
		with asyncio_timeout ( self, 'waiting to write data' ):
			return await asyncio.wait_for (
				self.tx.drain(),
				timeout = 1.0, # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			)
	
	async def starttls_client ( self, server_hostname: str ) -> None:
		context = self.ssl_context_or_default_client()
		
		transport = await asyncio.get_event_loop().start_tls (
			self.tx.transport,
			getattr ( self.tx, '_protocol' ),
			sslcontext = context,
			server_hostname = server_hostname,
		)
		self.rx.set_transport ( transport )
		setattr ( self.tx, '_transport', transport )
	
	async def starttls_server ( self ) -> None:
		#log = logger.getChild ( 'AsyncioTransport.starttls_server' )
		context = self.ssl_context_or_default_server()
		
		transport = await asyncio.get_event_loop().start_tls (
			self.tx.transport,
			getattr ( self.tx, '_protocol' ),
			sslcontext = context,
			server_side = True,
		)
		self.rx.set_transport ( transport )
		setattr ( self.tx, '_transport', transport )
	
	async def close ( self ) -> None:
		#log = logger.getChild ( 'AsyncioTransport.close' )
		self.tx.close()
		await self.tx.wait_closed()
