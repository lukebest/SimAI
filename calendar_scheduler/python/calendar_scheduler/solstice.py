class SolsticeScheduler:
    def __init__(self, frame_slots: int = 1024):
        self.frame_slots = int(frame_slots)

    def compute(self, demand):
        raise NotImplementedError("SolsticeScheduler is implemented in a later task")
