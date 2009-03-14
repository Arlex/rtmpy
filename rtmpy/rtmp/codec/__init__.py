# -*- test-case-name: rtmpy.tests.test_codec -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP codecs. Encoders and decoders for rtmp streams.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

from twisted.internet import task

from rtmpy import util
from rtmpy.rtmp import interfaces
from rtmpy.rtmp.codec import header


class BaseError(Exception):
    """
    Base class for codec errors.
    """


class DecodeError(BaseError):
    """
    Raised if there is an error decoding an RTMP bytestream.
    """


class EncodeError(BaseError):
    """
    Raised if there is an error encoding an RTMP bytestream.
    """


class BaseCodec(object):
    """
    @ivar deferred: The deferred from the result of L{getJob}.
    @type deferred: L{Deferred<twisted.internet.defer.Deferred>}
    @ivar job: A L{task.LoopingCall<twisted.internet.task.LoopingCall>}
        instance that is used to iteratively call the method supplied by
        L{getJob}.
    """

    def __init__(self, manager):
        if not interfaces.IChannelManager.providedBy(manager):
            raise TypeError('IChannelManager expected (got %s)' % (
                type(manager),))

        self.manager = manager
        self.deferred = None
        self.buffer = util.BufferedByteStream()

        self.job = task.LoopingCall(self.getJob())

    def __del__(self):
        if not hasattr(self, 'job'):
            return

        if self.job.running:
            self.job.stop()

    def getJob(self):
        """
        Returns the method to be iteratively called to process the codec.

        This method is intended to be implemented by sub-classes.
        """
        raise NotImplementedError()

    def start(self, when=0):
        """
        Starts or resumes the job. If the job is already running (i.e. not
        stopped) then this is a noop.

        @return: The deferred from starting the job.
        @rtype: L{twisted.internet.defer.Deferred}
        """
        if self.job.running:
            return self.deferred

        self.deferred = self.job.start(when, now=False)

        return self.deferred

    def pause(self):
        """
        Pauses the codec. Called when the buffer is exhausted. If the job is
        already stopped then this is a noop.
        """
        if self.job.running:
            self.job.stop()
            self.deferred = None


class Decoder(BaseCodec):
    """
    Decodes an RTMP stream. De-interlaces the channels and writes the frames
    to the individual buffers. The decoder has the power to pause itself, but
    not to start.

    @ivar currentChannel: The channel currently being decoded.
    @type currentChannel: L{interfaces.IChannel}
    """

    def __init__(self, manager):
        BaseCodec.__init__(self, manager)

        self.currentChannel = None

    def getJob(self):
        return self.decode

    def readHeader(self):
        """
        Reads an RTMP Header from the stream. If there is not enough data in
        the buffer then C{None} is returned.

        @rtype: L{interfaces.IHeader} or C{None}
        """
        headerPosition = self.buffer.tell()

        try:
            return header.decodeHeader(self.buffer)
        except EOFError:
            self.buffer.seek(headerPosition)

            return None

    def getBytesAvailableForChannel(self, channel):
        """
        Returns the number of bytes available in the buffer to be read as an
        RTMP stream.
        """
        return min(
            self.buffer.remaining(),
            channel.bodyRemaining,
            self.manager.frameSize
        )

    def readFrame(self):
        """
        This function attempts to read a frame from the stream. A frame is a
        set amount of data that borders header bytes. If a full frame was read
        from the buffer then L{currentChannel} is set to C{None}.

        After this function is finished, the next part of the buffer will
        either be empty or a header section.
        """
        if self.currentChannel is None:
            raise DecodeError('Channel is required to read frame')

        available = self.getBytesAvailableForChannel(self.currentChannel)
        frames = self.currentChannel.frames

        if available == 0:
            return

        self.currentChannel.write(self.buffer.read(available))

        if self.currentChannel.frames != frames:
            # a complete frame was read from the stream which means a new
            # header and frame body will be next in the stream
            self.currentChannel = None
        elif self.currentChannel.bodyRemaining == 0:
            self.currentChannel = None

    def canContinue(self, minBytes=1):
        """
        Checks to see if decoding can continue. If there are less bytes in the
        stream than C{minBytes} then the job is paused.

        @param minBytes: The minimum number of bytes required to continue
            decoding.
        @type minBytes: C{int}
        @rtype: C{bool}
        """
        remaining = self.buffer.remaining()

        if remaining < minBytes or remaining == 0:
            self.pause()

        return (remaining >= minBytes)

    def _decode(self):
        if self.currentChannel is not None:
            self.readFrame()

        if not self.canContinue():
            # the buffer is empty
            self.pause()

            return

        h = self.readHeader()

        if h is None:
            # not enough bytes left in the stream to continue decoding, we
            # require a complete header to decode
            self.pause()

            return

        self.currentChannel = self.manager.getChannel(h.channelId)
        self.currentChannel.setHeader(h)

        self.readFrame()

    def decode(self):
        """
        Attempt to decode the buffer. If a successful frame was decoded from
        the stream then the decoded bytes are removed.
        """
        if not self.canContinue():
            self.pause()

            return

        # start from the beginning of the buffer
        self.buffer.seek(0)

        self._decode()
        # delete the bytes that have already been decoded
        self.buffer.consume()

    def dataReceived(self, data):
        """
        Adds data to the end of the stream. 
        """
        self.buffer.seek(0, 2)
        self.buffer.write(data)


class ChannelContext(object):
    """
    Provides contextual meta data for each channel attached to L{Encoder}.

    @ivar buffer: Any data from the channel waiting to be encoded.
    @type buffer: L{util.BufferedByteStream}
    @ivar header: The last header that was written to the stream.
    @type header: L{interfaces.IHeader}
    @ivar channel: The underlying RTMP channel.
    @type channel: L{interfaces.IChannel}
    @ivar encoder: The RTMP encoder object.
    @type encoder: L{Encoder}
    @ivar active: Whether this channel is actively producing data.
    @type active: C{bool}
    """

    def __init__(self, channel, encoder):
        self.channel = channel
        self.encoder = encoder

        self.buffer = util.BufferedByteStream()
        self.active = False
        self.header = None

        self.channel.registerConsumer(self)

    def write(self, data):
        """
        Called by the channel when data becomes available.
        """
        self.buffer.append(data)

        if not self.active:
            self.encoder.activateChannel(self.channel)
            self.active = True

    def getData(self, length):
        """
        Called by the encoder to return any data that may be available in the
        buffer. If C{length} bytes cannot be retrieved then C{None} is
        returned. Once the data has been read from the stream, it is consumed.

        @param length: The length of data requested.
        @type length: C{int} or C{None}
        """
        pos = self.buffer.tell()

        try:
            data = self.buffer.read(length)
        except (EOFError, IOError):
            self.buffer.seek(pos)
            data = None

        if len(self.buffer) == 0 or data is None:
            self.encoder.deactivateChannel(self.channel)
            self.active = False
        else:
            self.buffer.consume()

        return data

    def getRelativeHeader(self):
        """
        Returns a header based on the last absolute header written to the
        stream and the channel's header. If there was no header written to the
        stream then the channel's header is returned.

        @rtype: L{interfaces.IHeader}
        """
        if self.header is None:
            return self.channel.getHeader()

        return header.diffHeaders(self.header, self.channel.getHeader())


class Encoder(BaseCodec):
    """
    Interlaces all active channels to form one stream. At this point no
    attempt has been made to prioritise other channels over others.

    @ivar channelContext: A C{dict} of {channel: L{ChannelContext}} objects.
    @type channelContext: C{dict}
    @ivar currentContext: A reference to the current context being encoded.
    @type currentContext: L{ChannelContext}
    @ivar scheduler: An RTMP channel scheduler. This composition allows
        different scheduler strategies without 'infecting' this class.
    @type scheduler: L{interfaces.IChannelScheduler}
    """

    def __init__(self, manager):
        BaseCodec.__init__(self, manager)

        self.channelContext = {}
        self.currentContext = None
        self.consumer = None
        self.scheduler = None

    def registerScheduler(self, scheduler):
        """
        Registers a RTMP channel scheduler for the encoder to use when
        determining which channel to encode next.

        @param scheduler: The scheduler to register.
        @type scheduler: L{IChannelScheduler}
        """
        if not interfaces.IChannelScheduler.providedBy(scheduler):
            raise TypeError('Expected IChannelScheduler interface')

        self.scheduler = scheduler

    def getJob(self):
        """
        @see L{BaseCodec.getJob}
        """
        return self.encode

    def registerConsumer(self, consumer):
        """
        Registers a consumer that will be the recipient of the encoded rtmp
        stream.
        """
        self.consumer = consumer

    def activateChannel(self, channel):
        """
        Flags a channel as actively producing data.

        @raise 
        """
        if not channel in self.channelContext:
            raise RuntimeError('Attempted to activate a non-existant channel')

        self.scheduler.activateChannel(channel)

    def deactivateChannel(self, channel):
        """
        """
        if not channel in self.channelContext:
            raise RuntimeError('Attempted to deactivate a non-existant ' + \
                'channel')

        self.scheduler.deactivateChannel(channel)

    def getMinimumFrameSize(self, channel):
        """
        Returns the minimum number of bytes required to complete a frame.

        @param channel: The channel to check.
        @type channel: L{interfaces.IChannel}
        @rtype: C{int}
        """
        available = min(channel.bodyRemaining, self.manager.frameSize)

        if available < 1:
            raise RuntimeError('%d bytes (< 1) are available for frame ' \
                '(channel:%d, manager:%d)' % (
                    available, channel.bodyRemaining, self.manager.frameSize))

        return available

    def writeFrame(self):
        """
        Writes an RTMP header and body to L{buffer}, based on the current
        context - if there is enough data available.
        """
        if self.currentContext is None:
            return

        context = self.currentContext
        channel = context.channel

        data = context.getData(self.getMinimumFrameSize(channel))

        if data is None:
            return

        relativeHeader = context.getRelativeHeader()
        context.header = channel.getHeader()

        header.encodeHeader(self.buffer, relativeHeader)
        self.buffer.write(data)

    def encode(self):
        """
        Called to encode an RTMP frame (header and body) and write the result
        to the C{consumer}. If there is nothing to do then L{pause} will be
        called.
        """
        channel = self.scheduler.getNextChannel()

        if channel is None:
            self.pause()

            return

        self.currentContext = self.channelContext[channel]
        self.writeFrame()

        if len(self.buffer) > 0:
            self.consumer.write(self.buffer.getvalue())

            self.buffer.truncate(0)