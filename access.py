from firebase_admin import storage
from os.path import basename, normpath
import time
import project

storage_bucket = "{project_id}.appspot.com"
allowed_prefix = "access/allowed/"
blocked_prefix = "access/blocked/"

# firebase_admin is assumed to already by initialized
class Accessor:
    def __init__(self, timeout=60):
        self._timeout = timeout
        self._allowed = set()
        self._blocked = set()
        self._timestamp = time.time()
        self._get_lists()

    def is_allowed(self, email):
        self._check_lists()
        return not self.is_blocked(email) and (email.endswith(".edu") or email.endswith(".org") or email.endswith(".gov") or has_match(email, self._allowed))

    def is_blocked(self, email):
        self._check_lists()
        return has_match(email, self._blocked)

    def _check_lists(self):
        if (time.time() - self._timestamp) > self._timeout:
            self._get_lists()

    def _get_lists(self):
        # this makes 2 requests, because bucket.list_blobs only lists the next layer of folders one depth beyond the prefix given
        # so using that function, it doesn't seem to be possible to get all the blobs below allowed and blocked folders
        self._allowed = subfolders(storage_bucket, allowed_prefix)
        self._blocked = subfolders(storage_bucket, blocked_prefix)
        self._timestamp = time.time()

def subfolders(bucket, prefix):
    buck = storage.bucket(bucket.format(project_id=project.project_id))
    iterator = buck.list_blobs(prefix=prefix, delimiter="/")
    subdirs = set()
    for page in iterator.pages:
        for prefix in page.prefixes:
            subdirs.update([basename(normpath(prefix))])
    
    return subdirs

def has_match(email, suffixes):
    for suffix in suffixes:
        if email.endswith(suffix):
            return True
    
    return False
