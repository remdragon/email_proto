# python imports:
import contextlib
import logging
from pathlib import Path
import sys
from typing import Iterator, Optional as Opt, Tuple, Type
import unittest

if __name__=='__main__': # pragma: no cover
	sys.path.append ( str ( Path ( __file__ ).parent.parent.absolute() ) )

# email_proto imports:
import base_proto
from util import BYTES

logger = logging.getLogger ( __name__ )

@contextlib.contextmanager
def quiet_logging ( quiet: bool = True ) -> Iterator[None]:
	try:
		if quiet:
			logging.disable ( logging.CRITICAL )
		yield None
	finally:
		if quiet:
			logging.disable ( logging.NOTSET )


class Tests ( unittest.TestCase ):
	def test_misc ( self ) -> None:
		test = self
		
		class BadResponse ( base_proto.BaseResponse ):
			def is_success ( self ) -> bool:
				return super().is_success()
		bad1 = BadResponse()
		with test.assertRaises ( NotImplementedError ):
			bad1.is_success()
		
		class BadRequest ( base_proto.BaseRequest ):
			def _client_protocol ( self, client: base_proto.ClientProtocol ) -> base_proto.RequestProtocolGenerator:
				return super()._client_protocol ( client )
			def _server_protocol ( self, server: base_proto.ServerProtocol, prefix: str, suffix: str ) -> base_proto.RequestProtocolGenerator:
				return super()._server_protocol ( server, prefix, suffix )
		bad2 = BadRequest()
		with test.assertRaises ( NotImplementedError ):
			bad2._client_protocol ( None )
		with test.assertRaises ( NotImplementedError ):
			bad2._server_protocol ( None, '', '' )
		
		def IsSendData ( evt: base_proto.Event ) -> base_proto.SendDataEvent:
			assert isinstance ( evt, base_proto.SendDataEvent )
			return evt
		
		class TestProtocol ( base_proto.Protocol ):
			_MAXLINE = 42
			def _receive_line ( self, line: bytes ) -> Iterator[base_proto.Event]:
				if line:
					yield base_proto.SendDataEvent ( line )
		tp = TestProtocol ( False )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in tp.receive ( b'foo\r' ) ]
		test.assertEqual ( evts, [] )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in tp.receive ( b'\nba' ) ]
		test.assertEqual ( evts, [
			b'foo\r\n',
		] )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in tp.receive ( b'ar\r\nbaz' ) ]
		test.assertEqual ( evts, [
			b'baar\r\n',
		] )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in tp.receive ( b'' ) ]
		test.assertEqual ( evts, [
			b'baz',
		] )
		with test.assertRaises ( base_proto.Closed ):
			list ( tp.receive ( b'' ) )
		
		tp = TestProtocol ( False )
		with test.assertRaises ( base_proto.ProtocolError ):
			list ( tp.receive ( b'X' * tp._MAXLINE ) )
		
		if True:
			class ClientProtocol ( base_proto.ClientProtocol ):
				pass
			cp = ClientProtocol ( False )
			class InvalidRequest ( base_proto.BaseRequest ):
				def _client_protocol ( self, client: base_proto.ClientProtocol ) -> base_proto.RequestProtocolGenerator:
					log = logger.getChild ( 'InvalidRequest._client_protocol' )
					log.debug ( 'yielding' )
					yield from () # this will trigger internal protocol error below
					log.debug ( 'returning' )
				def _server_protocol ( self, server: base_proto.ServerProtocol, prefix: str, suffix: str ) -> base_proto.RequestProtocolGenerator:
					yield from ()
			cp.request = ir = InvalidRequest()
			cp.request_protocol = ir._client_protocol ( cp )
			with test.assertRaises ( base_proto.Closed ):
				try:
					logger.debug ( 'calling _run_protocol()' )
					with quiet_logging():
						list ( cp._run_protocol() )
					logger.debug ( 'back from _run_protocol()' )
				except base_proto.Closed as e:
					test.assertEqual ( repr ( e ), "Closed('INTERNAL ERROR - CLIENT PROTOCOLS MUST THROW THEIR RESPONSE')" )
					raise
		
		class BadProtocol ( base_proto.Protocol ):
			def _receive_line ( self, line: bytes ) -> Iterator[base_proto.Event]:
				return super()._receive_line ( line )
		bp = BadProtocol ( False )
		with self.assertRaises ( NotImplementedError ):
			bp._receive_line ( b'' )
		
		class ServerProtocol ( base_proto.ServerProtocol ):
			def _parse_request_line ( self, line: BYTES ) -> Tuple[str,Opt[Type[base_proto.BaseRequest]],str]:
				return super()._parse_request_line ( line )
			
			def _error_invalid_command ( self ) -> base_proto.Event:
				return super()._error_invalid_command()
			
			def _error_tls_required ( self ) -> base_proto.Event:
				return super()._error_tls_required()
			
			def _error_tls_excluded ( self ) -> base_proto.Event:
				return super()._error_tls_excluded()
			
		sp = ServerProtocol ( False, 'localhost' )
		self.assertEqual ( [], list ( sp.startup() ) )
		with self.assertRaises ( NotImplementedError ):
			sp._parse_request_line ( b'' )
		with self.assertRaises ( NotImplementedError ):
			sp._error_invalid_command()
		with self.assertRaises ( NotImplementedError ):
			sp._error_tls_required()
		with self.assertRaises ( NotImplementedError ):
			sp._error_tls_excluded()

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
