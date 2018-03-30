#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading

from ..Task import Task
from ..FileList import FileList, DuplicateList
from ..Scannable import DecryptedScannable, EncryptedScannable
from .. import PathMatch
from .. import Paths
from .Tasks import EncryptedScanTask, DecryptedScanTask
from .Tasks import AsyncEncryptedScanTask, AsyncDecryptedScanTask
from .Worker import ScanWorker

__all__ = ["ScanTarget"]

class ScanTarget(Task):
    """
        Events: next_node, duplicates_found, scan_finished
    """

    def __init__(self, scanner, name):
        Task.__init__(self)

        self.scanner = scanner
        self.config = scanner.config
        self.type = None
        self.name = name
        self.storage = None
        self.encrypted = False

        self.path = ""
        self.filename_encoding = "base64"

        self.shared_flist = FileList(name, scanner.directory)
        self.shared_duplist = None

        self.tasks = []
        self.task_lock = threading.Lock()

    def get_next_task(self):
        with self.task_lock:
            try:
                return self.tasks.pop(0)
            except IndexError:
                pass

    def add_task(self, task):
        with self.task_lock:
            self.tasks.append(task)

        for w in self.scanner.get_worker_list():
            w.set_dirty()

    def stop_condition(self):
        if self.stopped or self.scanner.stop_condition():
            return True

        return self.status not in (None, "pending")

    def begin_scan(self):
        self.shared_flist.clear()

        if self.encrypted:
            self.shared_duplist.remove_children(self.path)

        if self.stop_condition():
            return

        if self.encrypted:
            scannable = EncryptedScannable(self.storage, self.path,
                                           filename_encoding=self.filename_encoding)
        else:
            scannable = DecryptedScannable(self.storage, self.path)

        try:
            scannable.identify()
        except FileNotFoundError:
            return

        if self.stop_condition():
            return

        path = self.path

        if scannable.type == "d":
            path = Paths.dir_normalize(path)

        allowed_paths = self.config.allowed_paths.get(self.storage.name, [])

        if not PathMatch.match(path, allowed_paths):
            return

        if scannable.type is not None:
            self.shared_flist.insert_node(scannable.to_node())

            if self.storage.parallelizable:
                if self.encrypted:
                    task = AsyncEncryptedScanTask(self, scannable)
                else:
                    task = AsyncDecryptedScanTask(self, scannable)
            elif self.encrypted:
                task = EncryptedScanTask(self, scannable)
            else:
                task = DecryptedScanTask(self, scannable)

            self.add_task(task)

    def complete(self, worker):
        if self.stop_condition():
            return True

        self.storage = self.config.storages[self.type]
        self.shared_duplist = DuplicateList(self.storage.name, self.scanner.directory)

        if not self.scanner.enable_journal:
            self.shared_flist.disable_journal()
            self.shared_duplist.disable_journal()

        self.shared_flist.create()
        self.shared_duplist.create()

        self.status = "pending"

        try:

            self.shared_flist.begin_transaction()
            self.shared_duplist.begin_transaction()

            self.begin_scan()

            if self.stop_condition():
                self.shared_flist.rollback()
                self.shared_duplist.rollback()
                return True

            if self.storage.parallelizable:
                self.scanner.start_workers(self.scanner.n_workers, ScanWorker,
                                           self.scanner, self)
                self.scanner.wait_workers()
                self.scanner.stop_workers()
            elif self.tasks:
                self.scanner.start_worker(ScanWorker, self.scanner, self)

            self.scanner.wait_workers()
            self.scanner.stop_workers()

            if self.stop_condition():
                self.scanner.stop_workers()
                self.scanner.join_workers()
                self.shared_flist.rollback()
                self.shared_duplist.rollback()
                return True

            self.scanner.join_workers()

            if self.status == "pending":
                self.shared_flist.commit()
                self.shared_duplist.commit()
                self.status = "finished" 

                self.emit_event("scan_finished")
            else:
                self.shared_flist.rollback()
                self.shared_duplist.rollback()
        except Exception as e:
            self.scanner.stop_workers()
            self.shared_flist.rollback()
            self.shared_duplist.rollback()

            self.status = "failed"

            raise e

        return True
