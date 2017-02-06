"""
.. module:: munin
   :platform: Any
   :synopsis: Provides MuninNode source which can get events from the
              munin-node protocol.

.. moduleauthor:: Colin Alston <colin@imcol.in>
"""
from twisted.internet import defer, reactor
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ClientCreator

from zope.interface import implementer

from duct.interfaces import IDuctSource
from duct.objects import Source
from duct.aggregators import Counter, Counter32

class MuninProtocol(LineReceiver):
    """MuninProtocol - provides a line receiver protocol for making requests
    to munin-node

    Requests must be made sequentially
    """
    delimiter = '\n'
    def __init__(self):
        self.ready = False
        self.buf = []
        self.d = None
        self.clist = None

    def lineReceived(self, line):
        if line.startswith('#'):
            return

        if self.d and (not self.d.called):
            if self.clist:
                if line == '.':
                    buf = self.buf
                    self.buf = []
                    self.d.callback(buf)
                else:
                    self.buf.append(line)
            else:
                self.d.callback(line)

    def disconnect(self):
        """Disconnect from transport
        """
        return self.transport.loseConnection()

    def sendCommand(self, command, clist=False):
        """Send command to munin
        """
        self.d = defer.Deferred()
        self.clist = clist
        self.sendLine(command)
        return self.d


@implementer(IDuctSource)
class MuninNode(Source):
    """Connects to munin-node and retrieves all metrics

    **Configuration arguments:**

    :param host: munin-node hostname (probably localhost)
    :type host: str.
    :param port: munin-node port (probably 4949)
    :type port: int.

    **Metrics:**

    :(service name).(plugin name).(keys...): A dot separated tree of
                                             munin plugin keys
    """

    def _connect_munin(self):
        host = self.config.get('host', 'localhost')
        port = int(self.config.get('port', 4949))

        creator = ClientCreator(reactor, MuninProtocol)
        return creator.connectTCP(host, port)

    @defer.inlineCallbacks
    def get(self):
        proto = yield self._connect_munin()

        # Announce our capabilities
        yield proto.sendCommand('cap multigraph')

        listout = yield proto.sendCommand('list')
        plug_list = listout.split()
        events = []

        for plug in plug_list:
            # Retrive the configuration for this plugin
            config = yield proto.sendCommand('config %s' % plug, True)
            plugin_config = {}
            for r in config:
                name, val = r.split(' ', 1)
                if '.' in name:
                    metric, key = name.split('.')

                    if key in ['type', 'label', 'min', 'info']:
                        plugin_config['%s.%s.%s' % (plug, metric, key)] = val

                else:
                    if name == 'graph_category':
                        plugin_config['%s.category' % plug] = val

            category = plugin_config.get('%s.category' % plug, 'system')

            # Retrieve the metrics
            metrics = yield proto.sendCommand('fetch %s' % plug, True)
            for m in metrics:
                name, val = m.split(' ', 1)
                if name != 'multigraph':
                    metric, key = name.split('.')
                    base = '%s.%s' % (plug, metric)
                    m_type = plugin_config.get('%s.type' % base, 'GAUGE')

                    try:
                        val = float(val)
                    except:
                        continue

                    base = '%s.%s' % (plug, metric)
                    info = plugin_config.get('%s.info' % base, base)
                    prefix = '%s.%s' % (category, base)

                    if m_type == 'COUNTER':
                        events.append(self.createEvent('ok', info, val,
                                                       prefix=prefix,
                                                       aggregation=Counter32))
                    elif m_type == 'DERIVE':
                        events.append(self.createEvent('ok', info, val,
                                                       prefix=prefix,
                                                       aggregation=Counter))
                    else:
                        events.append(self.createEvent('ok', info, val,
                                                       prefix=prefix))

        yield proto.disconnect()

        defer.returnValue(events)
