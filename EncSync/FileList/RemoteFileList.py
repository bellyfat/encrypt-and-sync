#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .FileList import FileList
from .. import Paths
from ..common import normalize_node, node_tuple_to_dict, format_timestamp
from ..common import escape_glob

def prepare_path(path):
    return Paths.join_properly("/", path)

class RemoteFileList(FileList):
    def __init__(self, directory=None, *args, **kwargs):
        FileList.__init__(self, "remote_filelist.db", directory, *args, **kwargs)

    def create(self):
        with self.connection:
            self.connection.execute("""CREATE TABLE IF NOT EXISTS filelist
                                       (type TEXT,
                                        modified DATETIME,
                                        padded_size INTEGER,
                                        path TEXT UNIQUE ON CONFLICT REPLACE,
                                        IVs TEXT)""")
            self.connection.execute("""CREATE INDEX IF NOT EXISTS path_index
                                       ON filelist(path ASC)""")

    def insert_node(self, node):
        node = dict(node)
        normalize_node(node, False)

        if node["type"] is None:
            raise ValueError("Node type is None")

        self.connection.execute("""INSERT INTO filelist VALUES
                                   (?, ?, ?, ?, ?)""",
                                (node["type"],
                                 format_timestamp(node["modified"]),
                                 node["padded_size"],
                                 prepare_path(node["path"]),
                                 node["IVs"]))

    def remove_node(self, path):
        path = prepare_path(path)

        self.connection.execute("DELETE FROM filelist WHERE path=? OR path=?",
                                (path, Paths.dir_normalize(path)))

    def remove_node_children(self, path):
        path = prepare_path(Paths.dir_normalize(path))
        path = escape_glob(path)

        self.connection.execute("DELETE FROM filelist WHERE path GLOB ?", (path + "*",))

    def clear(self):
        self.connection.execute("DELETE FROM filelist")

    def find_node(self, path):
        path = prepare_path(path)

        with self.connection:
            self.connection.execute("""SELECT * FROM filelist
                                       WHERE path=? OR path=? LIMIT 1""",
                                    (path, Paths.dir_normalize(path)))
            return node_tuple_to_dict(self.connection.fetchone())

    def find_node_children(self, path):
        path = prepare_path(path)
        path = escape_glob(path)
        path_n = Paths.dir_normalize(path)

        with self.connection:
            self.connection.execute("""SELECT * FROM filelist
                                       WHERE path GLOB ? OR path=? OR path=?
                                       ORDER BY path ASC""",
                                    (path_n + "*", path, path_n))

            return (node_tuple_to_dict(i) for i in self.connection.genfetch())

    def select_all_nodes(self):
        with self.connection:
            self.connection.execute("SELECT * FROM filelist ORDER BY path ASC")

            return (node_tuple_to_dict(i) for i in self.connection.genfetch())

    def is_empty(self, parent_dir="/"):
        parent_dir = prepare_path(Paths.dir_normalize(parent_dir))
        parent_dir = escape_glob(parent_dir)

        with self.connection:
            self.connection.execute("""SELECT COUNT(*) FROM filelist
                                       WHERE path GLOB ? LIMIT 1""",
                                    (parent_dir + "*",))

            return self.connection.fetchone()[0] == 0

    def get_file_count(self, parent_dir="/"):
        parent_dir = prepare_path(Paths.dir_normalize(parent_dir))
        parent_dir = escape_glob(parent_dir)

        with self.connection:
            self.connection.execute("SELECT COUNT(*) FROM filelist WHERE path GLOB ?",
                                    (parent_dir + "*",))

            return self.connection.fetchone()[0]
