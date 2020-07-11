# system imports:
from abc import ABCMeta, abstractmethod
import logging

# email_proto imports:
import smtp_proto

logger = logging.getLogger ( __name__ )

b2s = smtp_proto.b2s

class Client ( metaclass = ABCMeta ):
	cli: smtp_proto.Client
	
	def _connect ( self, tls: bool ) -> smtp_proto.SuccessResponse:
		self.cli = smtp_proto.Client ( tls )
		return self.greeting()
	
	def greeting ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.GreetingRequest() )
	
	def helo ( self, local_hostname: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.HeloRequest ( local_hostname ) )
	
	def ehlo ( self, local_hostname: str ) -> smtp_proto.EhloResponse:
		r = self._send_recv ( smtp_proto.EhloRequest ( local_hostname ) )
		assert isinstance ( r, smtp_proto.EhloResponse ), f'invalid {r=}'
		return r
	
	def starttls ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.StartTlsRequest() )
	
	def auth_plain1 ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.AuthPlain1Request ( uid, pwd ) )
	
	def auth_plain2 ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.AuthPlain2Request ( uid, pwd ) )
	
	def auth_login ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.AuthLoginRequest ( uid, pwd ) )
	
	def expn ( self, mailbox: str ) -> smtp_proto.ExpnResponse:
		r = self._send_recv ( smtp_proto.ExpnRequest ( mailbox ) )
		assert isinstance ( r, smtp_proto.ExpnResponse )
		return r
	
	def vrfy ( self, mailbox: str ) -> smtp_proto.VrfyResponse:
		r = self._send_recv ( smtp_proto.VrfyRequest ( mailbox ) )
		assert isinstance ( r, smtp_proto.VrfyResponse )
		return r
	
	def mail_from ( self, email: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.MailFromRequest ( email ) )
	
	def rcpt_to ( self, email: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.RcptToRequest ( email ) )
	
	def data ( self, content: bytes ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.DataRequest ( content ) )
	
	def rset ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.RsetRequest() )
	
	def noop ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.NoOpRequest() )
	
	def quit ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.QuitRequest() )
	
	def _event ( self, event: smtp_proto.Event ) -> None:
		log = logger.getChild ( 'Client._event' )
		if isinstance ( event, smtp_proto.SendDataEvent ):
			try:
				for chunk in event.chunks:
					log.debug ( f'C>{b2s(chunk).rstrip()}' ) # TODO FIXME: SendDataEvent.chunks isn't line-based so this log.debug doesn't make sense
					self._write ( chunk )
			except Exception as e:
				event.exception = e
		elif isinstance ( event, smtp_proto.StartTlsBeginEvent ):
			try:
				self.on_starttls_begin ( event )
			except Exception as e:
				event.exception = e
		else:
			assert False, f'unrecognized {event=}'
	
	def _recv ( self, request: smtp_proto.Request ) -> smtp_proto.SuccessResponse:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				self._event ( event )
		assert isinstance ( request.response, smtp_proto.SuccessResponse )
		return request.response
	
	def _send_recv ( self, request: smtp_proto.Request ) -> smtp_proto.SuccessResponse:
		log = logger.getChild ( 'Client._send_recv' )
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
	
	@abstractmethod
	def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._close()' )


class Server ( metaclass = ABCMeta ):
	esmtp_8bitmime: bool = True
	esmtp_pipelining: bool = True
	
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	@abstractmethod
	def on_starttls_accept ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_starttls_accept()' )
	
	@abstractmethod
	def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_starttls_begin()' )
	
	@abstractmethod
	def on_authenticate ( self, event: smtp_proto.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_authenticate()' )
	
	def on_expn ( self, event: smtp_proto.ExpnEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	def on_vrfy ( self, event: smtp_proto.VrfyEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	@abstractmethod
	def on_mail_from ( self, event: smtp_proto.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_mail_from()' )
	
	@abstractmethod
	def on_rcpt_to ( self, event: smtp_proto.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	@abstractmethod
	def on_complete ( self, event: smtp_proto.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	def _run ( self, tls: bool ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = smtp_proto.Server ( self.hostname, tls )
			srv.esmtp_8bitmime = self.esmtp_8bitmime
			srv.esmtp_pipelining = self.esmtp_pipelining
			
			def _send ( *chunks: bytes ) -> None:
				for chunk in chunks:
					log.debug ( f'S>{b2s(chunk).rstrip()}' )
					self._write ( chunk )
			
			_send ( srv.greeting() )
			while True:
				try:
					data = self._read()
				except OSError: # TODO FIXME: more specific exception?
					raise smtp_proto.Closed()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					if isinstance ( event, smtp_proto.SendDataEvent ): # this will be the most common event...
						try:
							_send ( *event.chunks )
						except Exception as e:
							event.exception = e
					elif isinstance ( event, smtp_proto.RcptToEvent ): # 2nd most common event
						self.on_rcpt_to ( event )
					elif isinstance ( event, smtp_proto.StartTlsAcceptEvent ):
						self.on_starttls_accept ( event )
					elif isinstance ( event, smtp_proto.StartTlsBeginEvent ):
						try:
							self.on_starttls_begin ( event )
						except Exception as e:
							event.exception = e
					elif isinstance ( event, smtp_proto.AuthEvent ):
						self.on_authenticate ( event )
					elif isinstance ( event, smtp_proto.MailFromEvent ):
						self.on_mail_from ( event )
					elif isinstance ( event, smtp_proto.CompleteEvent ):
						self.on_complete ( event )
					elif isinstance ( event, smtp_proto.ExpnEvent ):
						self.on_expn ( event )
					elif isinstance ( event, smtp_proto.VrfyEvent ):
						self.on_vrfy ( event )
					else:
						assert False, f'unrecognized {event=}'
		except smtp_proto.Closed:
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
