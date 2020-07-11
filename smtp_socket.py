from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import socket
import ssl
from typing import Optional as Opt

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
	
	def connect ( self, hostname: str, port: int, tls: bool ) -> None:
		log = logger.getChild ( 'Client.connect' )
		self.server_hostname = hostname
		for *params, _, address in socket.getaddrinfo ( hostname, port ):
			self.sock = socket.socket ( *params )
			try:
				self.sock.connect ( address )
				if tls:
					self._wrap_ssl()
			except Exception as e:
				log.warning ( f'Error connecting to {address=}: {e!r}' )
			else:
				self._connect ( tls )
		raise ConnectionError ( f'Unable to connect to {hostname=} {port=}' )
	
	def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		#log = logger.getChild ( 'Client.on_starttls_begin' )
		self._wrap_ssl()
	
	def _wrap_ssl ( self ) -> None:
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context ( ssl.Purpose.SERVER_AUTH )
		self.sock = self.ssl_context.wrap_socket (
			self.sock,
			server_hostname = self.server_hostname,
		)



class Server ( Transport, smtp_sync.Server ):
	ssl_context: Opt[ssl.SSLContext] = None
	
	def run ( self, sock: socket.socket, tls: bool ) -> None:
		self.sock = sock
		self._run ( tls )
	
	def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context()
			self.ssl_context.verify_mode = ssl.CERT_NONE
		self.sock = self.ssl_context.wrap_socket (
			self.sock,
			server_side = True,
		)
