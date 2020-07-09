from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import socket

# mail_proto imports:
import smtp
import smtp_sync

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s


class Transport:
	sock: socket.socket
	
	def _read ( self ) -> bytes:
		return self.sock.recv ( 4096 )
	
	def _write ( self, data: bytes ) -> None:
		self.sock.sendall ( data )
	
	def _close ( self ) -> None:
		self.sock.close()


class Client ( Transport, smtp_sync.Client ):
	
	def connect ( self, hostname: str, port: int ) -> None:
		log = logger.getChild ( 'Client.connect' )
		for *params, _, address in socket.getaddrinfo ( hostname, port ):
			self.sock = socket.socket ( *params )
			try:
				self.sock.connect ( address )
			except OSError as e:
				log.warning ( f'Error connecting to {address=}: {e!r}' )
			else:
				self._connect()
		raise ConnectionError ( f'Unable to connect to {hostname=} {port=}' )



class Server ( Transport, smtp_sync.Server ):
	
	def run ( self, sock: socket.socket ) -> None:
		self.sock = sock
		self._run()
