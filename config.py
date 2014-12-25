# I figured those values out back in 2011, but they still work as they are.
NEW_PASTE_INTERVAL = 12
RAW_PASTE_DELAY = 1.1
WORKER_OFFSET = NEW_PASTE_INTERVAL / 2

def get_database():
	# Return a Python Database API compliant connection (such as PyMySQL) here
	pass

# Query used to insert a paste into the database. This works for MySQL
DB_QUERY = 'INSERT IGNORE INTO pastes (paste, title, timestamp, data) VALUES (%s, %s, %s, %s)'
#                    VARCHAR[8] PRIMARY KEY^  ^SMALLTEXT  ^INT  ^MEDIUMTEXT

# Amount of local workers, keeping this at 1 is recommended
LOCAL_WORKERS = 1
# All remote workers in ('host[:port]', 'secret') format
REMOTE_WORKERS = []

# When all local and remote workers are banned, how many HTTP proxy and Glype
# proxy workers to start up until they are unbanned. 0 for none
DEPLOY_PROXIES = 0
DEPLOY_GLYPES = 0

# User agent to use for Glype proxies. Some of those run behind CloudFlare,
# which may not like a generic Python user agent.
GLYPE_USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:34.0) Gecko/20100101 Firefox/34.0'
