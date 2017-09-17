#!/usr/bin/env python
# -*- coding: utf-8 -*-

import s3m

import time

from .Logging import logger

__all__ = ["connect", "Connection"]

class Connection(s3m.Connection):
    def __init__(self, *args, **kwargs):
        s3m.Connection.__init__(self, *args, **kwargs)

        self.last_commit = time.time()

    def begin_transaction(self, transaction_type=""):
        if transaction_type.lower() not in ("", "immediate", "deferred", "exclusive"):
            raise ValueError("Unknown transaction type: %r" % (transaction_type))

        return self.execute("BEGIN %s TRANSACTION" % transaction_type)

    def time_since_last_commit(self):
        return time.time() - self.last_commit

    def commit(self):
        self.last_commit = time.time()
        s3m.Connection.commit(self)

    def seamless_commit(self):
        with self:
            self.commit()
            self.begin_transaction("immediate")

    def genfetch(self, *args, **kwargs):
        r = self.fetchmany(*args, **kwargs)

        while r:
            for i in r:
                yield i
            r = self.fetchmany(*args, **kwargs)

def connect(path, *args, **kwargs):
    kwargs = dict(kwargs)
    kwargs.setdefault("isolation_level", None)
    kwargs.setdefault("factory", Connection)
    kwargs.setdefault("check_same_thread", False)

    logger.debug("s3m.connect(%r, ...)" % (path,))

    return s3m.connect(path, *args, **kwargs)
