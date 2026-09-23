import unittest
from unittest.mock import Mock
import h2.events as events
from fi_mitm import MitmProxy

class H2CaptureTests(unittest.TestCase):
    def setUp(self):
        self.proxy=object.__new__(MitmProxy)
        self.output=[]
        self.proxy.on_event=self.output.append
        self.state={'connection':'test'}

    def capture(self,direction,event):
        self.proxy._capture_h2(self.state,5,direction,'example.test',event)
        return self.output[-1]

    def test_headers_split_body_and_trailers(self):
        request=self.capture('out',events.RequestReceived(stream_id=5,headers=[(':method','POST'),(':path','/rpc'),(':authority','example.test')]))
        self.assertEqual(request['url'],'https://example.test/rpc')
        self.capture('in',events.ResponseReceived(stream_id=5,headers=[(':status','202'),('content-type','application/json'),('x-test','yes')]))
        self.capture('in',events.DataReceived(stream_id=5,data=b'{"ok":',flow_controlled_length=6))
        body=self.capture('in',events.DataReceived(stream_id=5,data=b'true}',flow_controlled_length=5))
        trailer=self.capture('in',events.TrailersReceived(stream_id=5,headers=[('grpc-status','0')]))
        self.assertEqual(body['body'],'{"ok":true}')
        self.assertEqual(body['id'],trailer['id'])
        self.assertIn('x-test: yes',trailer['headers'])
        self.assertEqual(trailer['trailers'],'grpc-status: 0')
        self.assertIn('HTTP/2 202',trailer['data'])

    def test_binary_and_preview_limit(self):
        self.capture('in',events.ResponseReceived(stream_id=5,headers=[(':status','200'),('content-type','application/grpc')]))
        result=self.capture('in',events.DataReceived(stream_id=5,data=b'\x00'*70000,flow_controlled_length=70000))
        self.assertTrue(result['truncated'])
        self.assertEqual(result['size'],70000)
        self.assertEqual(len(self.state[(5,'in')]['body']),65536)
        self.assertIn('Binary body (hex',result['body'])

    def test_relay_and_completed_stream_cleanup(self):
        server,client=Mock(),Mock(); client.get_next_available_stream_id.return_value=1
        fwd,rev={},{}
        request=events.RequestReceived(stream_id=5,headers=[(':method','GET'),(':path','/')])
        self.proxy._h2_handle_event(request,server,client,None,None,fwd,rev,'example.test',False,self.state)
        client.send_headers.assert_called_once_with(1,request.headers,end_stream=None)
        response=events.ResponseReceived(stream_id=1,headers=[(':status','204')])
        self.proxy._h2_handle_event(response,server,client,None,None,fwd,rev,'example.test',True,self.state)
        server.send_headers.assert_called_once_with(5,response.headers,end_stream=None)
        self.proxy._h2_handle_event(events.StreamEnded(stream_id=1),server,client,None,None,fwd,rev,'example.test',True,self.state)
        self.assertEqual(self.state,{'connection':'test'})

if __name__=='__main__': unittest.main()
