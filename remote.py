import json, socket, sys, struct, threading, traceback, urllib2

# Server implementation of RemoteWorker

if len(sys.argv) < 2:
	print 'Usage: python remote.py secret [port [bindhost]]'
	sys.exit(1)

def thread(client, client_addr):
	"""Client thread"""
	s = ''
	while len(s) == 0 or s[len(s)-1] != '\n':
		s += client.recv(1024)
	try:
		req = json.loads(s)
	except:
		traceback.print_exc()
		return
	
	# Bad secret
	if 's' not in req or req['s'] != sys.argv[1]:
		print '[-] {0}:{1} => bad secret'.format(*client_addr)
		client.close()
		return
	
	# Get the URL
	try:
		data = urllib2.urlopen(req['u']).read()
		client.sendall(struct.pack('>HI', 200, len(data)) + data)
		print '[-] {1}:{2} => PASS {0}'.format(req['u'], *client_addr)
	except urllib2.HTTPError as e:
		# HTTP error, send it without any data
		client.sendall(struct.pack('>HI', e.code, 0))
		print '[-] {2}:{3} => H{0} {1}'.format(e.code, req['u'], *client_addr)
	except:
		# Other error, send it without any data
		client.sendall(struct.pack('>HI', 0, 0))
		print '[-] {1}:{2} => FAIL {0}'.format(req['u'], *client_addr)
		traceback.print_exc()
	client.close()

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((len(sys.argv) > 3 and sys.argv[3] or '', len(sys.argv) > 2 and int(sys.argv[2]) or 5397))
server.listen(5)

while True:
	t = threading.Thread(target=thread, args=server.accept())
	t.daemon = True
	t.start()
