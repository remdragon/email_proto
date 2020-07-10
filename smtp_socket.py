from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import socket
import ssl

# mail_proto imports:
import smtp_proto
import smtp_sync

logger = logging.getLogger ( __name__ )

b2s = smtp_proto.b2s


class Transport:
	sock: socket.socket
	
	def _read ( self ) -> bytes:
		return self.sock.recv ( 4096 )
	
	def _write ( self, data: bytes ) -> None:
		self.sock.sendall ( data )
	
	def _close ( self ) -> None:
		self.sock.close()


class Client ( Transport, smtp_sync.Client ):
	server_hostname: Opt[str] = None
	ssl_context: Opt[ssl.SSLContext] = None
	
	def connect ( self, hostname: str, port: int ) -> None:
		log = logger.getChild ( 'Client.connect' )
		self.server_hostname = hostname
		for *params, _, address in socket.getaddrinfo ( hostname, port ):
			self.sock = socket.socket ( *params )
			try:
				self.sock.connect ( address )
			except OSError as e:
				log.warning ( f'Error connecting to {address=}: {e!r}' )
			else:
				self._connect()
		raise ConnectionError ( f'Unable to connect to {hostname=} {port=}' )
	
	def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		log = logger.getChild ( 'Client.on_starttls_begin' )
		try:
			log.debug ( f'{self.server_hostname=}' )
			log.debug ( f'pre-{self.ssl_context=}' )
			if self.ssl_context is None:
				self.ssl_context = ssl.create_default_context ( ssl.Purpose.SERVER_AUTH )
			log.debug ( f'aft-{self.ssl_context=}' )
			log.debug ( f'pre-{self.sock=}' )
			self.sock = self.ssl_context.wrap_socket (
				self.sock,
				server_hostname = self.server_hostname,
			)
			log.debug ( f'aft-{self.sock=}' )
		except Exception:
			log.exception ( 'Error starting tls:' )
			raise smtp_proto.ResponseEvent ( 421, 'Error starting tls' )



class Server ( Transport, smtp_sync.Server ):
	ssl_context: Opt[ssl.SSLContext] = None
	
	def run ( self, sock: socket.socket ) -> None:
		self.sock = sock
		self._run()
	
	def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		try:
			if self.ssl_context is None:
				self.ssl_context = ssl.create_default_context()
			self.sock = self.ssl_context.wrap_socket (
				self.sock,
				server_side = True,
				#server_hostname = self.
			)
		except Exception as e:
			event.exception = e
			#raise smtp_proto.ResponseEvent ( 421, 'Error starting tls' ) from e
