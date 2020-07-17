from __future__ import annotations

# python imports:
import logging
import socket
import ssl
from typing import Type

# email_proto imports:
from transport import SyncTransport

logger = logging.getLogger ( __name__ )


class SocketTransport ( SyncTransport ):
	sock: socket.socket
	
	def __init__ ( self, sock: socket.socket ) -> None:
		self.sock = sock
	
	@classmethod
	def connect ( cls: Type[SocketTransport], hostname: str, port: int, tls: bool ) -> SocketTransport:
		log = logger.getChild ( 'SocketTransport.connect' )
		
		# TODO FIXME: implement happy eyeballs?
		for *params, _, address in socket.getaddrinfo ( hostname, port ):
			sock = socket.socket ( *params )
			try:
				sock.connect ( address )
			except Exception as e:
				log.warning ( f'Error connecting to {address=}: {e!r}' )
				continue
			else:
				self = cls ( sock )
				if tls:
					self.starttls_client ( hostname )
				return self
		raise ConnectionError ( f'Unable to connect to {hostname=} {port=}' )
	
	def read ( self ) -> bytes:
		#log = logger.getChild ( 'SocketTransport.read' )
		return self.sock.recv ( 4096 )
	
	def write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'SocketTransport.write' )
		self.sock.sendall ( data )
	
	def starttls_client ( self, server_hostname: str ) -> None:
		context = self.ssl_context_or_default_client()
		
		self.sock = context.wrap_socket (
			self.sock,
			server_hostname = server_hostname,
		)
	
	def starttls_server ( self ) -> None:
		#log = logger.getChild ( 'SocketTransport.starttls_server' )
		context = self.ssl_context_or_default_server()
		
		self.sock = context.wrap_socket (
			self.sock,
			server_side = True,
		)
	
	def close ( self ) -> None:
		#log = logger.getChild ( 'SocketTransport.close' )
		self.sock.close()
