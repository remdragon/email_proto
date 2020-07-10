import trustme # pip install trustme
import ssl

class ServerOnly:
	def __init__ ( self, *,
		server_hostname: str,
	) -> None:
		self.server_hostname = server_hostname
		self.ca = trustme.CA()
		self.server_cert = self.ca.issue_cert ( self.server_hostname )
	
	def server_context ( self ) -> ssl.SSLContext:
		ctx = ssl.create_default_context()
		ctx.check_hostname = False
		self.server_cert.configure_cert ( ctx )
		self.ca.configure_trust ( ctx )
		ctx.verify_mode = ssl.CERT_NONE
		return ctx
	
	def client_context ( self ) -> ssl.SSLContext:
		ctx = ssl.create_default_context()
		self.ca.configure_trust ( ctx )
		return ctx
