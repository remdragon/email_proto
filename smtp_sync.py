# system imports:
from abc import ABCMeta, abstractmethod
import logging

# email_proto imports:
import smtp

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s

class Client ( metaclass = ABCMeta ):
	cli: smtp.Client
	
	def _connect ( self ) -> smtp.Response:
		greeting = smtp.GreetingRequest()
		self.cli = smtp.Client ( greeting )
		return self._recv ( greeting )
	
	def helo ( self, local_hostname: str ) -> smtp.Response:
		return self._send_recv ( smtp.HeloRequest ( local_hostname ) )
	
	def ehlo ( self, local_hostname: str ) -> smtp.Response:
		return self._send_recv ( smtp.EhloRequest ( local_hostname ) )
	
	def auth_plain1 ( self, uid: str, pwd: str ) -> smtp.Response:
		return self._send_recv ( smtp.AuthPlain1Request ( uid, pwd ) )
	
	def auth_plain2 ( self, uid: str, pwd: str ) -> smtp.Response:
		return self._send_recv ( smtp.AuthPlain2Request ( uid, pwd ) )
	
	def auth_login ( self, uid: str, pwd: str ) -> smtp.Response:
		return self._send_recv ( smtp.AuthLoginRequest ( uid, pwd ) )
	
	def expn ( self, maillist: str ) -> smtp.Response:
		return self._send_recv ( smtp.ExpnRequest ( maillist ) )
	
	def vrfy ( self, mailbox: str ) -> smtp.Response:
		return self._send_recv ( smtp.VrfyRequest ( mailbox ) )
	
	def mail_from ( self, email: str ) -> smtp.Response:
		return self._send_recv ( smtp.MailFromRequest ( email ) )
	
	def rcpt_to ( self, email: str ) -> smtp.Response:
		return self._send_recv ( smtp.RcptToRequest ( email ) )
	
	def data ( self, content: bytes ) -> smtp.Response:
		return self._send_recv ( smtp.DataRequest ( content ) )
	
	def rset ( self ) -> smtp.Response:
		return self._send_recv ( smtp.RsetRequest() )
	
	def noop ( self ) -> smtp.Response:
		return self._send_recv ( smtp.NoOpRequest() )
	
	def quit ( self ) -> smtp.Response:
		return self._send_recv ( smtp.QuitRequest() )
	
	def _event ( self, event: smtp.Event ) -> None:
		log = logger.getChild ( 'Client._event' )
		if isinstance ( event, smtp.SendDataEvent ):
			log.debug ( f'C>{b2s(event.data).rstrip()}' )
			self._write ( event.data )
		elif isinstance ( event, smtp.ErrorEvent ):
			raise smtp.ErrorResponse ( event.code, event.message )
		else:
			assert False, f'unrecognized {event=}'
	
	def _recv ( self, request: smtp.Request ) -> smtp.Response:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				self._event ( event )
		return request.response
	
	def _send_recv ( self, request: smtp.Request ) -> smtp.Response:
		#log = logger.getChlid ( 'Client._send_recv' )
		for event in self.cli.send ( request ):
			self._event ( event )
		return self._recv ( request )
	
	@abstractmethod
	def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._read()' )
	
	@abstractmethod
	def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._write()' )
	
	@abstractmethod
	def _close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._close()' )


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
	
	def _run ( self ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = smtp.Server ( self.hostname )
			
			def _send ( data: bytes ) -> None:
				log.debug ( f'S>{b2s(data).rstrip()}' )
				self._write ( data )
			
			_send ( srv.greeting() )
			while True:
				try:
					data = self._read()
				except OSError: # TODO FIXME: more specific exception?
					raise smtp.Closed()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					if isinstance ( event, smtp.SendDataEvent ): # this will be the most common event...
						_send ( event.data )
					elif isinstance ( event, smtp.RcptToEvent ): # 2nd most common event
						self.on_rcpt_to ( event )
					elif isinstance ( event, smtp.AuthEvent ):
						self.on_authenticate ( event )
					elif isinstance ( event, smtp.MailFromEvent ):
						self.on_mail_from ( event )
					elif isinstance ( event, smtp.CompleteEvent ):
						self.on_complete ( event )
					elif isinstance ( event, smtp.ErrorEvent ):
						raise smtp.ErrorResponse ( event.code, event.message )
					else:
						assert False, f'unrecognized {event=}'
		except smtp.Closed:
			pass
		finally:
			self._close()
	
	@abstractmethod
	def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	def _close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._close()' )
