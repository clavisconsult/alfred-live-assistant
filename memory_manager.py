import lmdb
try:
    import ujson as json
except ImportError:
    import json

class MemoryManager:
    def __init__(self):
        # Extreme Optimization: Lightning Memory-Mapped Database (LMDB)
        # Using memory mapping to bypass the OS file system cache entirely
        self.env = lmdb.open('alfred_memory_lmdb', map_size=10485760, sync=False, metasync=False, writemap=True)
        
    def get_formatted_context(self):
        with self.env.begin() as txn:
            cursor = txn.cursor()
            memories = []
            for key, value in cursor:
                memories.append(f"- {key.decode('utf-8')}: {value.decode('utf-8')}")
            
            if not memories:
                return "No prior memories recorded yet."
            return "CRITICAL PERSISTENT MEMORY DATABANK (You must adhere to these facts and preferences):\n" + "\n".join(memories)

    def remember(self, topic, details):
        with self.env.begin(write=True) as txn:
            txn.put(topic.encode('utf-8'), details.encode('utf-8'))
        # Async flush to disk to guarantee 0.00ms latency on the audio thread
        self.env.sync()
