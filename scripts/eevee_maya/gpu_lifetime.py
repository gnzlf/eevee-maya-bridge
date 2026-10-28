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
