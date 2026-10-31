"""Keep producer resources alive until Maya releases their last published frame."""


class RetiredGpuPools:
    def __init__(self):
        self.pending=[]

    def retire(self,pool,last_frame):
        if pool:self.pending.append((last_frame,pool))

    def collect(self,released_frame):
        retained=[]
        for last_frame,pool in self.pending:
            if last_frame<=released_frame:
                for resource in pool:resource.close()
            else:retained.append((last_frame,pool))
        self.pending=retained

    def close(self):
        for _,pool in self.pending:
            for resource in pool:resource.close()
        self.pending=[]


class SizedGpuResources:
    """Bounded LRU of producer framebuffers and shared textures by dimensions.

    Eviction frees only producer framebuffers immediately. Shared handles remain
    retired until Maya acknowledges their last frame, exactly like resize.
    """
    def __init__(self, retired, capacity=3):
        from collections import OrderedDict
        self.entries=OrderedDict();self.retired=retired;self.capacity=capacity
        self.allocations=0;self.reuses=0

    def acquire(self, key, factory, released_frame=0):
        existing=self.entries.get(key)
        if key in self.entries:
            if max(existing['frames'],default=0)<=released_frame:
                self.reuses+=1
                self.entries.move_to_end(key)
                return existing
            # A delayed import can still own one of this size's handles. Do
            # not overwrite it or block the producer waiting on the consumer.
        # Allocation can fail under VRAM pressure. Keep all existing ownership
        # intact until the replacement has been constructed successfully.
        value=factory()
        if existing is not None:
            self.entries.pop(key)
            self.retired.retire(existing['pool'],max(existing['frames'],default=0))
            existing['offscreen'].free();existing['depth_offscreen'].free()
        self.entries[key]=value;self.allocations+=1
        while len(self.entries)>self.capacity:
            _,old=self.entries.popitem(last=False)
            self.retired.retire(old['pool'],max(old['frames'],default=0))
            old['offscreen'].free();old['depth_offscreen'].free()
        return value

    def close(self):
        for value in self.entries.values():
            for resource in value['pool']:resource.close()
            value['offscreen'].free();value['depth_offscreen'].free()
        self.entries.clear()
