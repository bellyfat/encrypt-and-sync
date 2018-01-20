# -*- coding: utf-8 -*-

import time

from requests.exceptions import RequestException
import yadisk.settings
from yadisk.exceptions import PathNotFoundError, DirectoryExistsError
from yadisk.exceptions import RetriableYaDiskError
import yadisk.utils

from ..constants import YADISK_APP_ID, YADISK_APP_SECRET

from ..SpeedLimiter import SpeedLimiter
from .Storage import Storage
from .Exceptions import ControllerInterrupt, TemporaryStorageError
from .DownloadController import DownloadController
from .UploadController import UploadController

__all__ = ["YaDiskStorage"]

MIN_READ_SIZE = 512 * 1024 # Bytes
DOWNLOAD_CHUNK_SIZE = 16384
RETRY_CODES = {500, 502, 503, 504}

def _yadisk_meta_to_dict(meta):
    try:
        modified = time.mktime(meta.modified.utctimetuple())
        modified = max(modified, 0)
    except (OSError, OverflowError):
        modified = 0

    return {"type":     meta.type,
            "name":     meta.name,
            "modified": modified,
            "size":     meta.size if meta.type != "dir" else 0,
            "link":     None}

class ControlledSpeedLimiter(SpeedLimiter):
    def __init__(self, controller, *args, **kwargs):
        SpeedLimiter.__init__(self, *args, **kwargs)

        self.controller = controller

    def sleep(self, duration):
        tolerance = 0.001
        check_interval = 0.25
        t1 = time.time()

        left_to_sleep = duration

        while not self.controller.stopped and left_to_sleep > tolerance:
            time.sleep(min(left_to_sleep, check_interval))

            left_to_sleep = duration - (time.time() - t1)

class LimitedFile(object):
    def __init__(self, file, controller, limit=float("inf")):
        self.file = file
        self.limit = limit

        if self.limit != float("inf"):
            self.limit = int(self.limit)

        self.last_delay = 0
        self.cur_read = 0
        self.controller = controller
        self.speed_limiter = ControlledSpeedLimiter(controller, self.limit)

    def __iter__(self):
        return self

    def __next__(self):
        return self.readline()

    def seek(self, *args, **kwargs):
        self.file.seek(*args, **kwargs)

    def tell(self):
        return self.file.tell()

    def delay(self):
        self.speed_limiter.delay()

    def readline(self):
        if self.controller.stopped:
            raise ControllerInterrupt

        self.delay()

        if self.controller.stopped:
            raise ControllerInterrupt

        line = self.file.readline()

        if self.controller.stopped:
            raise ControllerInterrupt

        self.speed_limiter.quantity += len(line)
        self.controller.uploaded = self.file.tell()

        return line

    def read(self, size=-1, min_size=MIN_READ_SIZE):
        amount_read = 0

        content = b""

        self.controller.uploaded = self.file.tell()
        
        if self.controller.stopped:
            raise ControllerInterrupt

        if size == -1:
            amount_to_read = self.limit
            if amount_to_read == float("inf"):
                amount_to_read = -1
            condition = lambda: cur_content
            # Just any non-empty string
            cur_content = b"1"
        else:
            size = max(min_size, size)
            amount_to_read = min(self.limit, size)
            condition = lambda: amount_read < size

        while condition():
            self.delay()

            if self.controller.stopped:
                raise ControllerInterrupt

            if size != -1:
                amount_to_read = min(size - amount_read, amount_to_read)

            cur_content = self.file.read(amount_to_read)

            if self.controller.stopped:
                raise ControllerInterrupt

            content += cur_content

            l = len(cur_content)

            self.speed_limiter.quantity += l
            amount_read += l

            self.controller.uploaded = self.file.tell()

            if l < amount_to_read:
                break

        return content

class YaDiskDownloadController(DownloadController):
    def __init__(self, ynd, in_path, out_file, limit=float("inf"), timeout=None, n_retries=None):
        self.speed_limiter = ControlledSpeedLimiter(self, limit)

        DownloadController.__init__(self, out_file, limit)

        self.in_path = in_path
        self.yadisk = ynd
        self.timeout = timeout
    
        self.n_retries = n_retries

    @property
    def limit(self):
        return self.speed_limiter.limit

    @limit.setter
    def limit(self, value):
        self.speed_limiter.limit = value

    def work(self):
        if self.stopped:
            raise ControllerInterrupt

        try:
            link = self.yadisk.get_download_link(self.in_path,
                                                 timeout=self.timeout,
                                                 n_retries=self.n_retries)
        except PathNotFoundError as e:
            raise FileNotFoundError(str(e))
        except RetriableYaDiskError as e:
            raise TemporaryStorageError(str(e))

        def attempt():
            if self.stopped:
                raise ControllerInterrupt

            response = self.yadisk.make_session().get(link, stream=True, timeout=self.timeout)

            if self.stopped:
                raise ControllerInterrupt

            if response.status_code != 200:
                raise yadisk.utils.get_exception(response)

            self.speed_limiter.begin()
            self.speed_limiter.quantity = 0

            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if self.stopped:
                    raise ControllerInterrupt

                if not chunk:
                    continue

                self.out_file.write(chunk)
                l = len(chunk)
                self.downloaded += l
                self.speed_limiter.quantity += l

                if self.stopped:
                    raise ControllerInterrupt

                self.speed_limiter.delay()

                if self.stopped:
                    raise ControllerInterrupt

        yadisk.utils.auto_retry(attempt, self.n_retries, 0.0)

class YaDiskUploadController(UploadController):
    def __init__(self, ynd, in_file, out_path, limit=float("inf"), timeout=None, n_retries=None):
        in_file = LimitedFile(in_file, self, limit)
        UploadController.__init__(self, in_file, limit)

        self.yadisk = ynd
        self.out_path = out_path
        self.timeout = timeout

        self.n_retries = n_retries

    @property
    def limit(self):
        return self.in_file.limit

    @limit.setter
    def limit(self, value):
        self.in_file.limit = value

    def work(self):
        if self.stopped:
            raise ControllerInterrupt

        try:
            self.yadisk.upload(self.in_file, self.out_path, overwrite=True,
                               timeout=self.timeout, n_retries=self.n_retries)
        except PathNotFoundError as e:
            raise FileNotFoundError(str(e))
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))

class YaDiskStorage(Storage):
    name = "yadisk"
    case_sensitive = True
    parallelizable = True

    def __init__(self, encsync):
        Storage.__init__(self, encsync)

        token = encsync.encrypted_data.get("yadisk_token", "")

        self.yadisk = yadisk.YaDisk(YADISK_APP_ID, YADISK_APP_SECRET, token)

    def get_meta(self, path, timeout=None, n_retries=None):
        if timeout is None:
            timeout = self.encsync.timeout

        if n_retries is None:
            n_retries = self.encsync.n_retries

        try:
            meta = self.yadisk.get_meta(path, timeout=timeout, n_retries=n_retries)
        except PathNotFoundError as e:
            raise FileNotFoundError(str(e))
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))

        return _yadisk_meta_to_dict(meta)

    def listdir(self, path, timeout=None, n_retries=None):
        if timeout is None:
            timeout = self.encsync.timeout

        if n_retries is None:
            n_retries = self.encsync.n_retries

        try:
            contents = self.yadisk.listdir(path, timeout=timeout, n_retries=n_retries)

            for i in contents:
                yield _yadisk_meta_to_dict(i)
        except PathNotFoundError as e:
            raise FileNotFoundError(str(e))
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))

    def mkdir(self, path, timeout=None, n_retries=None):
        if timeout is None:
            timeout = self.encsync.timeout

        if n_retries is None:
            n_retries = self.encsync.n_retries

        try:
            self.yadisk.mkdir(path, timeout=timeout, n_retries=n_retries)
        except PathNotFoundError as e:
            raise FileNotFoundError(str(e))
        except DirectoryExistsError as e:
            raise FileExistsError(str(e))
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))

    def remove(self, path, timeout=None, n_retries=None):
        if timeout is None:
            timeout = self.encsync.timeout

        if n_retries is None:
            n_retries = self.encsync.n_retries

        try:
            self.yadisk.remove(path, timeout=timeout, n_retries=n_retries)
        except PathNotFoundError as e:
            raise FileNotFoundError(str(e))
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))

    def upload(self, in_file, out_path, timeout=None, n_retries=None, limit=None):
        if limit is None:
            limit = self.encsync.upload_limit

        if n_retries is None:
            n_retries = self.encsync.n_retries

        if timeout is None:
            timeout = self.encsync.upload_timeout

        controller = YaDiskUploadController(self.yadisk, in_file, out_path,
                                            limit, timeout, n_retries)

        return controller

    def download(self, in_path, out_file, timeout=None, n_retries=None, limit=None):
        if limit is None:
            limit = self.encsync.download_limit

        if n_retries is None:
            n_retries = self.encsync.n_retries

        if timeout is None:
            timeout = self.encsync.timeout

        controller = YaDiskDownloadController(self.yadisk, in_path, out_file,
                                              limit, timeout, n_retries)

        return controller

    def is_file(self, path, timeout=None, n_retries=None):
        if timeout is None:
            timeout = self.encsync.timeout

        if n_retries is None:
            n_retries = self.encsync.n_retries

        try:
            return self.yadisk.is_file(path, timeout=timeout, n_retries=n_retries)
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))

    def is_dir(self, path, timeout=None, n_retries=None):
        if timeout is None:
            timeout = self.encsync.timeout

        if n_retries is None:
            n_retries = self.encsync.n_retries

        try:
            return self.yadisk.is_dir(path, timeout=timeout, n_retries=n_retries)
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))

    def exists(self, path, timeout=None, n_retries=None):
        if timeout is None:
            timeout = self.encsync.timeout

        if n_retries is None:
            n_retries = self.encsync.n_retries

        try:
            return self.yadisk.exists(path, timeout=timeout, n_retries=n_retries)
        except (RetriableYaDiskError, RequestException) as e:
            raise TemporaryStorageError(str(e))