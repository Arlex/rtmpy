# -*- test-case-name: rtmpy.tests.test_client -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

from twisted.internet import reactor, protocol

from rtmpy import rtmp, util

class RTMPClientProtocol(rtmp.RTMPBaseProtocol):
    """
    Client RTMP Protocol.
    """

    def connectionMade(self):
        """
        Called when a connection has been made to this protocol instance. Used
        to do general setup and protocol initialisation
        """
        rtmp.RTMPBaseProtocol.connectionMade(self)

        # generate and send initial handshake
        self.my_handshake = rtmp.generate_handshake()

        self.transport.write(rtmp.HEADER_BYTE)
        self.transport.write(self.my_handshake)

    def decodeHandshake(self):
        """
        Negotiates the handshake phase of the protocol.

        @see L{http://osflash.org/documentation/rtmp#handshake} for more info.
        """
        buffer = self.buffer

        if len(buffer) < 1:
            # no data has been received yet
            return

        if buffer.read(1) != rtmp.HEADER_BYTE:
            self.dispatch(rtmp.HANDSHAKE_FAILURE, 'Invalid header byte received')

            return

        if len(buffer) < rtmp.HANDSHAKE_LENGTH * 2 + 1:
            # buffer is too small, wait for more data
            return

        self.received_handshake = buffer.read(rtmp.HANDSHAKE_LENGTH)

        if buffer.read(rtmp.HANDSHAKE_LENGTH) != self.my_handshake:
            self.dispatch(rtmp.HANDSHAKE_FAILURE, 'Handshake mismatch')

            return

        self._consumeBuffer()
        self.transport.write(self.received_handshake)
        self.dispatch(rtmp.HANDSHAKE_SUCCESS)

    def dataReceived(self, data):
        """
        Called when some data has been received from the underlying transport
        """
        self.buffer.seek(0, 2)
        self.buffer.write(data)
        self.buffer.seek(0)

        if self.state == rtmp.RTMPBaseProtocol.HANDSHAKE:
            self.decodeHandshake()
        elif self.state == rtmp.RTMPBaseProtocol.STREAM:
            rtmp.RTMPBaseProtocol.dataReceived(data)
        else:
            self.transport.loseConnection()

    def onHandshakeSuccess(self):
        rtmp.RTMPBaseProtocol.onHandshakeSuccess(self)

        # send invoke->connect here

class RTMPClientFactory(protocol.ClientFactory):
    """
    RTMP client protocol factory
    """

    protocol = RTMPClientProtocol