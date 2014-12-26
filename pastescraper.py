# The Pastebin Scraper: est. 2014/12/13 20:41-0200
# Based on the work of: http://www.michielovertoom.com/python/pastebin-abused/

import BeautifulSoup, collections, datetime, json, os, Queue, random, sys, socket, struct, threading, time, traceback, urllib, urllib2
from config import *

logfile = open('pastescraper.log', 'w+')
def log(line):
	"""Quick and dirty logger"""
	print line
	logfile.write('[' + datetime.datetime.now().isoformat()[:19] + '] ' + line + '\n')
	logfile.flush()

THREADS = 5

class Worker:
	"""Base worker class, uses urllib2 locally to retrieve data"""
	def __init__(self):
		self.banned = False
		self.stop = False
	
	def get(self, url, text=False):
		"""Get the specified url. If text is True, the worker should watch out for data that doesn't look like a raw paste"""
		while True:
			try:
				return urllib2.urlopen(url).read()
			except urllib2.HTTPError as e:
				log(traceback.format_exc()) # DEBUG
				if e.code == 403:
					log('[!] Pastebin ban on local worker')
					# Wait 10 minutes
					self.banned = True
					time.sleep(600)
					self.banned = False
				else:
					return None
	
	def refresh(self):
		"""Refresh the worker. For a proxy worker, this should cycle to the next proxy"""
		pass
	
	def go_easy(self):
		"""Returns whether the rate limits should be applied to this worker"""
		return True

class ProxyWorker(Worker):
	"""Uses HTTP proxies loaded in host:port format from proxies.txt"""
	def __init__(self):
		Worker.__init__(self)
		self.proxies = None
		self.cur_proxy = None
		self.cur_proxy_addr = None
		self.tid = -1
	
	def proxy_filename(self):
		"""Filename to get proxies from"""
		return 'proxies.txt'
	
	def load_proxies(self):
		"""Load the list of proxies, shuffle it, then load it onto the queue"""
		ret = Queue.Queue()
		with open(self.proxy_filename()) as f:
			lines = [x.rstrip('\r\n') for x in f]
			random.shuffle(lines)
			for line in lines:
				ret.put(line)
			f.close()
		return ret
	
	def get(self, url, text=False):
		"""Use the self.cur_proxy opener to get the url"""
		if not self.cur_proxy: self.refresh()
		while True:
			try:
				resp = self.cur_proxy.open(url, timeout=10)
				content = resp.read()
				if text:
					if url in content:
						# There's no way a paste could include its own raw URL in the text, right?
						log('[!] Proxy {0} is blocking Pastebin (url in text)'.format(self.cur_proxy_addr))
						self.refresh()
					elif resp.headers.get('Content-Type')[:10] != 'text/plain':
						# HTML returned, this shouldn't happen
						log('[!] Proxy {0} is blocking Pastebin (not plain text)'.format(self.cur_proxy_addr))
						self.refresh()
				else:
					return content
			except urllib2.HTTPError as e:
				if e == 404:
					return None
				else:
					if e == 403: log('[!] Pastebin ban on proxy {0}'.format(self.cur_proxy_addr))
					self.refresh()
			except:
				self.refresh()
	
	def refresh(self):
		"""Cycle to the next proxy"""
		if not self.proxies or self.proxies.empty():
			# Reload list if out of proxies
			self.proxies = self.load_proxies()
		self.cur_proxy_addr = self.proxies.get_nowait()
		log('[{0}] Proxy: {1}'.format(self.tid, self.cur_proxy_addr))
		self.cur_proxy = urllib2.build_opener(urllib2.ProxyHandler({'http': self.cur_proxy_addr}))
	
	def go_easy(self):
		return False

class GlypeWorker(ProxyWorker):
	"""Uses glype proxies from glypes.txt"""
	
	def proxy_filename(self):
		return 'glypes.txt'
	
	def get(self, url, text=False):
		"""POSTing to includes/update.php does not work like one would think, browse.php works and is enough"""
		if not self.cur_proxy: self.refresh()
		while True:
			try:
				req = urllib2.Request('http://{0}/browse.php?{1}'.format(self.cur_proxy_addr, urllib.urlencode({'b': 24, 'f': 'norefer', 'u': url})), headers={'User-Agent': GLYPE_USER_AGENT, 'Referer': 'http://{0}/'.format(self.cur_proxy_addr)})
				resp = urllib2.urlopen(req, timeout=10)
				if text and resp.headers.get('Content-Type')[:10] != 'text/plain':
					# Glype only injects the browser thingy on HTML, and respects text/plain
					log('[!] Proxy {0} is blocking Pastebin (not plain text)'.format(self.cur_proxy_addr))
					self.refresh()
					continue
				content = resp.read()
				
				# How Glype reacts to HTTP errors
				error_index = content.find('The requested resource could not be loaded because the server returned an error:')
				if error_index > -1:
					if '<b>403 Forbidden</b>' in content[error_index:]:
						log('[!] Pastebin ban on proxy {0}'.format(self.cur_proxy_addr))
					self.refresh()
					continue
				
				if text and url in content:
					# Same reason as ProxyWorker
					log('[!] Proxy {0} is blocking Pastebin (url in text)'.format(self.cur_proxy_addr))
					self.refresh()
				else:
					return content
			except urllib2.HTTPError as e:
				# When going through an open Glype list, most of the time this is going to be a CloudFlare HTTP 522
				log('[!] Proxy {0} gave error {1}'.format(self.cur_proxy_addr, e.code))
				self.refresh()
			except:
				self.refresh()
	
	def go_easy(self):
		return False

class RemoteWorker(Worker):
	"""Worker which communicates to a remote host running remote.py"""
	def __init__(self, address, secret):
		"""Pass the remote host[:port] and authentication secret"""
		Worker.__init__(self)
		split = address.split(':')
		self.address = split[0]
		self.port = len(split) > 1 and int(split[1]) or 5397
		self.secret = secret
	
	def get(self, url, text=False):
		"""
		Request:  {'s': AUTHENTICATION_SECRET, 'u': URL}\n
		Response: short httpCode; int length; char[length] data;
		"""
		try:
			sock = socket.create_connection((self.address, self.port), 10)
			sock.sendall(json.dumps({'s': self.secret, 'u': url}) + '\n')
			
			code, length = struct.unpack('>HI', sock.recv(6))
			
			if code == 403:
				log('[!] Pastebin ban on remote worker {0}'.format(self.address))
				self.banned = True
				time.sleep(600)
				self.banned = False
				return None
			elif code not in [200, 404]:
				log('[!] Remote worker {0} returned error {1}'.format(self.address, response['s']))
			elif code == 200:
				data = ''
				# I know there's a better way to do a socket read loop than this, but whatever...
				while len(data) < length:
					try:
						data += sock.recv(4096)
					except:
						break
				return data
		except:
			log('[!] Could not contact remote worker {0}'.format(self.address))
			log(traceback.format_exc()) # DEBUG
			return None

seen_pastes = collections.deque(maxlen=256) # a list would do, but RAM is not infinite
def thread(worker, tid):
	"""Worker thread, gets the worker itself and thread ID passed"""
	worker.tid = tid
	
	db = get_database() # declared in config
	c = db.cursor()
	
	while not worker.stop:
		html = worker.get('http://pastebin.com/archive')
		if not html:
			log('[{0}] Could not get Pastebin archive page'.format(tid))
			time.sleep(NEW_PASTE_INTERVAL)
			continue
		ts = time.time()
		
		soup = BeautifulSoup.BeautifulSoup(html)
		table = soup.find('table', 'maintable')
		if not table: # maintable not found, this HTML is definitely not pastebin
			log('[{0}] Invalid Pastebin archive page'.format(tid))
			worker.refresh()
			continue
		
		# Paste links are adjacent to the icon image (i_p0)
		for img in table.findAll('img', 'i_p0'):
			paste_link = img.nextSibling
			paste = paste_link['href']
			if paste[0] == '/' and len(paste) == 9:
				# local/remote/proxy
				paste = paste[1:]
			else:
				# glype
				paste = urllib.unquote(paste)
				base = 'pastebin.com/'
				id_index = paste.find(base)+len(base)
				if id_index == len(base) - 1: continue			
				paste = paste[id_index:id_index+8]
			
			# Check if we downloaded this paste already
			if paste in seen_pastes: continue
			seen_pastes.append(paste)
			
			paste_title = paste_link.text.encode('utf-8', errors='ignore') # BeautifulSoup is unicode, let's not cause headaches about that
			if paste_title == 'Untitled': paste_title = None # Untitled gets stored as NULL on the database
			
			log('[{0}] {1} => downloading'.format(tid, paste))
			
			# Get the paste
			content = worker.get('http://pastebin.com/raw.php?i=' + paste, True)
			while content != None and len(content) == 0: # no paste can be empty!
				worker.refresh()
				if worker.go_easy(): time.sleep(RAW_PASTE_DELAY) # wait before trying again
				content = worker.get('http://pastebin.com/raw.php?i=' + paste, True)
			
			log('[{0}] {1} => downloaded'.format(tid, paste))
			
			while True:
				try:
					# Run DB query
					c.execute(DB_QUERY, (paste, paste_title, int(time.time()), content))
					break
				except pymysql.DatabaseError as e:
					log('[!] Error while inserting paste {0} into database'.format(paste))
					log(traceback.format_exc()) # DEBUG
					try:
						# I've had situations where ping fails with MySQL...
						db.ping(reconnect=True)
					except:
						# ...in this case, just reconnect
						time.sleep(10)
						try:
							c.close()
						except:
							pass
						try:
							db.close()
						except:
							pass
						db = get_database()
						c = db.cursor()
					continue
			
			if worker.go_easy(): time.sleep(RAW_PASTE_DELAY) # wait before going for the next paste
		
		if worker.go_easy():
			# Wait until the new paste interval has passed
			while time.time() - ts < NEW_PASTE_INTERVAL:
				time.sleep(0.5)
	c.close()
	db.close()

workers = []
tid = 0
def launch_worker(worker):
	"""Launches a worker, and returns it for convenience"""
	global workers
	global tid
	tid += 1
	t = threading.Thread(target=thread, args=(worker, tid))
	t.daemon = False
	t.start()
	workers.append(worker)
	return worker

def all_workers_banned():
	"""Verify if all rate-limited (= aren't supposed to be banned) workers are banned"""
	all_banned = True
	for worker in workers:
		if worker.go_easy() and not worker.banned:
			all_banned = False
			break
	return all_banned

# Deploy all workers!
for i in range(LOCAL_WORKERS):
	launch_worker(Worker())
	time.sleep(WORKER_OFFSET)

for worker in REMOTE_WORKERS:
	launch_worker(RemoteWorker(*worker))
	time.sleep(WORKER_OFFSET)

if DEPLOY_PROXIES > 0 or DEPLOY_GLYPES > 0:
	extra_workers = []
	while True:
		time.sleep(WORKER_OFFSET)
		all_banned = all_workers_banned()
		if all_banned and len(extra_workers) == 0:
			# All workers banned, deploy reinforcements
			extra_workers_deployed = True
			print '[i] Deploying extra workers!'
			
			for i in range(DEPLOY_PROXIES):
				extra_workers.append(launch_worker(ProxyWorker()))
				time.sleep(WORKER_OFFSET)
			
			for i in range(DEPLOY_GLYPES):
				extra_workers.append(launch_worker(GlypeWorker()))
				time.sleep(WORKER_OFFSET)
		elif not all_banned and len(extra_workers) > 0:
			time.sleep(WORKER_OFFSET) # wait a bit, could be a fluke
			# A worker is not banned anymore, stop all extra workers
			if not all_workers_banned():
				print '[i] Stopping extra workers!'
				for worker in extra_workers[:]: # Avoid concurrent modification
					workers.remove(worker)
					extra_workers.remove(worker)
					worker.stop = True
					tid -= 1
