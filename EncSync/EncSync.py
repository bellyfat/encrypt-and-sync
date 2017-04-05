#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import hashlib
import tempfile
import time
import io

from . import SyncList
from . import YandexDiskApi
from . import Encryption
from . import paths

def expand_path(path):
    return os.path.realpath(os.path.expanduser(path))

def chunk(b, n):
    n = int(n)
    for i in range(int(len(b) // n)):
        yield b[i * n:(i + 1) * n]

APP_ID = "59c915d2c2d546d3842f2c6fe3a9678e"
APP_SECRET = "faca3ddd1d574e54a258aa5d8e521c8d"

AUTH_URL = "https://oauth.yandex.ru/authorize?response_type=code&client_id=" + APP_ID

UPLOAD_BUFFER_LIMIT = 80 * 1024**2 # In bytes

class EncSync(object):
    def __init__(self, master_key):
        self.targets = []
        self.plain_key = ""
        self.key = ""
        self.set_master_key(master_key)
        self.ynd_id = APP_ID
        self.ynd_token = ""
        self.ynd_secret = APP_SECRET
        self.ynd = YandexDiskApi.YndApi(self.ynd_id, "", self.ynd_secret)
        self.upload_limit = 1024**4
        self.download_limit = 1024**4
        self.sync_threads = 2
        self.download_threads = 2

    def set_token(self, token):
        self.ynd_token = token
        self.ynd = YandexDiskApi.YndApi(self.ynd_id, self.ynd_token, self.ynd_secret)

    def set_key(self, key):
        self.plain_key = key
        self.key = hashlib.sha256(key.encode("utf8")).digest()

    def set_master_key(self, master_key):
        self.master_key = hashlib.sha256(master_key.encode("utf8")).digest()

    def check_token(self, max_retries=1):
        r = self.ynd.get_disk_data(max_retries=max_retries)

        if not r["success"] and r["data"] is not None:
            return r["data"]["error"] != "UnauthorizedError"

        return True

    def store_config(self, path):
        js = json.dumps({"targets": self.targets,
                         "downloadSpeedLimit": self.download_limit,
                         "uploadSpeedLimit": self.upload_limit,
                         "key": self.plain_key,
                         "nSyncThreads": self.sync_threads,
                         "nDownloadThreads": self.download_threads,
                         "yandexAppToken": self.ynd_token}).encode("utf8")
        with open(path, "wb") as f:
            f.write(Encryption.encrypt_data(js, self.master_key))
    
    def load_config(self, path):
        with open(path, "rb") as f:
            d = json.loads(Encryption.decrypt_data(f.read(), self.master_key).decode("utf8"))
            self.targets = d["targets"]
            self.set_key(d["key"])
            self.ynd_token = d["yandexAppToken"]
            self.download_limit = d["downloadSpeedLimit"]
            self.upload_limit = d["uploadSpeedLimit"]
            self.sync_threads = d["nSyncThreads"]
            self.download_threads = d["nDownloadThreads"]
            self.ynd = YandexDiskApi.YndApi(self.ynd_id, self.ynd_token, self.ynd_secret)

    def temp_encrypt(self, path):
        size = os.path.getsize(path)
        if size < UPLOAD_BUFFER_LIMIT:
            f = io.BytesIO()
        else:
            f = tempfile.TemporaryFile(mode="w+b")
        Encryption.encrypt_file(path, f, self.key)
        f.seek(0)
        return f

    def decrypt_file(self, in_path, out_path):
        Encryption.decrypt_file(in_path, out_path, self.key)

    def encrypt_path(self, path, prefix=None, IVs=b""):
        if prefix is not None:
            enc_path, IVs = self.encrypt_path(paths.cut_prefix(path, prefix), IVs=IVs)
            return paths.join(prefix, enc_path), IVs
        elif path == "":
            return "", b""
        else:
            f = lambda x, IV: Encryption.encrypt_filename(x, self.key, IV) if x else ("", b"")
            out_IVs = b""
            path_fragments = []

            if len(IVs):
                for fragment, IV in zip(path.split("/"), chunk(IVs, 16)):
                    enc_fragment = f(fragment, IV)[0]
                    path_fragments.append(enc_fragment)
                    out_IVs += IV
            else:
                for fragment in path.split("/"):
                    enc_fragment, IV = f(fragment, b"")
                    path_fragments.append(enc_fragment)
                    out_IVs += IV

            return "/".join(path_fragments), out_IVs

    def decrypt_path(self, path, prefix=None):
        if prefix is not None:
            dec_path, IVs = self.decrypt_path(paths.cut_prefix(path, prefix))
            return paths.join(prefix, dec_path), IVs
        else:
            f = lambda x: Encryption.decrypt_filename(x, self.key) if x else ("", b"")
            IVs = b""
            path_fragments = []

            for fragment in path.split("/"):
                dec_fragment, IV = f(fragment)
                path_fragments.append(dec_fragment)
                IVs += IV

            return "/".join(path_fragments), IVs
