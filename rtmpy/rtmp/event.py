# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Channel type declarations.

@since: 0.1
"""

from twisted.internet import defer, threads
from zope.interface import implements
import pyamf

from rtmpy.util import BufferedByteStream
from rtmpy.rtmp import interfaces


#: Changes the frame size for events
FRAME_SIZE = 0x01
# 0x02 is unknown
#: Send every x bytes read by both sides
BYTES_READ = 0x03
#: A stream control message, has subtypes
CONTROL = 0x04
#: The servers downstream bandwidth
DOWNSTREAM_BANDWIDTH = 0x05
#: The clients upstream bandwidth
UPSTREAM_BANDWIDTH = 0x06
#: Packet containing audio
AUDIO_DATA = 0x07
#: Packet containing video data
VIDEO_DATA = 0x08
# 0x0a - 0x0e is unknown
#: Shared object with variable length
FLEX_SHARED_OBJECT = 0x10
#: Shared message with variable length
FLEX_MESSAGE = 0x11
#: An invoke which does not expect a reply
NOTIFY = 0x12
#: Has subtypes
SHARED_OBJECT = 0x13
#: Like remoting call, used for stream actions too
INVOKE = 0x14
# 0x15 anyone?
#: FLV data
FLV_DATA = 0x16


class BaseError(Exception):
    """
    Base error class for all things C{event}.
    """


class DecodeError(BaseError):
    """
    Base error class for decoding RTMP events.
    """


class TrailingDataError(DecodeError):
    """
    Raised if decoding an event does not consume the whole buffer.
    """


class EncodeError(BaseError):
    """
    Base error class for encoding RTMP events.
    """


class UnknownEventType(BaseError):
    """
    Raised if an unknown event type is found.
    """


class BaseEvent(object):
    """
    An abstract class that all event types extend.
    """

    implements(interfaces.IEvent)

    def encode(self, buf):
        raise NotImplementedError()

    def decode(self, buf):
        raise NotImplementedError()

    def dispatch(self, listener):
        raise NotImplementedError()


class FrameSize(BaseEvent):
    """
    A frame size event. This determines the number of bytes for the frame
    body in the RTMP stream.

    @ivar size: Number of bytes for RTMP frame bodies.
    @type size: C{int}
    """

    def __init__(self, size=None):
        self.size = size

    def decode(self, buf):
        """
        Decode a frame size event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        """
        self.size = buf.read_ulong()

    def encode(self, buf):
        """
        Encode a frame size event.

        @param buf: Receives the encoded data.
        @type buf: L{BufferedByteStream}
        @raise EncodeError: Frame size not set or wrong type.
        """
        if self.size is None:
            raise EncodeError('Frame size not set')

        try:
            buf.write_ulong(self.size)
        except TypeError:
            raise EncodeError('Frame size wrong type '
                '(expected int, got %r)' % (type(self.size),))

    def dispatch(self, listener):
        """
        Dispatches an 'onFrameSize' event to the listener.

        @param listener: The listener to frame size events.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onFrameSize(self.size)


class BytesRead(BaseEvent):
    """
    A bytes read event.

    @param bytes: The number of bytes read.
    @type bytes: C{int}
    """

    def __init__(self, bytes=None):
        self.bytes = bytes

    def decode(self, buf):
        """
        Decode a bytes read event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        """
        self.bytes = buf.read_ulong()

    def encode(self, buf):
        """
        Encode a bytes read event.

        @param buf: Receives the encoded data.
        @type buf: L{BufferedByteStream}
        @raise EncodeError: Bytes read not set or wrong type.
        """
        if self.bytes is None:
            raise EncodeError('Bytes read not set')

        try:
            buf.write_ulong(self.bytes)
        except TypeError:
            raise EncodeError('Bytes read wrong type '
                '(expected int, got %r)' % (type(self.bytes),))

    def dispatch(self, listener):
        """
        Dispatches an 'onBytesRead' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onBytesRead(self.bytes)


class ControlEvent(BaseEvent):
    """
    A control event. Akin to Red5's Ping Event.
    """

    UNDEFINED = -1
    PING = 6
    PONG = 7

    def __init__(self, type=None, value1=0, value2=UNDEFINED, value3=UNDEFINED):
        self.type = type
        self.value1 = value1
        self.value2 = value2
        self.value3 = value3

    def __repr__(self):
        return '<%s type=%r value1=%r value2=%r value3=%r at 0x%x>' % (
            self.__class__.__name__, self.type, self.value1, self.value2,
            self.value3, id(self))

    def decode(self, buf):
        """
        Decode a control message event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        """
        self.type = buf.read_short()
        self.value1 = buf.read_long()
        self.value2 = buf.read_long()
        self.value3 = buf.read_long()

    def encode(self, buf):
        """
        Encode a control message event.

        @param buf: Receives the encoded data.
        @type buf: L{BufferedByteStream}
        @raise EncodeError: Type not set or unexpected type.
        """
        if self.type is None:
            raise EncodeError('Type not set')

        try:
            buf.write_short(self.type)
        except TypeError:
            raise EncodeError('TypeError encoding type '
                '(expected int, got %r)' % (type(self.type),))

        try:
            buf.write_long(self.value1)
        except TypeError:
            raise EncodeError('TypeError encoding value1 '
                '(expected int, got %r)' % (type(self.value1),))

        try:
            buf.write_long(self.value2)
        except TypeError:
            raise EncodeError('TypeError encoding value2 '
                '(expected int, got %r)' % (type(self.value2),))

        try:
            buf.write_long(self.value3)
        except TypeError:
            raise EncodeError('TypeError encoding value3 '
                '(expected int, got %r)' % (type(self.value3),))

    def dispatch(self, listener):
        """
        Dispatches an 'onControlMessage' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onControlMessage(self)


class DownstreamBandwidth(BaseEvent):
    """
    A downstream bandwidth event.
    """

    def __init__(self, bandwidth=None):
        self.bandwidth = bandwidth

    def decode(self, buf):
        """
        Decode a downstream bandwidth event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        """
        self.bandwidth = buf.read_ulong()

    def encode(self, buf):
        """
        Encode a downstream bandwidth event.

        @param buf: Receives the encoded data.
        @type buf: L{BufferedByteStream}
        @raise EncodeError: Downstream bandwidth not set.
        @raise EncodeError: C{TypeError} for downstream bandwidth.
        """
        if self.bandwidth is None:
            raise EncodeError('Downstream bandwidth not set')

        try:
            buf.write_ulong(self.bandwidth)
        except TypeError:
            raise EncodeError('TypeError for downstream bandwidth '
                '(expected int, got %r)' % (type(self.bandwidth),))

    def dispatch(self, listener):
        """
        Dispatches an 'onDownstreamBandwidth' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onDownstreamBandwidth(self.bandwidth)


class UpstreamBandwidth(BaseEvent):
    """
    An upstream bandwidth event.

    @param bandwidth: The upstream bandwidth available.
    @type bandwidth: C{int}
    @param extra: Not sure what this is supposed to represent at the moment.
    """

    def __init__(self, bandwidth=None, extra=None):
        self.bandwidth = bandwidth
        self.extra = extra

    def decode(self, buf):
        """
        Decode an upstream bandwidth event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        """
        self.bandwidth = buf.read_ulong()
        self.extra = buf.read_uchar()

    def encode(self, buf):
        """
        Encode an upstream bandwidth event.

        @param buf: Receives the encoded data.
        @type buf: L{BufferedByteStream}
        @raise EncodeError: Upstream bandwidth or L{extra} not set.
        @raise EncodeError: C{TypeError} for upstream bandwidth or
            L{extra}.
        """
        if self.bandwidth is None:
            raise EncodeError('Upstream bandwidth not set')

        if self.extra is None:
            raise EncodeError('Extra not set')

        try:
            buf.write_ulong(self.bandwidth)
        except TypeError:
            raise EncodeError('TypeError: Upstream bandwidth '
                '(expected int, got %r)' % (type(self.bandwidth),))

        try:
            buf.write_uchar(self.extra)
        except TypeError:
            raise EncodeError('TypeError: extra '
                '(expected int, got %r)' % (type(self.extra),))

    def dispatch(self, listener):
        """
        Dispatches an 'onUpstreamBandwidth' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onUpstreamBandwidth(self.bandwidth, self.extra)


class Notify(BaseEvent):
    """
    A notification event.

    @param name: The method name to call.
    @type name: C{str}
    @param id: The global identifier (per connection) for the call.
    @type id: C{int}
    @param argv: A list of elements to represent the method arguments.
    """

    def __init__(self, name=None, id=None, *args):
        self.name = name
        self.id = id
        self.argv = list(args)

    def __repr__(self):
        return '<%s name=%r id=%r argv=%r at 0x%x>' % (
            self.__class__.__name__, self.name, self.id, self.argv, id(self))

    def decode(self, buf, encoding=pyamf.AMF0):
        """
        Decode a notification event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        @param encoding: The AMF encoding type. Defaults to AMF0.
        @return: A L{defer.Deferred} that will `callback` when the decoding is
            finished.
        @rtype: L{defer.Deferred}
        """
        def _decode():
            decoder = pyamf.get_decoder(encoding)
            decoder.stream = buf

            for a in ['name', 'id']:
                setattr(self, a, decoder.readElement())

            self.argv = []

            while not buf.at_eof():
                self.argv.append(decoder.readElement())

        return threads.deferToThread(_decode)

    def encode(self, buf, encoding=pyamf.AMF0):
        """
        Encode a notification event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        @param encoding: The AMF encoding type. Defaults to AMF0.
        @return: A L{defer.Deferred} that will `callback` when the encoding is
            finished.
        @rtype: L{defer.Deferred}
        """
        def _encode():
            encoder = pyamf.get_encoder(encoding)
            encoder.stream = buf

            for e in [self.name, self.id]:
                encoder.writeElement(e)

            for e in self.argv:
                encoder.writeElement(e)

        return threads.deferToThread(_encode)

    def dispatch(self, listener):
        """
        Dispatches an 'onNotify' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onNotify(self)


class Invoke(Notify):
    """
    Similar to L{Notify} but a reply is expected.
    """

    def dispatch(self, listener):
        """
        Dispatches an 'onInvoke' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onInvoke(self)


class BaseStreamingEvent(BaseEvent):
    """
    An event containing streaming data.

    @param data: The raw audio data.
    @type data: C{str}
    """

    implements(interfaces.IStreamable)

    def __init__(self, data=None):
        self.data = data

    def decode(self, buf):
        """
        Decode a streaming event.

        @param buf: Contains the encoded data.
        @type buf: L{BufferedByteStream}
        """
        self.data = buf.read()

    def encode(self, buf):
        """
        Encode a streaming event.

        @param buf: Receives the encoded data.
        @type buf: L{BufferedByteStream}
        @raise EncodeError: No L{data} set or C{TypeError} for L{data}.
        """
        if self.data is None:
            raise EncodeError('No data set')

        try:
            buf.write(self.data)
        except TypeError:
            raise EncodeError('TypeError: data (expected str, got %r)' % (
                type(self.data),))


class AudioData(BaseStreamingEvent):
    """
    A event containing audio data.
    """

    def dispatch(self, listener):
        """
        Dispatches an 'onAudioData' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onAudioData(self.data)


class VideoData(BaseStreamingEvent):
    """
    A event containing video data.
    """

    def dispatch(self, listener):
        """
        Dispatches an 'onVideoData' event to the listener.

        @param listener: The event listener.
        @type listener: L{interfaces.IEventListener}
        """
        return listener.onVideoData(self.data)

#: Type map.
TYPE_MAP = {
    FRAME_SIZE: FrameSize,
    BYTES_READ: BytesRead,
    CONTROL: ControlEvent,
    DOWNSTREAM_BANDWIDTH: DownstreamBandwidth,
    UPSTREAM_BANDWIDTH: UpstreamBandwidth,
    NOTIFY: Notify,
    INVOKE: Invoke,
    AUDIO_DATA: AudioData,
    VIDEO_DATA: VideoData,
    # TODO: Shared object etc.
}


def decode(datatype, body, *args, **kwargs):
    """
    A helper method that decodes a byte stream to an L{interfaces.IEvent}
    instance.

    @param datatype: The type of the event.
    @type datatype: C{int}
    @param body: The byte string holding the encoded form of the event.
    @type body: C{str}
    @return: A deferred, whose callback will return the event instance.
    @rtype: L{defer.Deferred} that contains a {interfaces.IEvent} instance
        corresponding to C{datatype}
    @raise DecodeError: The datatype is not known.
    @raise TrailingDataError: Raised if the body was not completely decoded.
    @note: This function doesn't actually raise the exceptions, they are
        wrapped by the L{defer.Deferred}.
    """
    def _decode():
        try:
            event = TYPE_MAP[datatype]()
        except KeyError:
            raise DecodeError('Unknown datatype \'%r\'' % (datatype,))

        buf = BufferedByteStream(body)

        def cb(res):
            # check here to ensure the whole buffer has been consumed
            if not buf.at_eof():
                raise TrailingDataError()

            return event

        d = defer.maybeDeferred(event.decode, buf, *args, **kwargs)

        return d.addCallback(cb)

    return defer.maybeDeferred(_decode)


def encode(event, *args, **kwargs):
    """
    A helper method that encodes an event.

    @param event: The event to be encoded.
    @type event: L{interfaces.IEvent}
    @return: A deferred, whose callback will return a tuple, the event
        datatype and the encoded event byte string.
    @rtype: L{defer.Deferred} that contains a tuple (C{int}, C{str})
    @raise EncodeError: If the event class does not correspond to a registered
        type.
    @raise TypeError: The event does not implement L{interfaces.IEvent}
    @note: This function doesn't actually raise the exceptions, they are
        wrapped by the L{defer.Deferred}.
    """
    def _encode():
        if not interfaces.IEvent.providedBy(event):
            raise TypeError('Expected an event interface (got:%r)' % (
                type(event),))

        datatype = None
        kls = event.__class__

        for t, c in TYPE_MAP.iteritems():
            if c is kls:
                datatype = t

                break

        if datatype is None:
            raise UnknownEventType('Unknown event type for %r' % (event,))

        body = BufferedByteStream()

        def cb(res):
            return datatype, body.getvalue()

        d = defer.maybeDeferred(event.encode, body, *args, **kwargs)

        return d.addCallback(cb)

    return defer.maybeDeferred(_encode)


def get_type_class(datatype):
    """
    A helper method that returns the mapped event class to the supplied
    datatype.

    @param datatype: The event type
    @type datatype: C{int}
    @return: The event class that is mapped to C{datatype}.
    @rtype: C{class} implementing L{interfaces.IEvent}
    @raise UnknownEventType: Unknown event type for C{datatype}.
    """
    try:
        return TYPE_MAP[datatype]
    except KeyError:
        raise UnknownEventType('Unknown event type %r' % (datatype,))