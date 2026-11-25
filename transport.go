package cronet

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/textproto"
	"os"
	"runtime"
	"slices"
	"strconv"
	"strings"
	"sync"
)

var asyncExecutor Executor
var syncExecutor Executor

func init() {
	asyncExecutor = NewExecutor(func(executor Executor, command Runnable) {
		go func() {
			command.Run()
			command.Destroy()
		}()
	})
	syncExecutor = NewExecutor(func(executor Executor, command Runnable) {
		command.Run()
		command.Destroy()
	})
	runtime.SetFinalizer(&asyncExecutor, (*Executor).Destroy)
	runtime.SetFinalizer(&syncExecutor, (*Executor).Destroy)
}

// RoundTripper is a wrapper from URLRequest to http.RoundTripper
type RoundTripper struct {
	FollowRedirect bool
	Engine         Engine
	closeEngine    bool
}

func NewCronetTransport(params EngineParams, FollowRedirect bool) *RoundTripper {
	t := &RoundTripper{
		FollowRedirect: FollowRedirect,
	}
	t.Engine = NewEngine()
	t.Engine.StartWithParams(params)
	params.Destroy()
	t.closeEngine = true
	runtime.SetFinalizer(t, (*RoundTripper).Close)
	return t
}

func NewCronetTransportWithDefaultParams() *RoundTripper {
	engineParams := NewEngineParams()
	engineParams.SetEnableHTTP2(true)
	engineParams.SetEnableQuic(true)
	engineParams.SetEnableBrotli(true)
	engineParams.SetUserAgent("Go-cronet-http-client")
	return NewCronetTransport(engineParams, true)
}

func (t *RoundTripper) Close() error {
	if t.closeEngine {
		result := t.Engine.Shutdown()
		if result != ResultSuccess {
			return errors.New("engine still has active requests, so couldn't shutdown")
		}
		t.Engine.Destroy()
		t.closeEngine = false
	}
	return nil
}

func (t *RoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	requestParams := NewURLRequestParams()
	defer requestParams.Destroy()

	requestParams.SetPriority(URLRequestParamsRequestPriorityHighest)
	if request.Method == "" {
		requestParams.SetMethod("GET")
	} else {
		requestParams.SetMethod(request.Method)
	}
	for key, values := range request.Header {
		for _, value := range values {
			header := NewHTTPHeader()
			header.SetName(key)
			header.SetValue(value)
			requestParams.AddHeader(header)
			header.Destroy()

		}
	}
	if request.Body != nil {
		length := request.ContentLength
		if length == 0 && request.Body != http.NoBody {
			length = -1
		}
		uploadProvider := NewUploadDataProvider(&bodyUploadProvider{request.Body, request.GetBody, length})
		requestParams.SetUploadDataProvider(uploadProvider)
		requestParams.SetUploadDataExecutor(syncExecutor)
	}
	responseHandler := urlResponse{
		FollowRedirect: t.FollowRedirect,
		response: http.Response{
			Request:    request,
			Proto:      request.Proto,
			ProtoMajor: request.ProtoMajor,
			ProtoMinor: request.ProtoMinor,
			Header:     make(http.Header),
		},
		ready:  make(chan struct{}),
		read:   make(chan []byte, 1),
		cancel: make(chan struct{}),
		done:   make(chan struct{}),
	}
	responseHandler.response.Body = &responseHandler

	callback := NewURLRequestCallback(&responseHandler)
	urlRequest := NewURLRequest()
	responseHandler.request = urlRequest
	responseHandler.callback = callback
	cronetResult := urlRequest.InitWithParams(t.Engine, request.URL.String(), requestParams, callback, asyncExecutor)
	if cronetResult != ResultSuccess {
		urlRequest.Destroy()
		callback.Destroy()
		return nil, errors.New("failed to init request, cronet_result_code : " + strconv.Itoa(int(cronetResult)))
	}
	cronetResult = urlRequest.Start()
	if cronetResult != ResultSuccess {
		urlRequest.Destroy()
		callback.Destroy()
		return nil, errors.New("failed to start request, cronet_result_code : " + strconv.Itoa(int(cronetResult)))
	}
	go responseHandler.monitorContext(request.Context())
	<-responseHandler.ready
	responseHandler.access.Lock()
	defer responseHandler.access.Unlock()
	if responseHandler.response.StatusCode == 0 {
		return nil, responseHandler.err
	}
	return &responseHandler.response, nil
}

type urlResponse struct {
	FollowRedirect bool

	ready     chan struct{}
	readyOnce sync.Once
	callback  URLRequestCallback
	request   URLRequest
	response  http.Response
	err       error

	access sync.Mutex
	read   chan []byte
	cancel chan struct{}
	done   chan struct{}
}

func (r *urlResponse) monitorContext(ctx context.Context) {
	if ctx.Done() == nil {
		return
	}
	select {
	case <-r.cancel:
	case <-r.done:
	case <-ctx.Done():
		r.access.Lock()
		r.err = ctx.Err()
		r.access.Unlock()
		r.Close()
	}
}

func (r *urlResponse) Read(p []byte) (n int, err error) {
	if len(p) == 0 {
		return 0, nil
	}
	r.access.Lock()
	select {
	case <-r.done:
		err = r.err
		r.access.Unlock()
		return 0, err
	case <-r.cancel:
		r.access.Unlock()
		return 0, net.ErrClosed
	default:
	}
	buffer := NewBuffer()
	// Native asynchronous reads must not retain an unpinned Go byte slice.
	buffer.InitWithAlloc(int64(len(p)))
	// A successful Read transfers ownership to Cronet. It returns the buffer
	// through OnReadCompleted, or frees it itself on EOF, error or cancellation.
	result := r.request.Read(buffer)
	if result != ResultSuccess {
		buffer.Destroy()
		r.access.Unlock()
		return 0, errors.New("failed to read body, cronet_result_code : " + strconv.Itoa(int(result)))
	}
	r.access.Unlock()
	select {
	case data := <-r.read:
		if len(data) == 0 {
			return 0, io.EOF
		}
		return copy(p, data), nil
	case <-r.cancel:
		return 0, net.ErrClosed
	case <-r.done:
		// A terminal callback may follow the last completed read immediately.
		select {
		case data := <-r.read:
			if len(data) != 0 {
				return copy(p, data), nil
			}
		default:
		}
		r.access.Lock()
		err = r.err
		r.access.Unlock()
		return 0, err
	}
}

func (r *urlResponse) Close() error {
	r.access.Lock()
	defer r.access.Unlock()
	select {
	case <-r.cancel:
		return os.ErrClosed
	case <-r.done:
		return nil
	default:
		close(r.cancel)
		r.request.Cancel()
	}
	return nil
}

// Cronet automatically decompresses body content if one of these encodings is used
var cronetEncodings = []string{"br", "deflate", "gzip", "x-gzip", "zstd"}

func (r *urlResponse) OnRedirectReceived(self URLRequestCallback, request URLRequest, info URLResponseInfo, newLocationUrl string) {
	r.access.Lock()
	defer r.access.Unlock()
	if r.FollowRedirect {
		request.FollowRedirect()
		return
	}
	// No need to let cronet follow further redirect after first HTTP response
	r.response.Status = strconv.Itoa(info.StatusCode()) + " " + info.StatusText()
	r.response.StatusCode = info.StatusCode()
	headerLen := info.HeaderSize()
	for i := 0; i < headerLen; i++ {
		header := info.HeaderAt(i)
		r.response.Header.Add(header.Name(), header.Value())
	}
	r.response.Body = io.NopCloser(io.MultiReader())
	request.Cancel()
	r.readyOnce.Do(func() { close(r.ready) })
}

func (r *urlResponse) OnResponseStarted(self URLRequestCallback, request URLRequest, info URLResponseInfo) {
	r.access.Lock()
	defer r.access.Unlock()
	r.response.Status = strconv.Itoa(info.StatusCode()) + " " + info.StatusText()
	r.response.StatusCode = info.StatusCode()
	headerLen := info.HeaderSize()

	resetContentLength := false
	for i := 0; i < headerLen; i++ {
		header := info.HeaderAt(i)
		// Drop Content-Encoding header if body has been decompressed already
		// and reset Content-Length to unknown after loop completes
		if textproto.CanonicalMIMEHeaderKey(header.Name()) == "Content-Encoding" &&
			slices.Contains(cronetEncodings, strings.ToLower(header.Value())) {
			resetContentLength = true
			continue
		}
		r.response.Header.Add(header.Name(), header.Value())
	}
	if resetContentLength {
		r.response.Uncompressed = true
		r.response.ContentLength = -1
		r.response.Header.Del("Content-Length")
	} else {
		r.response.ContentLength = -1
		if value := r.response.Header.Get("Content-Length"); value != "" {
			r.response.ContentLength, _ = strconv.ParseInt(value, 10, 64)
		}
	}
	protocol := info.NegotiatedProtocol()
	r.response.Proto, r.response.ProtoMajor, r.response.ProtoMinor = "HTTP/1.1", 1, 1
	if protocol == "h2" {
		r.response.Proto, r.response.ProtoMajor, r.response.ProtoMinor = "HTTP/2.0", 2, 0
	} else if strings.HasPrefix(protocol, "h3") || strings.Contains(protocol, "quic") {
		r.response.Proto, r.response.ProtoMajor, r.response.ProtoMinor = "HTTP/3.0", 3, 0
	}
	r.response.TransferEncoding = r.response.Header.Values("Transfer-Encoding")
	r.response.Close = true
	r.readyOnce.Do(func() { close(r.ready) })
}

func (r *urlResponse) OnReadCompleted(self URLRequestCallback, request URLRequest, info URLResponseInfo, buffer Buffer, bytesRead int64) {
	defer buffer.Destroy()
	r.access.Lock()
	defer r.access.Unlock()
	data := append([]byte(nil), buffer.DataSlice()[:int(bytesRead)]...)
	select {
	case <-r.cancel:
	case <-r.done:
	case r.read <- data:
	}
}

func (r *urlResponse) OnSucceeded(self URLRequestCallback, request URLRequest, info URLResponseInfo) {
	r.close(request, io.EOF)
}

func (r *urlResponse) OnFailed(self URLRequestCallback, request URLRequest, info URLResponseInfo, error Error) {
	r.close(request, ErrorFromError(error))
}

func (r *urlResponse) OnCanceled(self URLRequestCallback, request URLRequest, info URLResponseInfo) {
	r.close(request, context.Canceled)
}

func (r *urlResponse) close(request URLRequest, err error) {
	r.access.Lock()
	defer r.access.Unlock()

	select {
	case <-r.done:
		return
	default:
	}

	if r.err == nil {
		r.err = err
	}

	close(r.done)
	r.readyOnce.Do(func() { close(r.ready) })
	request.Destroy()
	r.callback.Destroy()
}

type bodyUploadProvider struct {
	body          io.ReadCloser
	getBody       func() (io.ReadCloser, error)
	contentLength int64
}

func (p *bodyUploadProvider) Length(self UploadDataProvider) int64 {
	return p.contentLength
}

func (p *bodyUploadProvider) Read(self UploadDataProvider, sink UploadDataSink, buffer Buffer) {
	n, err := p.body.Read(buffer.DataSlice())
	if err != nil {
		if err == io.EOF {
			if p.contentLength == -1 {
				// Case for chunked uploads
				sink.OnReadSucceeded(int64(n), true)
			} else {
				sink.OnReadSucceeded(int64(n), false)
			}
			return
		}
		sink.OnReadError(err.Error())
	} else {
		sink.OnReadSucceeded(int64(n), false)
	}
}

func (p *bodyUploadProvider) Rewind(self UploadDataProvider, sink UploadDataSink) {
	if p.getBody == nil {
		sink.OnRewindError("unsupported")
		return
	}
	p.body.Close()
	newBody, err := p.getBody()
	if err != nil {
		sink.OnRewindError(err.Error())
		return
	}
	p.body = newBody
	sink.OnRewindSucceeded()
}

func (p *bodyUploadProvider) Close(self UploadDataProvider) {
	self.Destroy()
	p.body.Close()
}
