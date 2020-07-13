# system imports:
import packaging

# email_proto imports:
import smtp_proto

__version__ = packaging.version.parse ( '0.1.0' )

'''
NOTE: the individual protocols aren't automatically imported here because
most users won't need/want all of them.

Import them directly instead:

import email_proto.smtp_socket

from email_proto import pop3_trio
'''
