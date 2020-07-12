from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import asyncio
import logging
import ssl
from typing import Optional as Opt

# mail_proto imports:
import smtp_proto
import smtp_async

logger = logging.getLogger ( __name__ )


class Transport:
	rx: asyncio.StreamReader
	tx: asyncio.StreamWriter
	
	async def _read ( self ) -> bytes:
		#log = logger.getChild ( 'Transport._read' )
		try:
			data = await asyncio.wait_for (
				self.rx.readline(), # NOTE: there doesn't seem to be a way to tell asyncio to give us everything it has...
				timeout = 1.0, # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			)
		except asyncio.TimeoutError:
			raise TimeoutError ( f'{type(self).__module__}.{type(self).__name__} timeout waiting to read data' ) from None
		else:
			return data
	
	async def _write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'Transport._write' )
		self.tx.write ( data )
		try:
			return await asyncio.wait_for (
				self.tx.drain(),
				timeout = 1.0, # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			)
		except asyncio.TimeoutError:
			raise TimeoutError ( f'{type(self).__module__}.{type(self).__name__} timeout waiting to read data' ) from None
	
	async def close ( self ) -> None:
		self.tx.close()
		await self.tx.wait_closed()


class Client ( Transport, smtp_async.Client ):
	server_hostname: Opt[str] = None
	ssl_context: Opt[ssl.SSLContext] = None
	
	async def connect ( self, hostname: str, port: int, tls: bool ) -> None:
		self.server_hostname = hostname
		self.rx, self.tx = await asyncio.open_connection (
			hostname, port, ssl = tls,
		)
		await self._connect ( tls )
	
	async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		#log = logger.getChild ( 'Client.on_starttls_begin' )
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context ( ssl.Purpose.SERVER_AUTH )
		
		transport = await asyncio.get_event_loop().start_tls (
			self.tx.transport,
			getattr ( self.tx, '_protocol' ),
			sslcontext = self.ssl_context,
			server_hostname = self.server_hostname,
		)
		self.rx.set_transport ( transport )
		setattr ( self.tx, '_transport', transport )


class Server ( Transport, smtp_async.Server ):
	ssl_context: Opt[ssl.SSLContext] = None
	
	async def run ( self,
		rx: asyncio.StreamReader,
		tx: asyncio.StreamWriter,
		tls: bool,
	) -> None:
		self.rx = rx
		self.tx = tx
		await self._run ( tls )
	
	async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		#log = logger.getChild ( 'Server.on_starttls_begin' )
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context()
			self.ssl_context.verify_mode = ssl.CERT_NONE
		
		transport = await asyncio.get_event_loop().start_tls (
			self.tx.transport,
			getattr ( self.tx, '_protocol' ),
			sslcontext = self.ssl_context,
			server_side = True,
		)
		self.rx.set_transport ( transport )
		setattr ( self.tx, '_transport', transport )
