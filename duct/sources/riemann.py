"""
.. module:: riemann
   :platform: Unix
   :synopsis: A source module which provides Riemann servers

.. moduleauthor:: Colin Alston <colin@imcol.in>
"""
from twisted.internet import reactor
from twisted.internet.protocol import Factory

from zope.interface import implementer

from duct.interfaces import IDuctSource
from duct.objects import Source, Event

from duct.protocol import riemann


class RiemannTCPServer(riemann.RiemannProtocol):
    """
    Server implementation of the Riemann protocol
    """
    def __init__(self, source):
        riemann.RiemannProtocol.__init__(self)
        self.source = source

    def stringReceived(self, string):
        message = self.decodeMessage(string)

        for event in message.events:
            self.source.queueBack(
                Event(
                    event.state,
                    event.service,
                    event.description,
                    event.metric_f,
                    event.ttl,
                    hostname=event.host,
                    evtime=event.time
                )
            )

class RiemannTCPFactory(Factory):
    """TCP Factory for Riemann
    """
    def __init__(self, source):
        self.source = source

    def buildProtocol(self, addr):
        return RiemannTCPServer(self.source)

@implementer(IDuctSource)
class RiemannTCP(Source):
    """Provides a listening server which accepts Riemann metrics
    and proxies them to our queue.

    **Configuration arguments:**

    :param port: Port to listen on (default 5555)
    :type port: int.

    """
    def startTimer(self):
        """Creates a Riemann TCP server instead of a timer
        """
        reactor.listenTCP(int(self.config.get('port', 5555)),
                          RiemannTCPFactory(self))

    def get(self):
        pass
