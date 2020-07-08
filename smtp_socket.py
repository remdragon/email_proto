from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import socket

# mail_proto imports:
import smtp

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s

class Client:
	cli: smtp.Client
	sock: socket.socket
	
	def connect ( self, hostname: str, port: int ) -> None:
		log = logger.getChild ( 'Client.connect' )
		for *params, _, address in socket.getaddrinfo ( hostname, port ):
			sock = socket.socket ( *params )
			try:
				sock.connect ( address )
			except OSError as e:
				log.warning ( f'Error connecting to {address=}: {e!r}' )
			else:
				self._connect ( sock )
		raise ConnectionError ( f'Unable to connection to {hostname=} {port=}' )
	
	def _connect ( self, sock: socket.socket ) -> None:
		self.sock = sock
		greeting = smtp.GreetingRequest()
		self.cli = smtp.Client ( greeting )
		self._recv ( greeting )
	
	def helo ( self, local_hostname: str ) -> None:
		self._send_recv ( smtp.HeloRequest ( local_hostname ) )
	
	def auth_plain1 ( self, uid: str, pwd: str ) -> None:
		self._send_recv ( smtp.AuthPlain1Request ( uid, pwd ) )
	
	def auth_plain2 ( self, uid: str, pwd: str ) -> None:
		self._send_recv ( smtp.AuthPlain2Request ( uid, pwd ) )
	
	def auth_login ( self, uid: str, pwd: str ) -> None:
		self._send_recv ( smtp.AuthLoginRequest ( uid, pwd ) )
	
	def mail_from ( self, email: str ) -> None:
		self._send_recv ( smtp.MailFromRequest ( email ) )
	
	def rcpt_to ( self, email: str ) -> None:
		self._send_recv ( smtp.RcptToRequest ( email ) )
	
	def data ( self, content: bytes ) -> None:
		self._send_recv ( smtp.DataRequest ( content ) )
	
	def quit ( self ) -> None:
		self._send_recv ( smtp.QuitRequest() )
	
	def _event ( self, event: smtp.Event ) -> None:
		log = logger.getChild ( 'Client._event' )
		if isinstance ( event, smtp.SendDataEvent ):
			log.debug ( f'C>{b2s(event.data).rstrip()}' )
			self.sock.sendall ( event.data )
		elif isinstance ( event, smtp.ErrorEvent ):
			raise smtp.ErrorEvent ( event.code, event.message )
		else:
			assert False, f'unrecognized {event=}'
	
	def _recv ( self, request: smtp.Request ) -> smtp.Response:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = self.sock.recv ( 4096 )
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				self._event ( event )
		return request.response
	
	def _send_recv ( self, request: smtp.Request ) -> smtp.Response:
		#log = logger.getChlid ( 'Client._send_recv' )
		for event in self.cli.send ( request ):
			self._event ( event )
		return self._recv ( request )


class Server ( metaclass = ABCMeta ):
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	@abstractmethod
	def on_authenticate ( self, event: smtp.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_authenticate()' )
	
	@abstractmethod
	def on_mail_from ( self, event: smtp.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_mail_from()' )
	
	@abstractmethod
	def on_rcpt_to ( self, event: smtp.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	@abstractmethod
	def on_complete ( self, event: smtp.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	def run ( self, sock: socket.socket ) -> None:
		log = logger.getChild ( 'Server.run' )
		try:
			srv = smtp.Server ( self.hostname )
			
			def _send ( data: bytes ) -> None:
				log.debug ( f'S>{b2s(data).rstrip()}' )
				sock.sendall ( data )
			
			def _recv() -> bytes:
				try:
					data = sock.recv ( 4096 )
				except OSError: # TODO FIXME: more specific exception?
					raise smtp.Closed()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				return data
			
			_send ( srv.greeting() )
			while True:
				data = _recv()
				for event in srv.receive ( data ):
					if isinstance ( event, smtp.SendDataEvent ): # this will be the most common event...
						_send ( event.data )
					elif isinstance ( event, smtp.RcptToEvent ): # 2nd most common event
						#log.debug ( f'{event.rcpt_to=}' )
						self.on_rcpt_to ( event )
					elif isinstance ( event, smtp.AuthEvent ):
						self.on_authenticate ( event )
					elif isinstance ( event, smtp.MailFromEvent ):
						#log.debug ( f'{event.mail_from=}' )
						self.on_mail_from ( event )
					elif isinstance ( event, smtp.CompleteEvent ):
						self.on_complete ( event )
					elif isinstance ( event, smtp.ErrorEvent ):
						raise smtp.ErrorEvent ( event.code, event.message )
					else:
						assert False, f'unrecognized {event=}'
		except smtp.Closed:
			pass
		finally:
			sock.close()
