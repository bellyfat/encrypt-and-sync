from .common import node_tuple_to_dict
                                        modified INTEGER,
                                 node["modified"] * 1e6,
        modified = modified * 1e6
                                   VALUES(?, ?, ?, ?)""", ("v", path, ivs, 86400))